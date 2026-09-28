import os
import sys
import unittest
import tempfile
import json
import re
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import db_manager
from async_utils import run_async_in_isolated_thread
from mcp_server.file_server import write_markdown
from mcp_server.dart_server import (
    get_company_overview,
    get_financial_statements,
    get_recent_disclosures
)
from mcp_server.yahoo_server import (
    resolve_yahoo_ticker,
    get_yahoo_news_summary,
    get_yahoo_market_snapshot
)
from pages.chat_page import extract_financial_data, extract_verdict


class TestDBManagerAuth(unittest.TestCase):
    """1. DB 인증 및 사용자/세션 관리 엄격 검증"""

    def setUp(self):
        db_manager.init_db()

    def test_01_signup_success(self):
        uid = f"test_user_{os.urandom(4).hex()}"
        success, msg = db_manager.signup_user(uid, "테스트위원", "pass1234")
        self.assertTrue(success, f"회원가입 실패: {msg}")

    def test_02_signup_duplicate_prevented(self):
        uid = f"dup_user_{os.urandom(4).hex()}"
        db_manager.signup_user(uid, "중복테스트", "pass1234")
        success, msg = db_manager.signup_user(uid, "중복테스트2", "pass1234")
        self.assertFalse(success, "중복 ID 가입이 허용되어서는 안 됩니다.")
        self.assertIn("이미 존재하는", msg)

    def test_03_signup_validation_short_password(self):
        success, msg = db_manager.signup_user("short_pw_user", "짧은비번", "123")
        self.assertFalse(success, "4자 미만 비밀번호가 허용되어서는 안 됩니다.")

    def test_04_signup_validation_empty_fields(self):
        success, msg = db_manager.signup_user("", "빈아이디", "pass1234")
        self.assertFalse(success, "빈 아이디가 허용되어서는 안 됩니다.")

    def test_05_login_success_and_failure(self):
        uid = f"login_user_{os.urandom(4).hex()}"
        pwd = "secure_password_99"
        db_manager.signup_user(uid, "로그인테스터", pwd)

        # 성공 케이스
        user = db_manager.login_user(uid, pwd)
        self.assertIsNotNone(user, "올바른 비밀번호로 로그인 실패")
        self.assertEqual(user["user_id"], uid)
        self.assertEqual(user["username"], "로그인테스터")

        # 비밀번호 불일치 실패 케이스
        fail_user = db_manager.login_user(uid, "wrong_password")
        self.assertIsNone(fail_user, "잘못된 비밀번호로 로그인이 허용되어서는 안 됩니다.")

        # 미등록 아이디 실패 케이스
        no_user = db_manager.login_user("non_existent_uid_12345", pwd)
        self.assertIsNone(no_user, "미등록 아이디 로그인이 허용되어서는 안 됩니다.")

    def test_06_session_and_messages_lifecycle(self):
        uid = f"sess_user_{os.urandom(4).hex()}"
        sid = f"sess_{os.urandom(4).hex()}"
        db_manager.signup_user(uid, "세션테스터", "pass1234")

        # 세션 생성
        db_manager.create_session(uid, sid, "첫 심의 세션")
        sessions = db_manager.get_sessions(uid)
        self.assertTrue(any(s["session_id"] == sid for s in sessions))

        # 세션 제목 변경
        db_manager.update_session_title(sid, "수정된 심의 세션")
        sessions = db_manager.get_sessions(uid)
        updated_s = next(s for s in sessions if s["session_id"] == sid)
        self.assertEqual(updated_s["title"], "수정된 심의 세션")

        # 메시지 추가 및 조회
        db_manager.add_message(sid, uid, "user", "삼성전자 심의 요청")
        db_manager.add_message(sid, uid, "assistant", "심의 보고서 내용")
        messages = db_manager.get_messages(sid)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")

        # 세션 삭제 및 연쇄 메시지 삭제(CASCADE)
        db_manager.delete_session(sid)
        after_sessions = db_manager.get_sessions(uid)
        self.assertFalse(any(s["session_id"] == sid for s in after_sessions))
        after_messages = db_manager.get_messages(sid)
        self.assertEqual(len(after_messages), 0, "세션 삭제 후 메시지도 삭제되어야 합니다.")


class TestFileServer(unittest.TestCase):
    """2. 마크다운 보고서 저장 FastMCP 도구 검증"""

    def test_01_write_markdown_normal(self):
        session_id = f"test_sess_{os.urandom(4).hex()}"
        res = write_markdown("테스트보고서.md", "# 테스트 심의 보고서 본문", session_id=session_id)
        self.assertIn("성공", res)

        target = PROJECT_ROOT / "output" / session_id / "테스트보고서.md"
        self.assertTrue(target.exists(), "보고서 파일이 지정 경로에 생성되어야 합니다.")
        content = target.read_text(encoding="utf-8")
        self.assertEqual(content, "# 테스트 심의 보고서 본문")

        # 정리
        target.unlink(missing_ok=True)
        target.parent.rmdir()

    def test_02_write_markdown_path_traversal_prevention(self):
        # 상위 디렉터리 탈출 시도 방어 검증
        session_id = "safe_sess"
        res = write_markdown("../../evil.md", "악의적 파일", session_id=session_id)
        self.assertIn("성공", res)
        # 상위가 아닌 안전한 output/safe_sess/evil.md 로 저장되었는지 확인
        safe_target = PROJECT_ROOT / "output" / session_id / "evil.md"
        self.assertTrue(safe_target.exists(), "경로 조작이 필터링되어 안전 폴더 내에 저장되어야 합니다.")
        evil_outside = PROJECT_ROOT / "evil.md"
        self.assertFalse(evil_outside.exists(), "상위 디렉터리에 파일이 저장되어서는 안 됩니다.")

        # 정리
        safe_target.unlink(missing_ok=True)
        safe_target.parent.rmdir()


class TestDARTTools(unittest.TestCase):
    """3. DART 공시 및 재무 조회 도구 검증"""

    def test_01_get_company_overview_samsung(self):
        res = get_company_overview("삼성전자")
        self.assertIn("기업 개요", res)
        self.assertIn("005930", res)
        self.assertIn("대표자명", res)

    def test_02_get_company_overview_invalid(self):
        res = get_company_overview("존재하지않는가상기업_99999")
        self.assertTrue("찾을 수 없습니다" in res or "오류" in res)

    def test_03_get_financial_statements(self):
        res = get_financial_statements("삼성전자", 2024)
        self.assertIn("재무제표", res)
        # 매출액 또는 영업이익 지표가 포함되어 있어야 함
        has_key_metric = ("매출액" in res or "수익" in res or "영업이익" in res)
        self.assertTrue(has_key_metric, f"주요 재무 지표가 포함되어야 합니다:\n{res}")

    def test_04_get_recent_disclosures(self):
        res = get_recent_disclosures("삼성전자", count=3)
        self.assertIn("최근 주요 공시", res)
        res = get_recent_disclosures("삼성전자", count=3, days=7)
        self.assertIn("DART", res)
        self.assertIn("공시", res)
        self.assertIn("https://dart.fss.or.kr", res)

    def test_05_get_recent_disclosures_warning_when_no_recent_filings(self):
        # 0일 범위 지정 시 7일 이내 공시 부재 경고 및 직전 공시 안내 반환 검증
        res = get_recent_disclosures("삼성전자", count=3, days=0)
        self.assertIn("신규 DART 공시가 없습니다", res)
        self.assertIn("직전 최근 공시", res)


class TestUIParsers(unittest.TestCase):
    """4. 프론트엔드 파서 및 지표 추출 로직 검증"""

    def test_01_extract_financial_data(self):
        sample_text = """
        보고서 본문 내용입니다.
        ```json_financial_data
        {
          "corp_name": "테스트전자",
          "years": ["2023", "2024", "2025"],
          "revenue": [1000, 1200, 1500],
          "operating_profit": [100, 150, 200],
          "net_profit": [80, 120, 160],
          "unit": "억원"
        }
        ```
        추가 설명입니다.
        """
        data = extract_financial_data(sample_text)
        self.assertIsNotNone(data)
        self.assertEqual(data["corp_name"], "테스트전자")
        self.assertEqual(data["years"], ["2023", "2024", "2025"])
        self.assertEqual(data["revenue"], [1000, 1200, 1500])

    def test_02_extract_verdict(self):
        cases = [
            ("## 3. CRO 결론\n- **투자 판정**: [적극 매수]\n- 비중: 15%", "[적극 매수]"),
            ("평가 결과:\n- **투자 판정**: 분할 매수 (목표 비중 10%)\n- 손절가: 50,000", "분할 매수 (목표 비중 10%)"),
            ("- **투자판정**: [중립(관망)]", "[중립(관망)]"),
            ("- **투자  판정**: [매도(비중 축소)]", "[매도(비중 축소)]"),
        ]
        for text, expected in cases:
            extracted = extract_verdict(text)
            self.assertIsNotNone(extracted, f"판정 추출 실패: {text}")
            self.assertEqual(extracted, expected)


class TestAsyncIsolation(unittest.TestCase):
    """5. 동기/비동기 격리 엔진(Ctrl+C 보호) 검증"""

    def test_01_isolated_thread_execution(self):
        import asyncio

        async def sample_coro(x, y):
            await asyncio.sleep(0.01)
            return x + y

        result = run_async_in_isolated_thread(sample_coro, 10, 20)
        self.assertEqual(result, 30)

    def test_02_isolated_thread_exception_propagation(self):
        import asyncio

        async def failing_coro():
            await asyncio.sleep(0.01)
            raise ValueError("고의 발생 예외")

        with self.assertRaises(ValueError):
            run_async_in_isolated_thread(failing_coro)



class TestLangGraphNodes(unittest.TestCase):
    """6. 랭그래프(LangGraph) 멀티 노드 파이프라인 정밀 검증"""

    def test_01_graph_structure_and_nodes(self):
        from agent_builder import build_committee_graph
        graph = build_committee_graph()
        self.assertIsNotNone(graph)
        # 노드 이름 검증
        expected_nodes = {"fetch_context", "bull_analyst", "bear_analyst", "cro_analyst", "compile_report"}
        actual_nodes = set(graph.nodes.keys())
        for node in expected_nodes:
            self.assertIn(node, actual_nodes, f"노드 '{node}'가 그래프에 포함되어야 합니다.")

    def test_02_compile_report_node(self):
        from agent_builder import node_compile_report, CommitteeState
        state: CommitteeState = {
            "query": "삼성전자 심의",
            "thread_id": "test_unit_sess",
            "ticker": "삼성전자",
            "context_data": "컨텍스트 데이터",
            "fin_json": '{"corp_name": "삼성전자", "revenue": [100]}',
            "bull_analysis": "## 🟢 Bull Case 분석 보고서\n- 핵심 성장 동력: AI 반도체",
            "bear_analysis": "## 🔴 Bear Case 반박 보고서\n- 반박: 사이클 둔화",
            "cro_analysis": "## ⚖️ 최종 투자 심의 위원회 의결서\n- **투자 판정**: [분할 매수]",
            "final_report": ""
        }
        res = node_compile_report(state)
        report = res["final_report"]
        self.assertIn("# [삼성전자] 가상 투자 심의 보고서", report)
        self.assertIn("## 🟢 Bull Case 분석 보고서", report)
        self.assertIn("## 🔴 Bear Case 반박 보고서", report)
        self.assertIn("## ⚖️ 최종 투자 심의 위원회 의결서", report)
        self.assertIn("```json_financial_data", report)

    def test_03_extract_ticker(self):
        from agent_builder import extract_ticker_from_query
        from langchain_google_genai import ChatGoogleGenerativeAI
        from config import MODEL_NAME, GEMINI_API_KEY
        llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=GEMINI_API_KEY)

        self.assertEqual(extract_ticker_from_query("005930", llm), "005930")
        self.assertEqual(extract_ticker_from_query("SK하이닉스 투자 심의 해줘", llm), "SK하이닉스")
        self.assertEqual(extract_ticker_from_query("현대차 어때", llm), "현대차")

    def test_04_node_fetch_context_integration(self):
        from agent_builder import node_fetch_context, CommitteeState
        state: CommitteeState = {
            "query": "삼성전자",
            "thread_id": "test_fetch_sess",
            "ticker": "삼성전자",
            "context_data": "",
            "fin_json": None,
            "bull_analysis": "",
            "bear_analysis": "",
            "cro_analysis": "",
            "final_report": ""
        }
        res = node_fetch_context(state)
        self.assertIn("ticker", res)
        self.assertEqual(res["ticker"], "삼성전자")
        context = res.get("context_data", "")
        # DART 및 Yahoo Finance 데이터가 모두 통합되었는지 검증
        self.assertIn("(DART)", context)
        self.assertIn("(Yahoo Finance)", context)
        self.assertIn("시장 뉴스", context)


class TestYahooFinanceTools(unittest.TestCase):
    """7. Yahoo Finance 뉴스 요약 및 시장 지표 도구 검증"""

    def test_01_resolve_ticker_korean_name(self):
        sym = resolve_yahoo_ticker("삼성전자")
        self.assertEqual(sym, "005930.KS")

    def test_02_resolve_ticker_code(self):
        sym = resolve_yahoo_ticker("005930")
        self.assertEqual(sym, "005930.KS")

    def test_03_resolve_ticker_us(self):
        sym = resolve_yahoo_ticker("AAPL")
        self.assertEqual(sym, "AAPL")

    def test_04_get_yahoo_news_summary_samsung(self):
        res = get_yahoo_news_summary("삼성전자", count=3)
        self.assertIn("Yahoo Finance 최신 뉴스 요약", res)
        self.assertIn("Yahoo Finance 최신 시장 뉴스 요약", res)
        self.assertIn("005930.KS", res)
        # 뉴스 항목 또는 링크 존재 확인
        self.assertTrue("뉴스 요약" in res or "링크" in res)

    def test_05_get_yahoo_news_summary_us(self):
        res = get_yahoo_news_summary("AAPL", count=2)
        self.assertIn("Yahoo Finance 최신 뉴스 요약", res)
        self.assertIn("Yahoo Finance 최신 시장 뉴스 요약", res)
        self.assertIn("AAPL", res)

    def test_06_get_yahoo_news_fallback_nonexistent(self):
        # 존재하지 않는 종목에 대해 예외 없이 안내 메시지 반환 검증
        res = get_yahoo_news_summary("NON_EXISTENT_99999", count=2)
        self.assertTrue("찾을 수 없습니다" in res or "오류" in res)

    def test_07_get_yahoo_market_snapshot(self):
        res = get_yahoo_market_snapshot("삼성전자")
        self.assertIn("Yahoo Finance 시장 시세 스냅샷", res)
        self.assertIn("현재가", res)
        self.assertIn("시가총액", res)

    def test_08_get_yahoo_news_recency_tag(self):
        res = get_yahoo_news_summary("005930.KS", count=3)
        self.assertIn("최근 7일 이내 뉴스", res)


if __name__ == "__main__":
    unittest.main(verbosity=2)

