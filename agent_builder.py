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
    market_news: Optional[str]
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
    """[노드 0] 종합 원천 데이터 수집(DART, FDR, Naver API, Yahoo Finance) 및 Context Data 생성 노드"""
    ticker = state.get("ticker", "")
    query = state.get("query", "")

    # LLM 객체 생성
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY
    )

    if not ticker:
        raw_target = extract_ticker_from_query(query, llm)
    else:
        raw_target = ticker

    # 금융 데이터 파이프라인(종목명 정규화, DART, FDR, 네이버 증권, 최신 뉴스, 뉴스 인텔리전스)
    from financial_data_provider import build_comprehensive_context
    stock_info, context_data = build_comprehensive_context(raw_target or query, llm=llm)
    resolved_ticker = stock_info.get("corp_name", raw_target or "삼성전자")

    # 1차: 파이프라인에서 수집된 구조화된 분기별 재무 JSON 직접 사용
    fin_json = stock_info.get("fin_json")

    # 2차 Fallback: 없을 경우 LLM 기반 추출 시도
    if not fin_json:
        try:
            json_prompt = f"""다음 재무 정보 텍스트의 [최근 분기별 실적 추이]에서 이미 공식 분기보고서가 발표/확정된 분기(미발표/추정치(E) 제외)만을 선별하여 분기명, 매출액, 영업이익, 당기순이익 수치를 추출하여 JSON 형식으로만 응답하세요.
반드시 아래 JSON 포맷을 따르고 마크다운 코드블록이나 부가 설명 없이 순수 JSON만 반환하세요:
{{
  "corp_name": "{resolved_ticker}",
  "period_type": "quarterly",
  "periods": ["2025.06", "2025.09", "2025.12", "2026.03", "2026.06"],
  "years": ["2025.06", "2025.09", "2025.12", "2026.03", "2026.06"],
  "revenue": [숫자1, 숫자2, 숫자3, 숫자4, 숫자5],
  "operating_profit": [숫자1, 숫자2, 숫자3, 숫자4, 숫자5],
  "net_profit": [숫자1, 숫자2, 숫자3, 숫자4, 숫자5],
  "unit": "억원"
}}

재무 정보 텍스트:
{context_data}
"""
            json_resp = llm.invoke(json_prompt)
            raw_json_text = _clean_response_text(json_resp)
            match = re.search(r"\{.*\}", raw_json_text, re.DOTALL)
            if match:
                fin_json = match.group(0)
        except Exception:
            fin_json = None

    market_news = stock_info.get("market_news", "")

    return {
        "ticker": resolved_ticker,
        "context_data": context_data,
        "fin_json": fin_json,
        "market_news": market_news
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
    """[노드 3] Chief Investment Analyst (수석 투자분석가 종합 분석 의견서)"""
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
    """[노드 4] 최종 종합 투자분석 보고서 취합 및 파일 저장 노드"""
    ticker = state["ticker"]
    thread_id = state.get("thread_id", "default_thread")
    bull = state["bull_analysis"]
    bear = state["bear_analysis"]
    cro = state["cro_analysis"]
    fin_json = state.get("fin_json")
    market_news = state.get("market_news", "")

    # 전체 보고서 조합
    report_parts = [
        f"# [{ticker}] 종합 투자분석 보고서",
        ""
    ]

    # 최신 주요 뉴스 및 언론 보도 섹션 포함
    if market_news:
        report_parts.extend([
            "## 📰 최근 주요 시장 뉴스 및 언론 보도 (Yahoo Finance / 실시간 언론사 집계)",
            market_news,
            "",
            "---",
            ""
        ])

    report_parts.extend([
        bull,
        "",
        bear,
        "",
        cro
    ])

    # 시각화 데이터 JSON 블록 포함
    if fin_json:
        report_parts.extend([
            "",
            "```json_financial_data",
            fin_json,
            "```"
        ])

    final_report = "\n".join(report_parts)

    # PDF 종합 투자분석 보고서 자동 생성 및 저장
    clean_ticker = re.sub(r"[^\w]", "_", ticker)
    filename = f"{clean_ticker}_종합투자분석보고서.pdf"
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
async def execute_agent(
    query: str,
    thread_id: str = "default_thread",
    step_callback: Optional[Any] = None
) -> str:
    """
    LangGraph 3인 투자 심의 위원회 워크플로우를 실행하고 최종 보고서를 반환합니다.
    step_callback이 주어지면 각 노드 완료 시마다 실시간 진행 단계를 업데이트합니다.
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
        "market_news": None,
        "bull_analysis": "",
        "bear_analysis": "",
        "cro_analysis": "",
        "final_report": ""
    }

    if step_callback:
        step_callback(1, "🔍 DART 기업 개요 및 3개년 회계 결산 팩트 수집")

    final_report = ""
    async for event in graph.astream(initial_state):
        for node_name, node_val in event.items():
            if node_name == "fetch_context":
                if step_callback:
                    step_callback(2, "📊 Yahoo Finance 실시간 시세 및 언론사 최신 뉴스 수집")
            elif node_name == "bull_analyst":
                if step_callback:
                    step_callback(3, "🟢 Bull Analyst (롱 포지션) 성장 잠재력/Catalyst 분석")
            elif node_name == "bear_analyst":
                if step_callback:
                    step_callback(4, "🔴 Bear Analyst (숏 포지션) 주가 급락 원인 및 하방 리스크 검증")
            elif node_name == "cro_analyst":
                if step_callback:
                    step_callback(5, "📊 수석 투자분석가(CIO) 종합 분석 의견서 및 A4 PDF 보고서 발행")
            elif node_name == "compile_report":
                final_report = node_val.get("final_report", "")

    return final_report
