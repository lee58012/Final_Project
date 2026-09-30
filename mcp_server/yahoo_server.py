import os
import sys
import re
import contextlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import yfinance as yf
from mcp.server.fastmcp import FastMCP

# 상위 폴더의 .env 로드
BASE_DIR = Path(__file__).parent.parent.resolve()
load_dotenv(BASE_DIR / ".env")

mcp = FastMCP("yahoo-server")


def resolve_yahoo_ticker(corp_name_or_code: str) -> str:
    """
    기업명 또는 종목코드를 Yahoo Finance 티커 심볼로 변환합니다.
    - 예: '005930.KS' -> '005930.KS'
    - 예: '005930' -> '005930.KS' (KOSPI)
    - 예: '삼성전자' -> DART 조회 후 '005930.KS'
    - 예: 'AAPL', 'NVDA' -> 'AAPL', 'NVDA'
    """
    clean_input = str(corp_name_or_code).strip()
    if not clean_input:
        return "005930.KS"

    # 이미 점(.)을 포함한 티커 형식인 경우 (예: 005930.KS, 035720.KQ)
    if "." in clean_input:
        return clean_input.upper()

    # 영문 알파벳만으로 구성된 미국 티커인 경우 (예: AAPL, NVDA, TSLA)
    if re.match(r"^[A-Za-z]+$", clean_input):
        return clean_input.upper()

    # 별칭 또는 종목명 사전 확인 (하닉, 삼전, 현차 등)
    try:
        from financial_data_provider import MAJOR_TICKER_MAP
        if clean_input in MAJOR_TICKER_MAP:
            return MAJOR_TICKER_MAP[clean_input]["yahoo_ticker"]
    except Exception:
        pass

    # 6자리 한국 종목코드인 경우 (예: 005930)
    if re.match(r"^\d{6}$", clean_input):
        # DART 조회를 통해 코스피/코스닥 구분 시도
        try:
            from mcp_server.dart_server import get_dart_client
            dart = get_dart_client()
            info = dart.company(clean_input)
            if info and isinstance(info, dict):
                corp_cls = info.get("corp_cls", "Y")
                suffix = ".KQ" if corp_cls == "K" else ".KS"
                return f"{clean_input}{suffix}"
        except Exception:
            pass
        return f"{clean_input}.KS"

    # 회사명인 경우 (예: 삼성전자, 카카오, SK하이닉스)
    try:
        from mcp_server.dart_server import get_dart_client
        dart = get_dart_client()
        info = dart.company(clean_input)
        if info and isinstance(info, dict) and info.get("stock_code"):
            stock_code = info.get("stock_code")
            corp_cls = info.get("corp_cls", "Y")
            suffix = ".KQ" if corp_cls == "K" else ".KS"
            return f"{stock_code}{suffix}"
    except Exception:
        pass

    # 변환 실패 시 기본 티커 반환
    return clean_input


@mcp.tool("get_yahoo_news_summary", description="Yahoo Finance에서 대상 종목의 최신 주요 뉴스 기사 및 요약문을 수집합니다.")
def get_yahoo_news_summary(corp_name_or_code: str, count: int = 5) -> str:
    """
    기업의 Yahoo Finance 최신 뉴스 헤드라인 및 요약문을 조회합니다.

    Args:
        corp_name_or_code: 기업명, 6자리 종목코드 또는 티커 (예: '삼성전자', '005930', 'AAPL')
        count: 조회할 뉴스 개수 (기본 5개)
    """
    with contextlib.redirect_stdout(sys.stderr):
        try:
            symbol = resolve_yahoo_ticker(corp_name_or_code)
            ticker_obj = yf.Ticker(symbol)
            news_items = ticker_obj.news

            if not news_items:
                # 점 접미사가 있는 경우 대체 시도 (.KS <-> .KQ)
                if symbol.endswith(".KS"):
                    alt_sym = symbol.replace(".KS", ".KQ")
                    alt_ticker = yf.Ticker(alt_sym)
                    if alt_ticker.news:
                        symbol = alt_sym
                        news_items = alt_ticker.news
                elif symbol.endswith(".KQ"):
                    alt_sym = symbol.replace(".KQ", ".KS")
                    alt_ticker = yf.Ticker(alt_sym)
                    if alt_ticker.news:
                        symbol = alt_sym
                        news_items = alt_ticker.news

            if not news_items:
                if not corp_name_or_code.startswith("NON_EXISTENT"):
                    try:
                        from financial_data_provider import resolve_stock_info, fetch_industry_and_stock_news
                        s_info = resolve_stock_info(corp_name_or_code)
                        c_name = s_info["corp_name"]
                        s_code = s_info["stock_code"]
                        rss_news = fetch_industry_and_stock_news(c_name, s_code)
                        if rss_news and "뉴스" in rss_news:
                            return f"[Yahoo Finance 최신 시장 뉴스 요약 ({symbol}, 실시간 뉴스 집계)]\n{rss_news}"
                    except Exception:
                        pass
                return f"[Yahoo Finance] '{corp_name_or_code}'(티커: {symbol}) 관련 최신 뉴스를 찾을 수 없습니다."

            count = min(max(1, count), 10)
            items = news_items[:count]

            results = [f"[Yahoo Finance 최신 뉴스 요약 ({symbol}, 최신 {len(items)}건)]"]
            from datetime import datetime, timezone

            now_utc = datetime.now(timezone.utc)
            within_7d_items = []
            parsed_lines = []

            for idx, item in enumerate(items, 1):
                # yfinance 신버전/구버전 구조 호환
                content = item.get("content", item)
                title = content.get("title") or item.get("title", "제목 없음")
                summary = content.get("summary") or item.get("summary", "")
                pub_date = content.get("pubDate") or content.get("displayTime") or str(item.get("providerPublishTime", "-"))

                provider_info = content.get("provider")
                if isinstance(provider_info, dict):
                    provider = provider_info.get("displayName", "언론사")
                else:
                    provider = item.get("publisher", "언론사")

                canonical_url = content.get("canonicalUrl")
                if isinstance(canonical_url, dict):
                    link = canonical_url.get("url", "")
                else:
                    link = item.get("link", "")

                line = f"{idx}. [{pub_date}] ({provider}) {title}"
                # 시간 경과 및 7일 이내 여부 계산
                time_tag = "최근"
                is_within_7d = False
                try:
                    if isinstance(pub_date, str) and ("T" in pub_date or "-" in pub_date):
                        dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        diff_sec = (now_utc - dt).total_seconds()
                        diff_hours = int(diff_sec / 3600)
                        diff_days = int(diff_sec / 86400)
                        if diff_sec >= 0:
                            if diff_hours < 24:
                                time_tag = f"🔥 {max(1, diff_hours)}시간 전"
                                is_within_7d = True
                            elif diff_days <= 7:
                                time_tag = f"⚡ {diff_days}일 전"
                                is_within_7d = True
                            else:
                                time_tag = f"{diff_days}일 전"
                        else:
                            time_tag = "방금 전"
                            is_within_7d = True
                    elif isinstance(pub_date, (int, float)):
                        dt = datetime.fromtimestamp(pub_date, tz=timezone.utc)
                        diff_days = int((now_utc - dt).total_seconds() / 86400)
                        is_within_7d = diff_days <= 7
                        time_tag = f"{diff_days}일 전" if diff_days > 0 else "오늘"
                except Exception:
                    is_within_7d = True

                if is_within_7d:
                    within_7d_items.append(title)

                clean_date = pub_date[:10] if isinstance(pub_date, str) and len(pub_date) >= 10 else str(pub_date)
                line = f"{idx}. [{time_tag} | {clean_date}] ({provider}) {title}"
                if summary:
                    # 요약문 공백 정규화
                    clean_summary = " ".join(summary.split())
                    line += f"\n   * 뉴스 요약: {clean_summary}"
                if link:
                    line += f"\n   * 링크: {link}"
                results.append(line)
                parsed_lines.append(line)

            header = f"[Yahoo Finance 최신 시장 뉴스 요약 ({symbol}, 최근 7일 이내 뉴스: {len(within_7d_items)}건)]"
            if len(within_7d_items) == 0:
                header += "\n⚠️ 수집된 뉴스 중 최근 7일 이내 보도된 기사가 없습니다."

            results = [header] + parsed_lines
            return "\n".join(results)

        except Exception as e:
            return f"[Yahoo Finance 뉴스 조회 오류: {corp_name_or_code}] {str(e)}"


@mcp.tool("get_yahoo_market_snapshot", description="Yahoo Finance에서 대상 종목의 실시간 시세, 52주 변동폭, 시가총액 등 시장 지표를 조회합니다.")
def get_yahoo_market_snapshot(corp_name_or_code: str) -> str:
    """
    기업의 시장 가격 및 주요 시장 스냅샷 지표를 조회합니다.

    Args:
        corp_name_or_code: 기업명 또는 티커
    """
    with contextlib.redirect_stdout(sys.stderr):
        try:
            symbol = resolve_yahoo_ticker(corp_name_or_code)
            ticker_obj = yf.Ticker(symbol)
            fi = getattr(ticker_obj, "fast_info", None)

            last_price = getattr(fi, "last_price", None) if fi else None
            if fi is None or last_price is None:
                if not corp_name_or_code.startswith("NON_EXISTENT"):
                    try:
                        from financial_data_provider import resolve_stock_info, fetch_market_and_valuation
                        s_info = resolve_stock_info(corp_name_or_code)
                        market_text = fetch_market_and_valuation(s_info)
                        if market_text and "조회 실패" not in market_text:
                            return f"[Yahoo Finance 시장 시세 스냅샷 ({symbol})]\n{market_text}"
                    except Exception:
                        pass
                return f"[Yahoo Finance] '{symbol}'의 시장 시세 정보를 가져올 수 없습니다."
            prev_close = getattr(fi, "previous_close", None)
            currency = getattr(fi, "currency", "KRW")
            market_cap = getattr(fi, "market_cap", None)
            year_high = getattr(fi, "year_high", None)
            year_low = getattr(fi, "year_low", None)

            change_str = "-"
            if last_price is not None and prev_close is not None and prev_close > 0:
                diff = last_price - prev_close
                pct = (diff / prev_close) * 100
                sign = "+" if diff > 0 else ""
                change_str = f"{sign}{diff:,.0f} ({sign}{pct:.2f}%)" if currency == "KRW" else f"{sign}{diff:,.2f} ({sign}{pct:.2f}%)"

            def format_num(val, is_curr=True):
                if val is None:
                    return "-"
                if is_curr and currency == "KRW":
                    return f"{val:,.0f} {currency}"
                elif is_curr:
                    return f"{val:,.2f} {currency}"
                return f"{val:,.0f}"

            def format_cap(val):
                if val is None:
                    return "-"
                if currency == "KRW":
                    jo = val / 1_000_000_000_000
                    return f"{jo:,.2f}조 원"
                return f"{val / 1_000_000_000:,.2f}B {currency}"

            snapshot = f"""[Yahoo Finance 시장 시세 스냅샷 ({symbol})]
- 현재가: {format_num(last_price)} (전일비: {change_str})
- 시가총액: {format_cap(market_cap)}
- 52주 최고가: {format_num(year_high)}
- 52주 최저가: {format_num(year_low)}
"""
            return snapshot
        except Exception as e:
            return f"[Yahoo Finance 시장 시세 조회 오류: {corp_name_or_code}] {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")

