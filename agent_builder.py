import os
import sys
import json
import re
from pathlib import Path
from typing import TypedDict, Optional, Dict, Any

# Windows 콘솔 cp949 이모지 인코딩 에러 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from config import (
    DB_PATH,
    MODEL_NAME,
    GEMINI_API_KEY,
    BULL_PROMPT_TEMPLATE,
    BEAR_PROMPT_TEMPLATE,
    CRO_PROMPT_TEMPLATE
)
from mcp_server.dart_server import (
    get_company_overview,
    get_financial_statements,
    get_recent_disclosures,
    get_dart_client
)
from mcp_server.yahoo_server import (
    get_yahoo_news_summary,
    get_yahoo_market_snapshot
)
from mcp_server.file_server import write_pdf

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# ============================================================
# 1. 랭그래프 상태(State) 정의
# ============================================================
class CommitteeState(TypedDict):
    query: str
    thread_id: str
    ticker: str
    context_data: str
    fin_json: Optional[str]
    bull_analysis: str
    bear_analysis: str
    cro_analysis: str
    final_report: str


def _clean_response_text(resp: Any) -> str:
    """ChatGoogleGenerativeAI 응답 객체에서 문자열 텍스트를 안전하게 추출 (list 또는 str 호환)"""
    if resp is None:
        return ""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                parts.append(str(p["text"]))
            elif hasattr(p, "text"):
                parts.append(str(p.text))
            else:
                parts.append(str(p))
        return "\n".join(parts).strip()
    return str(content).strip()


# ============================================================
# 2. 유틸리티 함수: 종목명 추출
# ============================================================
def extract_ticker_from_query(query: str, llm: ChatGoogleGenerativeAI) -> str:
    """사용자 질문에서 분석 대상 기업명 또는 종목코드를 추출"""
    clean_q = query.strip()
    # 이미 6자리 종목코드인 경우
    if re.match(r"^\d{6}$", clean_q):
        return clean_q

    # 간단한 단어인 경우 (예: "삼성전자", "SK하이닉스", "현대차")
    words = clean_q.split()
    first_word = words[0] if words else ""
    stopwords = ["투자", "심의", "분석", "해줘", "보고서", "어때", "주식", "종목"]
    filtered_words = [w for w in words if not any(sw in w for sw in stopwords)]
    if filtered_words and len(filtered_words[0]) >= 2:
        candidate = filtered_words[0]
        # 한글/영문/숫자만 추출
        clean_candidate = re.sub(r"[^\w]", "", candidate)
        if clean_candidate:
            return clean_candidate

    # LLM을 통한 정확한 단일 종목명 추출 (Fallback)
    try:
        extract_prompt = (
            f"다음 문장에서 분석 대상 기업명(또는 종목코드) 딱 하나만 단어로 답하세요. "
            f"다른 부가 설명 없이 회사명만 출력하세요.\n문장: '{query}'"
        )
        resp = llm.invoke(extract_prompt)
        ticker_text = _clean_response_text(resp)
        ticker = ticker_text.split()[0] if ticker_text else first_word
        return re.sub(r"[^\w]", "", ticker)
    except Exception:
        return first_word or "삼성전자"


# ============================================================
# 3. 랭그래프 노드(Node) 구현
# ============================================================

def node_fetch_context(state: CommitteeState) -> Dict[str, Any]:
    """[노드 0] DART 원천 데이터 수집 및 Context Data 생성 노드"""
    ticker = state.get("ticker", "")
    query = state.get("query", "")

    # LLM 객체 생성
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY
    )

    if not ticker:
        ticker = extract_ticker_from_query(query, llm)

    # 1. 기업 개요 (DART)
    overview_text = get_company_overview(ticker)

    # 2. 최근 재무제표 (DART, 2025 -> 2024 -> 2023 순차 시도)
    fs_text = get_financial_statements(ticker, year=2024)

    # 3. 최근 공시 목록 (DART)
    disc_text = get_recent_disclosures(ticker, count=5)
    # 3. 최근 공시 목록 (DART, 최근 7일 이내 우선 필터링)
    disc_text = get_recent_disclosures(ticker, count=5, days=7)

    # 4. 최근 주요 시장 뉴스 요약 (Yahoo Finance, 7일 이내 시점 태깅)
    yahoo_news_text = get_yahoo_news_summary(ticker, count=5)

    # 5. 실시간 시장 시세 및 스냅샷 (Yahoo Finance)
    yahoo_market_text = get_yahoo_market_snapshot(ticker)

    # 타임스탬프 및 7일 유효 범위 설정
    from datetime import datetime, timedelta
    today_dt = datetime.today()
    week_ago_dt = today_dt - timedelta(days=7)
    time_window_str = f"{week_ago_dt.strftime('%Y-%m-%d')} ~ {today_dt.strftime('%Y-%m-%d')}"

    # 컨텍스트 데이터 종합 (DART 공시/재무 + Yahoo Finance 시장 뉴스/시세)
    context_data = f"""[분석 기준 시점 및 데이터 유효 범위]
- 데이터 수집 시점: {today_dt.strftime('%Y-%m-%d %H:%M')}
- 주식 시장 초단기 모멘텀 기준: 최근 7일(1주일, {time_window_str})
- [데이터 성격 구분]:
  1) DART 재무제표: 공식 회계감사 결산 팩트(분기/연간 단위 펀더멘털)
  2) DART 공시: 최근 7일간 공식 접수된 법적 의무 공시 (신규 부재 시 상태 명시)
  3) Yahoo Finance: 최근 7일/실시간 언론 보도 및 시장 센티먼트, 실시간 시세

[기업 개요 및 기본 정보 (DART)]
{overview_text}

[주요 재무제표 팩트 데이터 (DART)]
{fs_text}

[최근 주요 공시 내역 (DART - 최근 7일 우선 검증)]
{disc_text}

[최근 주요 시장 뉴스 및 센티먼트 요약 (Yahoo Finance - 최근 7일/실시간 기준)]
{yahoo_news_text}

[시장 시세 및 스냅샷 (Yahoo Finance)]
{yahoo_market_text}
"""

    # 시각화용 재무 JSON 추출 시도
    fin_json = None
    try:
        json_prompt = f"""다음 재무제표 텍스트에서 매출액, 영업이익, 당기순이익의 최근 3개년 수치를 추출하여 JSON 형식으로만 응답하세요.
반드시 아래 JSON 포맷을 따르고 다른 텍스트는 일절 출력하지 마세요:
{{
  "corp_name": "{ticker}",
  "years": ["2022", "2023", "2024"],
  "revenue": [숫자1, 숫자2, 숫자3],
  "operating_profit": [숫자1, 숫자2, 숫자3],
  "net_profit": [숫자1, 숫자2, 숫자3],
  "unit": "원 또는 억원"
}}

재무제표 텍스트:
{fs_text}
"""
        json_resp = llm.invoke(json_prompt)
        raw_json_text = _clean_response_text(json_resp)
        match = re.search(r"\{.*\}", raw_json_text, re.DOTALL)
        if match:
            fin_json = match.group(0)
    except Exception:
        fin_json = None

    return {
        "ticker": ticker,
        "context_data": context_data,
        "fin_json": fin_json
    }


def node_bull_analyst(state: CommitteeState) -> Dict[str, Any]:
    """[노드 1] Bull Analyst (성장 잠재력 발굴 시니어 롱 전문 애널리스트)"""
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY
    )

    prompt = BULL_PROMPT_TEMPLATE.format(
        ticker=state["ticker"],
        context_data=state["context_data"]
    )

    response = llm.invoke(prompt)
    return {"bull_analysis": _clean_response_text(response)}


def node_bear_analyst(state: CommitteeState) -> Dict[str, Any]:
    """[노드 2] Bear Analyst (냉철한 숏 포지션 전문 헤지펀드 매니저)"""
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY
    )

    prompt = BEAR_PROMPT_TEMPLATE.format(
        ticker=state["ticker"],
        context_data=state["context_data"],
        bull_analysis=state["bull_analysis"]
    )

    response = llm.invoke(prompt)
    return {"bear_analysis": _clean_response_text(response)}


def node_cro_analyst(state: CommitteeState) -> Dict[str, Any]:
    """[노드 3] Chief Risk Officer (최고 위험 관리 책임자)"""
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY
    )

    prompt = CRO_PROMPT_TEMPLATE.format(
        ticker=state["ticker"],
        context_data=state["context_data"],
        bull_analysis=state["bull_analysis"],
        bear_analysis=state["bear_analysis"]
    )

    response = llm.invoke(prompt)
    return {"cro_analysis": _clean_response_text(response)}


def node_compile_report(state: CommitteeState) -> Dict[str, Any]:
    """[노드 4] 최종 가상 투자 심의 보고서 취합 및 파일 저장 노드"""
    ticker = state["ticker"]
    thread_id = state.get("thread_id", "default_thread")
    bull = state["bull_analysis"]
    bear = state["bear_analysis"]
    cro = state["cro_analysis"]
    fin_json = state.get("fin_json")

    # 전체 보고서 조합
    report_parts = [
        f"# [{ticker}] 가상 투자 심의 보고서",
        "",
        bull,
        "",
        bear,
        "",
        cro
    ]

    # 시각화 데이터 JSON 블록 포함
    if fin_json:
        report_parts.extend([
            "",
            "```json_financial_data",
            fin_json,
            "```"
        ])

    final_report = "\n".join(report_parts)

    # PDF 투자 심의 보고서 자동 생성 및 저장
    clean_ticker = re.sub(r"[^\w]", "_", ticker)
    filename = f"{clean_ticker}_가상투자심의보고서.pdf"
    try:
        write_pdf(filename, final_report, session_id=thread_id)
    except Exception as e:
        print(f"[Warning] PDF 보고서 파일 저장 실패: {e}")

    return {"final_report": final_report}


# ============================================================
# 4. 랭그래프(LangGraph) 워크플로우 구성
# ============================================================
def build_committee_graph(checkpointer=None):
    """3인 투자 심의 위원회 StateGraph 컴파일"""
    workflow = StateGraph(CommitteeState)

    # 노드 등록
    workflow.add_node("fetch_context", node_fetch_context)
    workflow.add_node("bull_analyst", node_bull_analyst)
    workflow.add_node("bear_analyst", node_bear_analyst)
    workflow.add_node("cro_analyst", node_cro_analyst)
    workflow.add_node("compile_report", node_compile_report)

    # 엣지 연결 (순차 실행 파이프라인)
    workflow.set_entry_point("fetch_context")
    workflow.add_edge("fetch_context", "bull_analyst")
    workflow.add_edge("bull_analyst", "bear_analyst")
    workflow.add_edge("bear_analyst", "cro_analyst")
    workflow.add_edge("cro_analyst", "compile_report")
    workflow.add_edge("compile_report", END)

    # 컴파일
    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# 5. 에이전트 실행 진입점 함수
# ============================================================
async def execute_agent(query: str, thread_id: str = "default_thread") -> str:
    """
    LangGraph 3인 투자 심의 위원회 워크플로우를 실행하고 최종 보고서를 반환합니다.
    """
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 입력해주세요. "
            "(https://aistudio.google.com/ 에서 무료 발급 가능)"
        )

    # 그래프 빌드
    graph = build_committee_graph()

    # 초기 상태
    initial_state: CommitteeState = {
        "query": query,
        "thread_id": thread_id,
        "ticker": "",
        "context_data": "",
        "fin_json": None,
        "bull_analysis": "",
        "bear_analysis": "",
        "cro_analysis": "",
        "final_report": ""
    }

    # 비동기 실행
    result = await graph.ainvoke(initial_state)
    return result.get("final_report", "")
