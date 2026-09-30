import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import time
import db_manager
import task_manager
from config import BASE_DIR, OUTPUT_DIR, GEMINI_API_KEY, DART_API_KEY
from agent_builder import execute_agent
from async_utils import run_async_in_isolated_thread
from pdf_generator import markdown_to_pdf_bytes

def extract_financial_data(text: str):
    """답변 텍스트에서 json_financial_data 코드 블록을 추출하여 딕셔너리로 반환"""
    pattern = r"```json_financial_data\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            return None
    return None

def extract_verdict(text: str):
    """답변 텍스트에서 CRO 투자 판정 추출"""
    match = re.search(r"\*\*투자\s*판정\*\*:\s*([^\n\r]+)", text)
    if match:
        verdict = match.group(1).strip()
        return verdict
    return None

def render_verdict_badge(verdict: str):
    """투자 판정에 따른 시각적 배지 렌더링"""
    if "적극 매수" in verdict:
        color = "#10B981"  # 녹색
        bg = "#ECFDF5"
        icon = "🚀"
    elif "분할 매수" in verdict:
        color = "#3B82F6"  # 파란색
        bg = "#EFF6FF"
        icon = "📈"
    elif "중립" in verdict or "관망" in verdict:
        color = "#F59E0B"  # 노란색
        bg = "#FFFBEB"
        icon = "⚖️"
    elif "매도" in verdict or "축소" in verdict:
        color = "#EF4444"  # 빨간색
        bg = "#FEF2F2"
        icon = "⚠️"
    else:
        color = "#6B7280"
        bg = "#F3F4F6"
        icon = "📋"

    st.markdown(f"""
        <div style='background: {bg}; border: 1.5px solid {color}; border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.8rem; display: inline-block;'>
            <span style='font-size: 1.1rem; font-weight: bold; color: {color};'>{icon} 심의 판정: {verdict}</span>
        </div>
    """, unsafe_allow_html=True)

def render_financial_chart(fin_data: dict):
    """Plotly를 이용한 인터랙티브 분기별/연도별 실적 지표 및 차트 렌더링"""
    corp_name = fin_data.get("corp_name", "기업")
    # 분기(periods) 우선, 없으면 years 참조
    periods = [str(p) for p in (fin_data.get("periods") or fin_data.get("quarters") or fin_data.get("years", []))]
    revenue = fin_data.get("revenue", [])
    operating_profit = fin_data.get("operating_profit", [])
    net_profit = fin_data.get("net_profit", [])
    unit = fin_data.get("unit", "억원")
    period_type = fin_data.get("period_type", "quarterly" if any("." in str(p) or "Q" in str(p).upper() for p in periods) else "annual")
    delta_tag = "(전분기비)" if period_type == "quarterly" else "(전년비)"

    if not periods or not revenue:
        return

    # 1. 최신 실적 요약 카드
    col_m1, col_m2, col_m3 = st.columns(3)
    latest_rev = revenue[-1] if revenue else 0
    latest_op = operating_profit[-1] if operating_profit else 0
    latest_np = net_profit[-1] if net_profit else 0

    rev_delta = None
    if len(revenue) >= 2 and revenue[-2] and isinstance(revenue[-1], (int, float)) and isinstance(revenue[-2], (int, float)):
        diff = revenue[-1] - revenue[-2]
        pct = (diff / revenue[-2]) * 100
        rev_delta = f"{pct:+.1f}% {delta_tag}"

    op_delta = None
    if len(operating_profit) >= 2 and operating_profit[-2] and isinstance(operating_profit[-1], (int, float)) and isinstance(operating_profit[-2], (int, float)):
        diff = operating_profit[-1] - operating_profit[-2]
        pct = (diff / abs(operating_profit[-2])) * 100 if operating_profit[-2] != 0 else 0
        op_delta = f"{pct:+.1f}% {delta_tag}"

    np_delta = None
    if len(net_profit) >= 2 and net_profit[-2] and isinstance(net_profit[-1], (int, float)) and isinstance(net_profit[-2], (int, float)):
        diff = net_profit[-1] - net_profit[-2]
        pct = (diff / abs(net_profit[-2])) * 100 if net_profit[-2] != 0 else 0
        np_delta = f"{pct:+.1f}% {delta_tag}"

    with col_m1:
        st.metric(
            label=f"최신 분기 매출액 ({unit})" if period_type == "quarterly" else f"최신 매출액 ({unit})",
            value=f"{latest_rev:,}" if isinstance(latest_rev, (int, float)) else str(latest_rev),
            delta=rev_delta
        )
    with col_m2:
        st.metric(
            label=f"최신 분기 영업이익 ({unit})" if period_type == "quarterly" else f"최신 영업이익 ({unit})",
            value=f"{latest_op:,}" if isinstance(latest_op, (int, float)) else str(latest_op),
            delta=op_delta
        )
    with col_m3:
        st.metric(
            label=f"최신 분기 당기순이익 ({unit})" if period_type == "quarterly" else f"최신 당기순이익 ({unit})",
            value=f"{latest_np:,}" if isinstance(latest_np, (int, float)) else str(latest_np),
            delta=np_delta
        )

    # 2. 실적 추이 인터랙티브 차트
    chart_title = f"{corp_name} 최근 분기별 실적 추이" if period_type == "quarterly" else f"{corp_name} 연도별 실적 추이"
    xaxis_title = "분기 (QoQ)" if period_type == "quarterly" else "결산 연도"

    with st.expander(f"📊 {chart_title} 차트 펼쳐보기", expanded=True):
        fig = go.Figure()

        # 매출액 바 차트
        fig.add_trace(go.Bar(
            x=periods,
            y=revenue,
            name="매출액",
            marker_color="#2563EB",
            text=[f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in revenue],
            textposition="outside"
        ))

        # 영업이익 바 차트
        if operating_profit:
            fig.add_trace(go.Bar(
                x=periods,
                y=operating_profit,
                name="영업이익",
                marker_color="#10B981",
                text=[f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in operating_profit],
                textposition="outside"
            ))

        # 당기순이익 라인 차트
        if net_profit:
            fig.add_trace(go.Scatter(
                x=periods,
                y=net_profit,
                name="당기순이익",
                mode="lines+markers+text",
                line=dict(color="#F59E0B", width=3),
                marker=dict(size=8),
                text=[f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in net_profit],
                textposition="top center"
            ))

        fig.update_layout(
            title=dict(
                text=f"{corp_name} 주요 재무 실적 추이 ({unit})",
                font=dict(size=15)
            ),
            barmode="group",
            xaxis_title=xaxis_title,
            yaxis_title=f"금액 ({unit})",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=20, r=20, t=50, b=30),
            template="plotly_white",
            hovermode="x unified"
        )

        st.plotly_chart(fig, use_container_width=True)

def cleanup_guest_data():
    """게스트 모드의 임시 파일 및 메시지 완전 파기"""
    if "guest_session_id" in st.session_state:
        guest_dir = OUTPUT_DIR / st.session_state.guest_session_id
        if guest_dir.exists():
            shutil.rmtree(guest_dir, ignore_errors=True)
    st.session_state.guest_messages = []
    st.session_state.guest_session_id = f"guest_{uuid.uuid4().hex[:8]}"

def render_auth_header():
    """상단 헤더 타이틀 (우측 상단 인증 UI는 완전히 삭제되고 사이드바로 이동됨)"""
    st.markdown("### 🐂 불곰 (Bull-Gom) : AI 투자 분석가 🐻")


def render_chat_page():
    # DB 초기화
    db_manager.init_db()

    # 상단 헤더 타이틀만 표시
    render_auth_header()

    # 새로고침 시 로그인 복원: query_params에 토큰이 있으면 자동 로그인
    if st.session_state.get("auth_user") is None:
        token = st.query_params.get("token")
        if token:
            restored_user = db_manager.verify_login_token(token)
            if restored_user:
                st.session_state.auth_user = restored_user
            else:
                # 유효하지 않은 토큰 제거
                del st.query_params["token"]

    auth_user = st.session_state.get("auth_user")
    is_guest = auth_user is None

    # 1. 왼쪽 사이드바 구성 (로그인/회원가입/로그아웃 상시 지원)
    with st.sidebar:
        if is_guest:
            st.header("👤 게스트 모드")
            st.info("""
            **현재 게스트 모드로 접속 중입니다.**
            
            - 게스트 분석 대화 및 생성된 PDF 보고서는 **영구 저장되지 않으며**, 브라우저를 닫거나 세션 초기화 시 **자동으로 영구 파기**됩니다.
            - 분석 보고서와 대화 내역을 계속 보존하고 관리하시려면 아래에서 **로그인 또는 회원가입**을 진행해주세요.
            """)

            with st.popover("🔑 로그인 / 회원가입", use_container_width=True):
                tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
                
                with tab_login:
                    with st.form("chat_login_form"):
                        st.markdown("##### 기존 회원 로그인")
                        login_id = st.text_input("아이디", key="login_id")
                        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
                        if st.form_submit_button("로그인하기", use_container_width=True, type="primary"):
                            user_info = db_manager.login_user(login_id, login_pw)
                            if user_info:
                                # 로그인 시 게스트 임시 보고서/대화 안전하게 파기
                                cleanup_guest_data()
                                st.session_state.auth_user = user_info
                                # 토큰 발급 → query_params에 저장 (새로고침 시 로그인 유지)
                                token = db_manager.create_login_token(user_info["user_id"])
                                st.query_params["token"] = token
                                st.success(f"{user_info['username']}님 환영합니다!")
                                st.rerun()
                            else:
                                st.error("아이디 또는 비밀번호가 일치하지 않습니다.")

                with tab_signup:
                    with st.form("chat_signup_form"):
                        st.markdown("##### 신규 회원가입")
                        signup_id = st.text_input("새 아이디", key="signup_id")
                        signup_name = st.text_input("닉네임(이름)", key="signup_name")
                        signup_pw = st.text_input("새 비밀번호", type="password", key="signup_pw")
                        if st.form_submit_button("가입 및 자동 로그인", use_container_width=True):
                            success, msg = db_manager.signup_user(signup_id, signup_name, signup_pw)
                            if success:
                                # 회원가입 및 로그인 시 게스트 임시 보고서/대화 안전하게 파기
                                cleanup_guest_data()
                                new_user = {"user_id": signup_id.strip(), "username": signup_name.strip()}
                                st.session_state.auth_user = new_user
                                # 토큰 발급 → query_params에 저장 (새로고침 시 로그인 유지)
                                token = db_manager.create_login_token(new_user["user_id"])
                                st.query_params["token"] = token
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

            if st.button("🧹 대화 초기화", use_container_width=True):
                cleanup_guest_data()
                if "guest_session_id" in st.session_state:
                    task_manager.clear_task(st.session_state.guest_session_id)
                st.toast("대화 내용이 초기화되었습니다.", icon="🧹")
                st.rerun()
        else:
            st.header(f"🗂️ {auth_user['username']}")

            # 언제든지 로그아웃할 수 있도록 사이드바 상단에 회원 정보 및 로그아웃 버튼 배치
            user_cols = st.columns([1.7, 1.3])
            with user_cols[0]:
                st.caption(f"아이디: `{auth_user['user_id']}`")
            with user_cols[1]:
                if st.button("로그아웃", key="sb_logout", use_container_width=True):
                    # 로그인 토큰 삭제 (DB + URL)
                    db_manager.delete_login_token(auth_user["user_id"])
                    if "token" in st.query_params:
                        del st.query_params["token"]
                    st.session_state.auth_user = None
                    if "current_session_id" in st.session_state:
                        del st.session_state["current_session_id"]
                    cleanup_guest_data()
                    st.rerun()

            st.markdown("---")
            current_user_id = auth_user["user_id"]

            # 단일 대화 세션 유지 (항상 1개만 관리)
            sessions = db_manager.get_sessions(current_user_id)
            if sessions:
                user_sid = sessions[0]["session_id"]
            else:
                user_sid = f"sess_{current_user_id}"
                db_manager.create_session(current_user_id, user_sid, "종합 투자분석 대화")
            st.session_state.current_session_id = user_sid

            # 대화 초기화 버튼
            if st.button("🧹 대화 초기화", use_container_width=True):
                db_manager.clear_session_messages(user_sid)
                task_manager.clear_task(user_sid)
                st.toast("대화 내용이 초기화되었습니다.", icon="🧹")
                st.rerun()


    # 2. 메시지 히스토리 로드 (회원은 DB, 게스트는 session_state)
    if is_guest:
        if "guest_session_id" not in st.session_state:
            st.session_state.guest_session_id = f"guest_{uuid.uuid4().hex[:8]}"
        if "guest_messages" not in st.session_state:
            st.session_state.guest_messages = []
        messages = st.session_state.guest_messages
        thread_id = st.session_state.guest_session_id
    else:
        thread_id = st.session_state.current_session_id

    # 백그라운드 태스크 상태 점검 및 완료 동기화
    task = task_manager.get_task(thread_id)
    is_running = (task is not None and task.get("status") == "running")

    if task and task.get("status") == "done":
        if is_guest:
            resp_text = task.get("response")
            if resp_text and (not st.session_state.guest_messages or st.session_state.guest_messages[-1].get("role") != "assistant"):
                st.session_state.guest_messages.append({"role": "assistant", "content": resp_text})
        task_manager.clear_task(thread_id)
        task = None
        is_running = False
    elif task and task.get("status") == "error":
        if is_guest:
            err_text = f"⚠️ 기업 분석 실행 중 오류가 발생했습니다: {task.get('error')}"
            if not st.session_state.guest_messages or st.session_state.guest_messages[-1].get("role") != "assistant":
                st.session_state.guest_messages.append({"role": "assistant", "content": err_text})
        task_manager.clear_task(thread_id)
        task = None
        is_running = False

    # 최신 메시지 목록 로드
    if is_guest:
        messages = st.session_state.guest_messages
    else:
        messages = db_manager.get_messages(thread_id)

    # 메시지 화면 렌더링
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                # 모든 분석이 완료되었을 때 체크표시(complete) 상태 표시
                st.status("✅ 불곰 투자심의위원회(Bull-Gom) 심의 및 보고서 발행 완료 (5/5단계)", state="complete", expanded=False)

                verdict = extract_verdict(msg["content"])
                if verdict:
                    render_verdict_badge(verdict)

            display_content = re.sub(r"```json_financial_data\s*\{.*?\}\s*```", "", msg["content"], flags=re.DOTALL)
            st.markdown(display_content)
            
            fin_data = extract_financial_data(msg["content"])
            if fin_data:
                render_financial_chart(fin_data)

    # 실행 중인 경우 직관적인 실시간 심의 현황 UI 표출 (분석 중에는 항상 원이 도는 running 상태 유지)
    if is_running and task:
        with st.chat_message("assistant"):
            step_num = task.get("current_step", 1)
            elapsed = int(time.time() - task.get("start_time", time.time()))
            status_box = st.status(
                f"🐂 불곰 투자심의위원회(Bull-Gom) 심의 진행 중... ({step_num}/5단계) ⏱️ {elapsed}초",
                state="running",
                expanded=True
            )
            for step_text in task.get("completed_steps", []):
                status_box.markdown(f"- ✅ **완료**: {step_text}")
            cur_desc = task.get("step_desc", "")
            if cur_desc and cur_desc not in task.get("completed_steps", []):
                status_box.markdown(f"- ⏳ **진행 중**: {cur_desc}")
            status_box.caption("💡 다른 페이지로 이동하셔도 분석은 백그라운드에서 안전하게 완료되며 보고서가 보존됩니다.")

    # 3. 사용자 질문 입력 및 에이전트 실행
    if is_running:
        st.chat_input("⏳ 불곰 AI 분석가가 현재 기업을 심의 중입니다. 완료 후 다음 질문을 입력해주세요...", disabled=True)
        time.sleep(1.2)
        st.rerun()
    else:
        prompt = st.chat_input("분석할 기업명이나 종목코드를 입력하세요... (예: 삼성전자 최근 재무제표 및 투자 분석해줘)")
        if prompt:
            # 사용자 메시지 선저장 (유실 방지)
            if is_guest:
                st.session_state.guest_messages.append({"role": "user", "content": prompt})
            else:
                db_manager.add_message(thread_id, auth_user["user_id"], "user", prompt)
                if len(messages) == 0:
                    short_title = prompt[:20] + ("..." if len(prompt) > 20 else "")
                    db_manager.update_session_title(thread_id, short_title)

            # 백그라운드 비동기 워커에 작업 위임 (페이지 이동 시에도 중단되지 않음)
            user_id = auth_user["user_id"] if auth_user else "guest"
            task_manager.start_background_analysis(
                session_id=thread_id,
                user_id=user_id,
                prompt=prompt,
                is_guest=is_guest
            )
            st.rerun()

    # 보고서 열람/다운로드는 전용 [보고서 보관소] 페이지에서 제공
    pass

render_chat_page()


