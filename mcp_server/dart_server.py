import os
import sys
import contextlib
from pathlib import Path
from dotenv import load_dotenv
import OpenDartReader
from mcp.server.fastmcp import FastMCP

# 상위 폴더의 .env 로드
BASE_DIR = Path(__file__).parent.parent.resolve()
load_dotenv(BASE_DIR / ".env")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from config import STOCK_ALIASES
except Exception:
    STOCK_ALIASES = {}

mcp = FastMCP("dart-server")

DART_API_KEY = os.getenv("DART_API_KEY", "").strip()

# OpenDartReader 모듈 수준 사전 초기화 (워커 스레드 내 임포트 락 및 지연 방지)
_cached_dart = None
if DART_API_KEY:
    try:
        orig_cwd = os.getcwd()
        os.chdir(BASE_DIR)
        _cached_dart = OpenDartReader(DART_API_KEY)
    except Exception as e:
        sys.stderr.write(f"[DART_SERVER] 사전 초기화 오류: {e}\n")
        sys.stderr.flush()
    finally:
        os.chdir(orig_cwd)

def get_dart_client():
    """DART 클라이언트 반환 및 검증"""
    global _cached_dart
    if _cached_dart is not None:
        return _cached_dart
    if not DART_API_KEY:
        raise ValueError(
            "DART_API_KEY가 설정되지 않았습니다. .env 파일에 DART_API_KEY를 입력해주세요. "
            "(https://opendart.fss.or.kr/ 에서 무료 발급 가능)"
        )
    orig_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        _cached_dart = OpenDartReader(DART_API_KEY)
    finally:
        os.chdir(orig_cwd)
    return _cached_dart

def resolve_corp_name(corp_name_or_code: str) -> str:
    """별칭/은어 및 종목명을 DART 정식 상장사 사명 또는 코드로 정규화"""
    query = (corp_name_or_code or "").strip()
    if not query:
        return query

    # 1. 6자리 종목코드인 경우 그대로 반환
    if query.isdigit() and len(query) == 6:
        return query

    # 2. 은어/약어 사전 확인 (긴 문자열부터 매칭)
    for alias, real_name in sorted(STOCK_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias.lower() == query.lower() or alias == query:
            return real_name

    # 3. DART 상장사 목록에서 정확히 일치 또는 부분 일치 검색
    try:
        dart = get_dart_client()
        if hasattr(dart, "corp_codes") and dart.corp_codes is not None:
            df = dart.corp_codes[dart.corp_codes['stock_code'].str.len() == 6]
            exact = df[df['corp_name'] == query]
            if not exact.empty:
                return exact['corp_name'].values[0]
            if len(query) >= 2:
                match = df[df['corp_name'].str.contains(query, regex=False)]
                if not match.empty:
                    return match['corp_name'].values[0]
    except Exception:
        pass

    return query

@mcp.tool("get_company_overview", description="기업명 또는 종목코드로 기업의 기본 정보(종목코드, 업종, 대표자, 설립일, 결산월 등)를 조회합니다.")
def get_company_overview(corp_name_or_code: str) -> str:
    """
    기업의 기본 개요 정보를 조회합니다.

    Args:
        corp_name_or_code: 회사명(예: '삼성전자', 'SK하이닉스') 또는 6자리 종목코드(예: '005930')
    """
    corp_name_or_code = resolve_corp_name(corp_name_or_code)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            dart = get_dart_client()
            info = dart.company(corp_name_or_code)
            if info is None or (isinstance(info, dict) and info.get("status") not in (None, "000")):
                return f"'{corp_name_or_code}'에 해당하는 기업 정보를 DART에서 찾을 수 없습니다."
            
            overview = f"""[기업 개요: {info.get('corp_name', corp_name_or_code)}]
- 정식 회사명: {info.get('corp_name', '-')}
- 영문명: {info.get('corp_name_eng', '-')}
- 종목코드: {info.get('stock_code', '-')}
- 법인구분: {'유가증권(코스피)' if info.get('corp_cls') == 'Y' else '코스닥' if info.get('corp_cls') == 'K' else '기타'}
- 대표자명: {info.get('ceo_nm', '-')}
- 업종(업태): {info.get('induty_code', '-')}
- 설립일: {info.get('est_dt', '-')}
- 결산월: {info.get('acc_mt', '-')}월
- 주소: {info.get('adres', '-')}
- 홈페이지: {info.get('hm_url', '-')}
"""
            return overview
        except Exception as e:
            return f"[DART 기업 정보 조회 오류] {str(e)}"

@mcp.tool("get_financial_statements", description="기업의 연도별 주요 재무제표(매출액, 영업이익, 당기순이익, 자산총계, 부채총계, 자본총계)를 조회합니다. 기본값은 최신 결산연도인 2025년이며, 2023~2025년 3개년 실적이 자동 포함됩니다.")
def get_financial_statements(corp_name_or_code: str, year: int = 2025) -> str:
    """
    지정된 연도의 사업보고서 기반 주요 재무제표(연결/개별)를 조회합니다.
    최신 결산 사업보고서를 조회하면 최근 3개년 실적(전전기, 전기, 당기)이 한 번에 반환됩니다.

    Args:
        corp_name_or_code: 회사명 또는 종목코드
        year: 조회 기준 사업연도 (기본값: 2025. 2025년 사업보고서 기준 2023~2025년 3개년 실적 조회)
    """
    corp_name_or_code = resolve_corp_name(corp_name_or_code)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            import re
            dart = get_dart_client()
            
            fs = None
            reprt_code = "11011"  # 사업보고서
            
            # 지정된 연도 조회 시도
            try:
                fs = dart.finstate(corp_name_or_code, year, reprt_code=reprt_code)
            except Exception:
                pass

            # 데이터가 없으면 전년도 시도 (예: 2025 -> 2024)
            if fs is None or (hasattr(fs, "empty") and fs.empty):
                for fallback_year in [year - 1, year - 2]:
                    try:
                        fs = dart.finstate(corp_name_or_code, fallback_year, reprt_code=reprt_code)
                        if fs is not None and not fs.empty:
                            year = fallback_year
                            break
                    except Exception:
                        pass

            if fs is None or (hasattr(fs, "empty") and fs.empty):
                return f"'{corp_name_or_code}'의 {year}년 재무제표 데이터를 가져올 수 없습니다. DART 공시 미제출 또는 미존재 상태일 수 있습니다."

            # 주요 항목 필터링 (특수기호 re.escape 처리로 정규식 경고 방지)
            key_accounts = ["매출액", "수익(매출액)", "영업수익", "영업이익", "영업이익(손실)", "당기순이익", "당기순이익(손실)", "자산총계", "부채총계", "자본총계"]
            escaped_pattern = '|'.join(re.escape(k) for k in key_accounts)
            filtered = fs[fs['account_nm'].str.contains(escaped_pattern, na=False, regex=True)]
            
            results = [f"[재무제표 주요 지표 ({corp_name_or_code}, 기준연도: {year}년)]"]
            seen_accounts = set()
            
            for _, row in filtered.iterrows():
                acc_name = row.get('account_nm', '').strip()
                if acc_name in seen_accounts:
                    continue
                seen_accounts.add(acc_name)
                
                thstrm_nm = row.get('thstrm_nm', f'당기({year})')
                thstrm_amount = row.get('thstrm_amount', '-')
                frmtrm_nm = row.get('frmtrm_nm', f'전기({year-1})')
                frmtrm_amount = row.get('frmtrm_amount', '-')
                bfefrmtrm_amount = row.get('bfefrmtrm_amount', '-')
                
                results.append(f"- {acc_name}: {thstrm_nm}={thstrm_amount}원 | {frmtrm_nm}={frmtrm_amount}원 | 전전기={bfefrmtrm_amount}원")

            if len(results) == 1:
                for _, row in fs.head(10).iterrows():
                    results.append(f"- {row.get('account_nm')}: {row.get('thstrm_amount')}원")

            return "\n".join(results)

        except Exception as e:
            return f"[DART 재무제표 조회 오류] {str(e)}"

@mcp.tool("get_recent_disclosures", description="기업의 최근 주요 공시 내역을 최신순으로 조회합니다. 최근 7일(1주일) 이내 공시를 우선 검증하며 신선도를 명시합니다.")
def get_recent_disclosures(corp_name_or_code: str, count: int = 5, days: int = 7) -> str:
    """
    기업의 최근 공시 목록을 조회합니다. 최근 7일(1주일) 이내 공시를 우선 필터링하며,
    최근 7일간 신규 공시가 없을 경우 직전 최근 공시와 함께 고지합니다.

    Args:
        corp_name_or_code: 회사명 또는 종목코드
        count: 조회할 공시 개수 (기본 5건, 최대 10건)
        days: 최근 기준 일수 (기본 7일)
    """
    corp_name_or_code = resolve_corp_name(corp_name_or_code)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            from datetime import datetime, timedelta
            dart = get_dart_client()
            count = min(max(1, count), 10)
            
            today = datetime.today()
            today_str = today.strftime('%Y-%m-%d')
            start_7d = (today - timedelta(days=days)).strftime('%Y-%m-%d')

            # 1. 최근 7일(1주일) 이내 신규 공시 우선 조회
            disc_7d = dart.list(corp_name_or_code, start=start_7d)
            if disc_7d is not None and not disc_7d.empty:
                items = disc_7d.head(count)
                results = [
                    f"[DART 최근 주요 공시 (최근 7일 신규 접수 | {corp_name_or_code}, 기간: {start_7d} ~ {today_str}, 총 {len(disc_7d)}건 중 {len(items)}건)]"
                ]
                for _, row in items.iterrows():
                    rcept_dt = str(row.get('rcept_dt', '-'))
                    # YYYYMMDD -> YYYY-MM-DD 포맷팅
                    formatted_dt = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}" if len(rcept_dt) == 8 else rcept_dt
                    report_nm = row.get('report_nm', '-')
                    flr_nm = row.get('flr_nm', '-')
                    rcept_no = row.get('rcept_no', '')
                    link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else ""
                    results.append(f"- [최근 7일 이내 | {formatted_dt}] {report_nm} (제출인: {flr_nm}) \n  링크: {link}")
                return "\n".join(results)

            # 2. 최근 7일 이내 신규 공시가 없는 경우: 직전 최근 공시 시점 명시
            start_fallback = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            disc_fallback = dart.list(corp_name_or_code, start=start_fallback)
            if disc_fallback is None or disc_fallback.empty:
                start_fallback = (today - timedelta(days=365)).strftime('%Y-%m-%d')
                disc_fallback = dart.list(corp_name_or_code, start=start_fallback)

            results = [
                f"[DART 공시 현황 ({corp_name_or_code})]",
                f"⚠️ 최근 7일(1주일, {start_7d} ~ {today_str}) 이내에 접수된 신규 DART 공시가 없습니다."
            ]
            if disc_fallback is not None and not disc_fallback.empty:
                last_row = disc_fallback.iloc[0]
                last_dt = str(last_row.get('rcept_dt', '-'))
                formatted_last_dt = f"{last_dt[:4]}-{last_dt[4:6]}-{last_dt[6:]}" if len(last_dt) == 8 else last_dt
                results.append(f"- 직전 최근 공시 접수일: {formatted_last_dt} | 보고서명: {last_row.get('report_nm', '-')}")
                results.append(f"  링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={last_row.get('rcept_no', '')}")
            else:
                results.append("- 최근 1년간 접수된 DART 주요 공시 내역이 없습니다.")
            return "\n".join(results)

        except Exception as e:
            return f"[DART 공시 목록 조회 오류] {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
