import os
import sys
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import html

import FinanceDataReader as fdr
import yfinance as yf
import concurrent.futures

try:
    from news_intelligence import (
        evaluate_and_rank_news,
        format_ranked_news_for_context,
        format_ranked_news_for_report
    )
except Exception:
    def evaluate_and_rank_news(corp_name: str, raw_articles: List[Dict[str, Any]], llm: Optional[Any] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        return raw_articles[:top_k]
    def format_ranked_news_for_context(ranked_news: List[Dict[str, Any]]) -> str:
        return "\n".join([f"- {a.get('title', '')}" for a in ranked_news])
    def format_ranked_news_for_report(ranked_news: List[Dict[str, Any]]) -> str:
        return "\n".join([f"- {a.get('title', '')}" for a in ranked_news])

# 상위 폴더 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    STOCK_ALIASES,
    normalize_ticker,
    DEFAULT_HTTP_TIMEOUT,
    THREAD_POOL_TIMEOUT,
    MAX_RAW_NEWS_COUNT,
    NEWS_RANKING_TOP_K,
    NAVER_USER_AGENT
)

# ============================================================
# 1. 종목명 정규화 및 티커 매핑 (Ticker Resolution)
# ============================================================

MAJOR_TICKER_MAP: Dict[str, Dict[str, str]] = {
    # 반도체 / IT
    "하닉": {"corp_name": "SK하이닉스", "stock_code": "000660", "yahoo_ticker": "000660.KS", "market": "KOSPI"},
    "SK하이닉스": {"corp_name": "SK하이닉스", "stock_code": "000660", "yahoo_ticker": "000660.KS", "market": "KOSPI"},
    "하이닉스": {"corp_name": "SK하이닉스", "stock_code": "000660", "yahoo_ticker": "000660.KS", "market": "KOSPI"},
    "000660": {"corp_name": "SK하이닉스", "stock_code": "000660", "yahoo_ticker": "000660.KS", "market": "KOSPI"},

    "삼전": {"corp_name": "삼성전자", "stock_code": "005930", "yahoo_ticker": "005930.KS", "market": "KOSPI"},
    "삼성전자": {"corp_name": "삼성전자", "stock_code": "005930", "yahoo_ticker": "005930.KS", "market": "KOSPI"},
    "삼성": {"corp_name": "삼성전자", "stock_code": "005930", "yahoo_ticker": "005930.KS", "market": "KOSPI"},
    "005930": {"corp_name": "삼성전자", "stock_code": "005930", "yahoo_ticker": "005930.KS", "market": "KOSPI"},

    "한미반도체": {"corp_name": "한미반도체", "stock_code": "042700", "yahoo_ticker": "042700.KS", "market": "KOSPI"},
    "한미": {"corp_name": "한미반도체", "stock_code": "042700", "yahoo_ticker": "042700.KS", "market": "KOSPI"},
    "042700": {"corp_name": "한미반도체", "stock_code": "042700", "yahoo_ticker": "042700.KS", "market": "KOSPI"},

    "네이버": {"corp_name": "NAVER", "stock_code": "035420", "yahoo_ticker": "035420.KS", "market": "KOSPI"},
    "NAVER": {"corp_name": "NAVER", "stock_code": "035420", "yahoo_ticker": "035420.KS", "market": "KOSPI"},
    "035420": {"corp_name": "NAVER", "stock_code": "035420", "yahoo_ticker": "035420.KS", "market": "KOSPI"},

    "카카오": {"corp_name": "카카오", "stock_code": "035720", "yahoo_ticker": "035720.KS", "market": "KOSPI"},
    "035720": {"corp_name": "카카오", "stock_code": "035720", "yahoo_ticker": "035720.KS", "market": "KOSPI"},
    "카뱅": {"corp_name": "카카오뱅크", "stock_code": "323410", "yahoo_ticker": "323410.KS", "market": "KOSPI"},
    "카페": {"corp_name": "카카오페이", "stock_code": "377300", "yahoo_ticker": "377300.KS", "market": "KOSPI"},

    # 2차전지
    "엔솔": {"corp_name": "LG에너지솔루션", "stock_code": "373220", "yahoo_ticker": "373220.KS", "market": "KOSPI"},
    "lg엔솔": {"corp_name": "LG에너지솔루션", "stock_code": "373220", "yahoo_ticker": "373220.KS", "market": "KOSPI"},
    "LG에너지솔루션": {"corp_name": "LG에너지솔루션", "stock_code": "373220", "yahoo_ticker": "373220.KS", "market": "KOSPI"},
    "373220": {"corp_name": "LG에너지솔루션", "stock_code": "373220", "yahoo_ticker": "373220.KS", "market": "KOSPI"},

    "포스코홀딩스": {"corp_name": "POSCO홀딩스", "stock_code": "005490", "yahoo_ticker": "005490.KS", "market": "KOSPI"},
    "포홀": {"corp_name": "POSCO홀딩스", "stock_code": "005490", "yahoo_ticker": "005490.KS", "market": "KOSPI"},
    "POSCO홀딩스": {"corp_name": "POSCO홀딩스", "stock_code": "005490", "yahoo_ticker": "005490.KS", "market": "KOSPI"},
    "005490": {"corp_name": "POSCO홀딩스", "stock_code": "005490", "yahoo_ticker": "005490.KS", "market": "KOSPI"},

    # 자동차 / 모빌리티
    "현차": {"corp_name": "현대차", "stock_code": "005380", "yahoo_ticker": "005380.KS", "market": "KOSPI"},
    "현대차": {"corp_name": "현대차", "stock_code": "005380", "yahoo_ticker": "005380.KS", "market": "KOSPI"},
    "005380": {"corp_name": "현대차", "stock_code": "005380", "yahoo_ticker": "005380.KS", "market": "KOSPI"},

    "기아": {"corp_name": "기아", "stock_code": "000270", "yahoo_ticker": "000270.KS", "market": "KOSPI"},
    "000270": {"corp_name": "기아", "stock_code": "000270", "yahoo_ticker": "000270.KS", "market": "KOSPI"},

    # 바이오
    "삼바": {"corp_name": "삼성바이오로직스", "stock_code": "207940", "yahoo_ticker": "207940.KS", "market": "KOSPI"},
    "삼성바이오로직스": {"corp_name": "삼성바이오로직스", "stock_code": "207940", "yahoo_ticker": "207940.KS", "market": "KOSPI"},
    "207940": {"corp_name": "삼성바이오로직스", "stock_code": "207940", "yahoo_ticker": "207940.KS", "market": "KOSPI"},

    "셀트": {"corp_name": "셀트리온", "stock_code": "068270", "yahoo_ticker": "068270.KS", "market": "KOSPI"},
    "셀트리온": {"corp_name": "셀트리온", "stock_code": "068270", "yahoo_ticker": "068270.KS", "market": "KOSPI"},
    "068270": {"corp_name": "셀트리온", "stock_code": "068270", "yahoo_ticker": "068270.KS", "market": "KOSPI"},

    "알테": {"corp_name": "알테오젠", "stock_code": "196170", "yahoo_ticker": "196170.KQ", "market": "KOSDAQ"},
    "알테오젠": {"corp_name": "알테오젠", "stock_code": "196170", "yahoo_ticker": "196170.KQ", "market": "KOSDAQ"},
    "196170": {"corp_name": "알테오젠", "stock_code": "196170", "yahoo_ticker": "196170.KQ", "market": "KOSDAQ"},
}


def _detect_market_and_suffix(stock_code: str) -> Tuple[str, str]:
    """네이버 금융 기본 API를 통해 KOSPI / KOSDAQ 시장 구분 및 야후 티커 접미사(.KS / .KQ) 판별"""
    if not stock_code or not stock_code.isdigit():
        return "KOSPI", ".KS"
    try:
        url = f"https://m.stock.naver.com/api/stock/{stock_code}/basic"
        req = urllib.request.Request(url, headers={"User-Agent": NAVER_USER_AGENT})
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sosok = data.get("stockExchangeType", {}).get("name", "KOSPI").upper()
            if "KOSDAQ" in sosok:
                return "KOSDAQ", ".KQ"
            return "KOSPI", ".KS"
    except Exception:
        return "KOSPI", ".KS"


def resolve_stock_info(query: str) -> Dict[str, str]:
    """
    사용자 입력(은어/약칭/종목명/종목코드)을 분석하여 표준 기업명, 6자리 종목코드, 야후 티커를 반환합니다.
    """
    raw_q = str(query or "").strip()
    if not raw_q:
        return {"corp_name": "SK하이닉스", "stock_code": "000660", "yahoo_ticker": "000660.KS", "market": "KOSPI"}

    clean_q = raw_q
    # 불필요한 특수문자 및 조사/어미/불용어 필터링
    clean_q_no_symbols = re.sub(r"[^\w\s]", " ", clean_q)
    stopwords = ["투자", "심의", "분석", "해줘", "보고서", "어때", "주식", "종목", "전망", "목표가", "살까", "팔까", "알려줘", "추천"]
    words = clean_q_no_symbols.split()
    filtered_words = []
    for w in words:
        # 한국어 조사 분리 제거 (예: 하닉은 -> 하닉, 삼전의 -> 삼전)
        w_stem = re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|로|과|와)$", "", w)
        if w_stem and not any(sw in w_stem for sw in stopwords):
            filtered_words.append(w_stem)
    candidate_q = filtered_words[0] if filtered_words else clean_q

    # 1. 직접 매핑 테이블 확인
    for q_try in [candidate_q, clean_q]:
        if q_try in MAJOR_TICKER_MAP:
            return MAJOR_TICKER_MAP[q_try]
        norm = normalize_ticker(q_try)
        if norm in MAJOR_TICKER_MAP:
            return MAJOR_TICKER_MAP[norm]

    # 2. 문장 내 부분 일치 확인
    sorted_aliases = sorted(MAJOR_TICKER_MAP.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        if len(alias) >= 2 and alias in clean_q:
            return MAJOR_TICKER_MAP[alias]

    # 3. 6자리 종목코드인 경우
    digits_match = re.search(r"\b(\d{6})\b", clean_q)
    target_code = digits_match.group(1) if digits_match else (clean_q if (clean_q.isdigit() and len(clean_q) == 6) else None)
    if target_code:
        market, suffix = _detect_market_and_suffix(target_code)
        corp_name = target_code
        try:
            from mcp_server.dart_server import get_dart_client
            dart = get_dart_client()
            info = dart.company(target_code)
            if info and isinstance(info, dict):
                corp_name = info.get("corp_name", target_code)
                corp_cls = info.get("corp_cls", "Y")
                if corp_cls == "K":
                    market = "KOSDAQ"
                    suffix = ".KQ"
        except Exception:
            pass
        return {
            "corp_name": corp_name,
            "stock_code": target_code,
            "yahoo_ticker": f"{target_code}{suffix}",
            "market": market
        }

    # 4. DART 전체 상장사 목록 매칭 (3,996개 상장법인 탐색)
    normalized_name = normalize_ticker(candidate_q)
    try:
        from mcp_server.dart_server import get_dart_client
        dart = get_dart_client()
        if hasattr(dart, "corp_codes") and dart.corp_codes is not None:
            df = dart.corp_codes[dart.corp_codes['stock_code'].str.len() == 6]
            for term in [normalized_name, candidate_q, clean_q]:
                if not term or len(term) < 2:
                    continue
                exact = df[df['corp_name'].str.lower() == term.lower()]
                if not exact.empty:
                    r = exact.iloc[0]
                    code = str(r['stock_code'])
                    market, suffix = _detect_market_and_suffix(code)
                    return {
                        "corp_name": str(r['corp_name']),
                        "stock_code": code,
                        "yahoo_ticker": f"{code}{suffix}",
                        "market": market
                    }
                match = df[df['corp_name'].str.contains(term, regex=False)]
                if not match.empty:
                    r = match.iloc[0]
                    code = str(r['stock_code'])
                    market, suffix = _detect_market_and_suffix(code)
                    return {
                        "corp_name": str(r['corp_name']),
                        "stock_code": code,
                        "yahoo_ticker": f"{code}{suffix}",
                        "market": market
                    }
    except Exception:
        pass

    # 5. 미국 티커인 경우 (영문 대문자 처리)
    if re.match(r"^[A-Za-z]+$", candidate_q):
        sym = candidate_q.upper()
        return {
            "corp_name": sym,
            "stock_code": sym,
            "yahoo_ticker": sym,
            "market": "US"
        }

    # 6. 안전한 기본 Fallback (임의 종목 강제 할당 제거 및 미확인 처리)
    return {
        "corp_name": candidate_q or clean_q,
        "stock_code": "",
        "yahoo_ticker": candidate_q or clean_q,
        "market": "UNKNOWN"
    }


# ============================================================
# 2. 시세 및 밸류에이션 데이터 수집 (FinanceDataReader + Naver API Fallback)
# ============================================================

def _fetch_naver_stock_data(stock_code: str) -> Dict[str, Any]:
    if not stock_code or not stock_code.isdigit():
        return {
            "now_price": "-",
            "fluc_rate": "-",
            "diff_price": "-",
            "metrics": {},
            "consensus": {},
            "deal_trend": []
        }
    headers = {"User-Agent": NAVER_USER_AGENT}
    # 실시간 시세
    basic_url = f"https://m.stock.naver.com/api/stock/{stock_code}/basic"
    now_price = "-"
    fluc_rate = "-"
    diff_price = "-"
    try:
        req = urllib.request.Request(basic_url, headers=headers)
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
            b_data = json.loads(resp.read().decode("utf-8"))
            now_price = b_data.get("closePrice", "-")
            fluc_rate = b_data.get("fluctuationsRatio", "-")
            diff_price = b_data.get("compareToPreviousClosePrice", "-")
    except Exception:
        pass

    # 통합 지표
    integ_url = f"https://m.stock.naver.com/api/stock/{stock_code}/integration"
    total_infos = []
    consensus_info = {}
    deal_trend = []
    try:
        req = urllib.request.Request(integ_url, headers=headers)
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
            i_data = json.loads(resp.read().decode("utf-8"))
            total_infos = i_data.get("totalInfos", [])
            consensus_info = i_data.get("consensusInfo", {})
            deal_trend = i_data.get("dealTrendInfos", [])
    except Exception:
        pass

    metrics = {item.get("code"): item.get("value") for item in total_infos}
    return {
        "now_price": now_price,
        "fluc_rate": fluc_rate,
        "diff_price": diff_price,
        "metrics": metrics,
        "consensus": consensus_info,
        "deal_trend": deal_trend
    }


def fetch_market_and_valuation(stock_info: Dict[str, str]) -> str:
    corp_name = stock_info["corp_name"]
    code = stock_info["stock_code"]
    yahoo_sym = stock_info["yahoo_ticker"]

    if not code or not code.isdigit():
        return f"[{corp_name}] 유효한 6자리 국내 종목코드가 없어 시세 조회를 생략합니다."

    # 1. FinanceDataReader를 통한 최근 7영업일 OHLCV 수집
    fdr_lines = []
    try:
        from datetime import datetime, timedelta
        end_date = datetime.today().strftime("%Y-%m-%d")
        start_date = (datetime.today() - timedelta(days=20)).strftime("%Y-%m-%d")
        df = fdr.DataReader(code, start=start_date, end=end_date)
        if df is not None and not df.empty:
            df_recent = df.tail(7)
            fdr_lines.append("[최근 7영업일 실시간 주가 흐름 및 거래량 추이]")
            for dt, row in df_recent.iterrows():
                dt_str = dt.strftime("%Y-%m-%d")
                close_p = int(row.get("Close", 0))
                change_pct = row.get("Change", 0) * 100
                vol = int(row.get("Volume", 0))
                fdr_lines.append(
                    f"  * [{dt_str}] 종가: {close_p:,.0f}원 ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%) | 거래량: {vol:,.0f}주"
                )
    except Exception as e:
        sys.stderr.write(f"[Warning] FDR DataReader error: {e}\n")

    # 2. 네이버 모바일 증권 통합 API (실시간 시세, 52주 고저, PER/PBR, 외국인/기관 수급)
    naver_lines = []
    try:
        n_data = _fetch_naver_stock_data(code)
        metrics = n_data["metrics"]
        consensus_info = n_data["consensus"]
        deal_trend = n_data["deal_trend"]

        cur_price = n_data["now_price"]
        fluc_rate = n_data["fluc_rate"]
        high52 = metrics.get("highPriceOf52Weeks", "-")
        low52 = metrics.get("lowPriceOf52Weeks", "-")
        per = metrics.get("per", "-")
        cns_per = metrics.get("cnsPer", "-")
        pbr = metrics.get("pbr", "-")
        bps = metrics.get("bps", "-")
        target_price = consensus_info.get("priceTargetMean", "-")
        invest_opinion = consensus_info.get("opinionMean", "-")

        naver_lines.append(f"[실시간 시장 시세 및 밸류에이션 종합 ({corp_name} / {code} / {yahoo_sym})]")
        naver_lines.append(f"- 현재가: {cur_price}원 (전일비 등락: {fluc_rate}%)")
        naver_lines.append(f"- 시가총액: {metrics.get('marketValue', '-')}")
        naver_lines.append(f"- 52주 변동폭: {low52} ~ {high52}원")
        naver_lines.append(f"- 증권사 컨센서스 목표주가: {target_price}원 (투자의견: {invest_opinion})")
        naver_lines.append(f"\n[핵심 밸류에이션 지표]")
        naver_lines.append(f"- PER: {per} (선행/추정 PER: {cns_per})")
        naver_lines.append(f"- PBR: {pbr} (BPS: {bps})")
        naver_lines.append(f"- 외국인 지분율(소진율): {metrics.get('foreignRate', '-')}")

        if deal_trend:
            naver_lines.append(f"\n[최근 수급 동향 (외국인 및 기관 순매수)]")
            for t in deal_trend[:5]:
                dt = t.get("bizdate", "")
                close_p = t.get("closePrice", "")
                def _safe_int(v):
                    try:
                        return int(float(str(v).replace(",", "")))
                    except Exception:
                        return 0
                frg_net = _safe_int(t.get("foreignerPureBuyQuant", 0))
                org_net = _safe_int(t.get("organPureBuyQuant", 0))
                naver_lines.append(
                    f"  * [{dt}] 종가 {close_p}원 | 외인 순매수: {'+' if frg_net > 0 else ''}{frg_net:,.0f}주 | 기관 순매수: {'+' if org_net > 0 else ''}{org_net:,.0f}주"
                )
    except Exception as e:
        sys.stderr.write(f"[Warning] Naver Stock API error: {e}\n")

    combined = []
    if naver_lines:
        combined.extend(naver_lines)
    if fdr_lines:
        combined.append("")
        combined.extend(fdr_lines)

    if not combined:
        return f"[{corp_name}] 실시간 시세 및 밸류에이션 조회 완료 (기본 시장 데이터 연동)"
    return "\n".join(combined)


# ============================================================
# 3. 최신 분기 실적 및 연간 컨센서스 데이터 수집
# ============================================================

def fetch_quarterly_financials_and_consensus(stock_info: Dict[str, str]) -> str:
    code = stock_info.get("stock_code", "")
    corp_name = stock_info.get("corp_name", "")

    if not code or not code.isdigit():
        return f"[{corp_name}] 유효한 6자리 국내 종목코드가 없어 분기 실적 조회를 생략합니다."

    url = f"https://m.stock.naver.com/api/stock/{code}/finance/quarter"
    headers = {"User-Agent": NAVER_USER_AGENT}
    result_lines = []
    fin_json_dict = None

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        finance_info = data.get("financeInfo", {})
        tr_titles = finance_info.get("trTitleList", []) or finance_info.get("titleList", [])
        row_list = finance_info.get("rowList", [])

        if tr_titles and row_list:
            result_lines.append(f"[최근 분기별 실적 추이 (QoQ / YoY) - {corp_name}]")
            keys = [t.get("key", "") for t in tr_titles if isinstance(t, dict)]
            
            # 확정 공시 분기와 미발표 컨센서스(E) 분기 엄격 구분
            quarter_labels = []
            for t in tr_titles:
                if isinstance(t, dict):
                    q_title = t.get("title", "").strip().rstrip(".")
                    if t.get("isConsensus") == "Y" or "(E)" in q_title:
                        quarter_labels.append(f"{q_title}(E - 미발표 전망치)")
                    else:
                        quarter_labels.append(q_title)
            
            result_lines.append(f"분기: {' | '.join(quarter_labels)}")

            row_map = {}
            for row in row_list:
                item_name = row.get("title", "")
                cols = row.get("columns", {})
                if cols and isinstance(cols, dict):
                    vals = [cols.get(k, {}).get("value", "-") for k in keys]
                else:
                    vals = [c.get("value", "-") for c in row.get("columnList", [])]
                row_map[item_name] = vals
                if any(k in item_name for k in ["매출액", "영업이익", "당기순이익", "영업이익률"]):
                    result_lines.append(f"- {item_name}: {' | '.join(vals)} (억 원)")

            # 미발표 분기 보고서 관련 할루시네이션 방지 가이드라인 명시
            has_consensus_q = any(t.get("isConsensus") == "Y" for t in tr_titles if isinstance(t, dict))
            if has_consensus_q:
                result_lines.append("※ [필수 주의]: (E)가 표기된 분기(예: 9월 분기 등)는 아직 기업의 공식 분기보고서가 발표되지 않은 '시장 컨센서스 추정치'입니다. 확정 실적으로 오인하여 분석하지 마시고, 공식 공시된 직전 분기까지를 실제 확정 실적으로 다루세요.")

            # 분기별 시각화 JSON 데이터 생성: 공식 발표된 확정 분기만 추출 (미발표 추정치는 그래프에서 배제하여 할루시네이션 원천 차단)
            actual_indices = [
                idx for idx, t in enumerate(tr_titles)
                if isinstance(t, dict) and t.get("isConsensus") != "Y" and "(E)" not in t.get("title", "")
            ]
            if not actual_indices:
                actual_indices = list(range(len(tr_titles)))

            def parse_actual_num_list(kword):
                for k, v in row_map.items():
                    if kword in k:
                        res = []
                        for idx in actual_indices:
                            x = v[idx] if idx < len(v) else 0
                            try:
                                res.append(int(float(str(x).replace(",", ""))))
                            except Exception:
                                res.append(0)
                        return res
                return []

            actual_quarters = [tr_titles[i].get("title", "").strip().rstrip(".") for i in actual_indices]
            clean_q_labels = [q.replace(".", "/").strip("/") for q in actual_quarters]
            rev_nums = parse_actual_num_list("매출")
            op_nums = parse_actual_num_list("영업이익")
            np_nums = parse_actual_num_list("당기순")

            if clean_q_labels and rev_nums:
                fin_json_dict = {
                    "corp_name": corp_name,
                    "period_type": "quarterly",
                    "periods": clean_q_labels,
                    "years": clean_q_labels,
                    "revenue": rev_nums,
                    "operating_profit": op_nums,
                    "net_profit": np_nums,
                    "unit": "억원"
                }
                stock_info["fin_json"] = json.dumps(fin_json_dict, ensure_ascii=False)

    except Exception as e:
        sys.stderr.write(f"[Warning] Naver Finance quarter API error: {e}\n")

    # 연간 컨센서스 추정치 수집 (annual)
    annual_url = f"https://m.stock.naver.com/api/stock/{code}/finance/annual"
    try:
        req = urllib.request.Request(annual_url, headers=headers)
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
            ann_data = json.loads(resp.read().decode("utf-8"))

        a_info = ann_data.get("financeInfo", {})
        a_titles = a_info.get("trTitleList", []) or a_info.get("titleList", [])
        a_rows = a_info.get("rowList", [])

        if a_titles and a_rows:
            result_lines.append(f"\n[연간 실적 및 컨센서스 추정치(E) - {corp_name}]")
            a_keys = [t.get("key", "") for t in a_titles if isinstance(t, dict)]
            years = [t.get("title", "") for t in a_titles if isinstance(t, dict)]
            result_lines.append(f"사업연도: {' | '.join(years)}")
            for row in a_rows:
                item_name = row.get("title", "")
                cols = row.get("columns", {})
                if cols and isinstance(cols, dict):
                    vals = [cols.get(k, {}).get("value", "-") for k in a_keys]
                else:
                    vals = [c.get("value", "-") for c in row.get("columnList", [])]
                if any(k in item_name for k in ["매출액", "영업이익", "당기순이익"]):
                    result_lines.append(f"- {item_name}: {' | '.join(vals)} (억 원)")
    except Exception as e:
        sys.stderr.write(f"[Warning] Naver Finance annual API error: {e}\n")

    return "\n".join(result_lines) if result_lines else f"[{corp_name}] 최근 분기 실적 및 컨센서스 데이터 연동"


# ============================================================
# 4. 광범위 뉴스 원천 수집 및 뉴스 인텔리전스 (News Intelligence) 연동
# ============================================================

def fetch_raw_news_pool(corp_name: str, stock_code: str) -> List[Dict[str, Any]]:
    """
    네이버 증권 API, 구글 뉴스 RSS(다각도 검색어), Yahoo Finance에서
    종목 관련 최근 뉴스를 최소 25~40건 이상 넓게 수집하여 중복을 제거하고 반환합니다.
    """
    raw_articles: List[Dict[str, Any]] = []
    seen_titles = set()

    def _clean_title_key(t: str) -> str:
        return re.sub(r"[^가-힣a-zA-Z0-9]", "", t)[:20]

    def _add_article(item: Dict[str, Any]):
        t = item.get("title", "").strip()
        norm_k = _clean_title_key(t)
        if norm_k and norm_k not in seen_titles:
            seen_titles.add(norm_k)
            raw_articles.append(item)

    # 1. 네이버 모바일 증권 종목 뉴스 API (최대 30건, 본문 요약 포함)
    clean_code = stock_code.strip() if stock_code else ""
    if re.match(r"^\d{6}$", clean_code):
        try:
            naver_url = f"https://m.stock.naver.com/api/news/stock/{clean_code}?pageSize=30&page=1"
            headers = {"User-Agent": NAVER_USER_AGENT}
            req = urllib.request.Request(naver_url, headers=headers)
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for group in data:
                for it in group.get("items", []):
                    title = it.get("title") or it.get("titleFull") or ""
                    snippet = it.get("body", "")
                    office = it.get("officeName", "네이버증권")
                    dt = it.get("datetime", "")
                    link = it.get("mobileNewsUrl", "")
                    _add_article({
                        "title": title,
                        "snippet": snippet,
                        "provider": office,
                        "pubDate": dt,
                        "link": link
                    })
        except Exception as e:
            sys.stderr.write(f"[Warning] Naver stock news API error: {e}\n")

    # 2. 구글 뉴스 RSS 다각도 검색 (수주/계약, 자회사/신사업, 주가 변동성, 실적 등)
    rss_queries = [
        f"{corp_name}",
        f"{corp_name} 실적 수주 계약",
        f"{corp_name} 자회사 사업 신제품",
        f"{corp_name} 주가 급락 리스크",
        f"{corp_name} 공시 투자 증설"
    ]

    def _fetch_rss_query(query: str) -> List[Dict[str, str]]:
        q_results = []
        try:
            encoded_q = urllib.parse.quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
            headers = {"User-Agent": NAVER_USER_AGENT}
            req = urllib.request.Request(rss_url, headers=headers)
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for it in root.findall(".//item")[:8]:
                title = it.findtext("title", "")
                raw_desc = it.findtext("description", "")
                unescaped = html.unescape(raw_desc)
                clean_snippet = re.sub(r"<[^>]+>", " ", unescaped).strip()
                clean_snippet = " ".join(clean_snippet.split())
                source_elem = it.find("source")
                provider = source_elem.text if source_elem is not None else "언론사"
                pub_date = it.findtext("pubDate", "")
                link = it.findtext("link", "")
                q_results.append({
                    "title": title,
                    "snippet": clean_snippet,
                    "provider": provider,
                    "pubDate": pub_date[:16],
                    "link": link
                })
        except Exception:
            pass
        return q_results

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_fetch_rss_query, q) for q in rss_queries]
        try:
            for f in concurrent.futures.as_completed(futures, timeout=THREAD_POOL_TIMEOUT):
                try:
                    for it in f.result():
                        _add_article(it)
                except Exception:
                    pass
        except Exception as e:
            sys.stderr.write(f"[Warning] RSS news aggregation timeout or error: {e}\n")

    # 3. Yahoo Finance 글로벌 뉴스
    try:
        from mcp_server.yahoo_server import resolve_yahoo_ticker
        sym = resolve_yahoo_ticker(stock_code or corp_name)
        ticker_obj = yf.Ticker(sym)
        yf_news = getattr(ticker_obj, "news", []) or []
        for item in yf_news[:5]:
            content = item.get("content", item)
            title = content.get("title") or item.get("title", "")
            pub_date = content.get("pubDate") or item.get("displayTime") or str(item.get("providerPublishTime", "-"))[:16]
            provider = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else item.get("publisher", "Yahoo Finance")
            link = content.get("canonicalUrl", {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", "")
            summary = content.get("summary", "") or item.get("summary", "")
            _add_article({
                "title": title,
                "snippet": summary,
                "provider": provider,
                "pubDate": pub_date,
                "link": link
            })
    except Exception:
        pass

    return raw_articles[:MAX_RAW_NEWS_COUNT]


def fetch_industry_and_stock_news(corp_name: str, stock_code: str, llm: Optional[Any] = None) -> str:
    """
    20~30건 이상의 원천 뉴스를 수집한 후, 뉴스 인텔리전스 노드를 통해
    주가/펀더멘털 파급력 Top 3~5개를 선별하고 마크다운 포맷으로 변환합니다.
    """
    raw_articles = fetch_raw_news_pool(corp_name, stock_code)

    # 뉴스 인텔리전스(Filter & Rank) 노드 호출
    ranked_news = evaluate_and_rank_news(
        corp_name=corp_name,
        raw_articles=raw_articles,
        llm=llm,
        top_k=NEWS_RANKING_TOP_K
    )

    # 콘솔에 선별된 Top 3~5개 뉴스 출력 (평가 및 디버깅용)
    print("\n" + "=" * 64)
    print(f"🔥 [{corp_name}] 뉴스 인텔리전스(News Intelligence) 영향도 Top {len(ranked_news)} 선별 결과 (총 {len(raw_articles)}건 수집 중)")
    print("=" * 64)
    for idx, item in enumerate(ranked_news, 1):
        icon = "🟢 Catalyst" if item["category"] == "Catalyst" else "🔴 Risk"
        print(f" {idx}. [{icon}] 영향도: {item['impact_score']}/10 | {item['provider']}")
        print(f"    - 제목: {item['title']}")
        print(f"    - 핵심 영향: {item['core_reason']}")
        if item.get("link"):
            print(f"    - 링크: {item['link']}")
    print("=" * 64 + "\n")

    # 1. 뉴스 인텔리전스 Top 선별 뉴스 포맷팅
    ranked_markdown = format_ranked_news_for_context(ranked_news, total_count=len(raw_articles))

    # 2. 보조: 최근 주요 헤드라인 (단순 참조용 상위 5건)
    headline_lines = ["\n### 📰 최근 주요 언론 보도 헤드라인 요약"]
    for idx, a in enumerate(raw_articles[:5], 1):
        headline_lines.append(f"{idx}. **[{a.get('provider', '언론사')}]** {a.get('title', '')}")

    return f"{ranked_markdown}\n" + "\n".join(headline_lines)


# ============================================================
# 5. 전체 종합 컨텍스트 데이터 빌더
# ============================================================

def build_comprehensive_context(raw_input: str, llm: Optional[Any] = None) -> Tuple[Dict[str, str], str]:
    stock_info = resolve_stock_info(raw_input)
    corp_name = stock_info["corp_name"]
    code = stock_info["stock_code"]

    today_str = datetime.today().strftime("%Y-%m-%d %H:%M")
    week_ago_str = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    overview_text = ""
    fs_text = ""
    disc_text = ""
    market_text = ""
    quarterly_text = ""
    news_text = ""

    from mcp_server.dart_server import (
        get_company_overview,
        get_financial_statements,
        get_recent_disclosures
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_overview = executor.submit(get_company_overview, corp_name)
        f_fs = executor.submit(get_financial_statements, corp_name, 2025)
        f_disc = executor.submit(get_recent_disclosures, corp_name, 5, 7)
        f_market = executor.submit(fetch_market_and_valuation, stock_info)
        f_quarterly = executor.submit(fetch_quarterly_financials_and_consensus, stock_info)
        f_news = executor.submit(fetch_industry_and_stock_news, corp_name, code, llm)

        task_timeout = DEFAULT_HTTP_TIMEOUT * 2
        try:
            overview_text = f_overview.result(timeout=task_timeout)
        except Exception as e:
            overview_text = f"[{corp_name}] 개요 조회 지연: {e}"

        try:
            fs_text = f_fs.result(timeout=task_timeout)
        except Exception as e:
            fs_text = f"[{corp_name}] 재무제표 조회 지연: {e}"

        try:
            disc_text = f_disc.result(timeout=task_timeout)
        except Exception as e:
            disc_text = f"[{corp_name}] 최근 공시 조회 지연: {e}"

        try:
            market_text = f_market.result(timeout=task_timeout)
        except Exception as e:
            market_text = f"[{corp_name}] 시세 조회 지연: {e}"

        try:
            quarterly_text = f_quarterly.result(timeout=task_timeout)
        except Exception as e:
            quarterly_text = f"[{corp_name}] 분기 실적 조회 지연: {e}"

        try:
            news_text = f_news.result(timeout=THREAD_POOL_TIMEOUT)
        except Exception as e:
            news_text = f"[{corp_name}] 실시간 뉴스 수집 지연: {e}"

    stock_info["market_news"] = news_text

    context_data = f"""[분석 기준 시점 및 데이터 유효 범위]
- 데이터 수집 시점: {today_str}
- 실시간 시세 및 초단기 모멘텀 기준: 최근 7영업일 ({week_ago_str} ~ {today_str[:10]})
- 기업 식별 정보: 정식 사명 [{corp_name}], 6자리 종목코드 [{code}], 야후 티커 [{stock_info['yahoo_ticker']}]

[기업 개요 및 기본 정보 (DART)]
{overview_text}

[시장 시세 및 스냅샷 (Yahoo Finance)]
{market_text}

[최근 분기별 실적 추이(QoQ/YoY) 및 연간 컨센서스 추정치]
{quarterly_text}

[DART 공시 재무제표 (최근 3개년 회계감사 결산 팩트)]
{fs_text}

[최근 주요 공시 내역 (DART - 최근 7일 우선 검증)]
{disc_text}

[최근 주요 시장 뉴스 및 센티먼트 요약 (Yahoo Finance)]
{news_text}
"""
    return stock_info, context_data
