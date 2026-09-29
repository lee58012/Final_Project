import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db_manager
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
    """Plotly를 이용한 인터랙티브 3개년 실적 지표 및 차트 렌더링"""
    corp_name = fin_data.get("corp_name", "기업")
    years = [str(y) for y in fin_data.get("years", [])]
    revenue = fin_data.get("revenue", [])
    operating_profit = fin_data.get("operating_profit", [])
    net_profit = fin_data.get("net_profit", [])
    unit = fin_data.get("unit", "억원/원")

    if not years or not revenue:
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
        rev_delta = f"{pct:+.1f}% (전년비)"

    op_delta = None
    if len(operating_profit) >= 2 and operating_profit[-2] and isinstance(operating_profit[-1], (int, float)) and isinstance(operating_profit[-2], (int, float)):
        diff = operating_profit[-1] - operating_profit[-2]
        pct = (diff / abs(operating_profit[-2])) * 100 if operating_profit[-2] != 0 else 0
        op_delta = f"{pct:+.1f}% (전년비)"

    np_delta = None
    if len(net_profit) >= 2 and net_profit[-2] and isinstance(net_profit[-1], (int, float)) and isinstance(net_profit[-2], (int, float)):
        diff = net_profit[-1] - net_profit[-2]
        pct = (diff / abs(net_profit[-2])) * 100 if net_profit[-2] != 0 else 0
        np_delta = f"{pct:+.1f}% (전년비)"

    with col_m1:
        st.metric(
            label=f"최신 매출액 ({unit})",
            value=f"{latest_rev:,}" if isinstance(latest_rev, (int, float)) else str(latest_rev),
            delta=rev_delta
        )
    with col_m2:
        st.metric(
            label=f"최신 영업이익 ({unit})",
            value=f"{latest_op:,}" if isinstance(latest_op, (int, float)) else str(latest_op),
            delta=op_delta
        )
    with col_m3:
        st.metric(
            label=f"최신 당기순이익 ({unit})",
            value=f"{latest_np:,}" if isinstance(latest_np, (int, float)) else str(latest_np),
            delta=np_delta
        )

    # 2. 실적 추이 인터랙티브 차트
    with st.expander(f"📊 {corp_name} 연도별 실적 추이 차트 펼쳐보기", expanded=True):
        fig = go.Figure()

        # 매출액 바 차트
        fig.add_trace(go.Bar(
            x=years,
            y=revenue,
            name="매출액",
            marker_color="#2563EB",
            text=[f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in revenue],
            textposition="outside"
        ))

        # 영업이익 바 차트
        if operating_profit:
            fig.add_trace(go.Bar(
                x=years,
                y=operating_profit,
                name="영업이익",
                marker_color="#10B981",
                text=[f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in operating_profit],
                textposition="outside"
            ))

        # 당기순이익 라인 차트
        if net_profit:
            fig.add_trace(go.Scatter(
                x=years,
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
                text=f"{corp_name} 최근 3개년 주요 재무 실적 추이 ({unit})",
                font=dict(size=15)
            ),
            barmode="group",
            xaxis_title="결산 연도",
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
    """오른쪽 상단 회원가입 및 로그인 팝오버 UI"""
    col_title, col_auth = st.columns([3, 1.3])
    
    with col_title:
        st.markdown("### 🐂 불곰 (Bull-Gom) : AI 투자 분석가 🐻")

    with col_auth:
        auth_user = st.session_state.get("auth_user")
        
        if auth_user:
            # 로그인 상태
            user_cols = st.columns([2, 1])
            with user_cols[0]:
                st.markdown(f"👤 **{auth_user['username']}** 분석가님", help=f"아이디: {auth_user['user_id']}")
            with user_cols[1]:
                if st.button("로그아웃", key="btn_logout", use_container_width=True):
                    st.session_state.auth_user = None
                    if "current_session_id" in st.session_state:
                        del st.session_state["current_session_id"]
                    cleanup_guest_data()
                    st.rerun()
        else:
            # 게스트 상태 -> 로그인/회원가입 팝오버 제공
            with st.popover("👤 로그인 / 회원가입", use_container_width=True):
                tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
                
                with tab_login:
                    st.markdown("##### 기존 회원 로그인")
                    login_id = st.text_input("아이디", key="login_id")
                    login_pw = st.text_input("비밀번호", type="password", key="login_pw")
                    if st.button("로그인하기", key="btn_do_login", use_container_width=True, type="primary"):
                        user_info = db_manager.login_user(login_id, login_pw)
                        if user_info:
                            # 로그인 시 게스트 임시 보고서/대화 안전하게 파기
                            cleanup_guest_data()
                            st.session_state.auth_user = user_info
                            st.success(f"{user_info['username']}님 환영합니다!")
                            st.rerun()
                        else:
                            st.error("아이디 또는 비밀번호가 일치하지 않습니다.")

                with tab_signup:
                    st.markdown("##### 신규 회원가입")
                    signup_id = st.text_input("새 아이디", key="signup_id")
                    signup_name = st.text_input("닉네임(이름)", key="signup_name")
                    signup_pw = st.text_input("새 비밀번호", type="password", key="signup_pw")
                    if st.button("가입 및 자동 로그인", key="btn_do_signup", use_container_width=True):
                        success, msg = db_manager.signup_user(signup_id, signup_name, signup_pw)
                        if success:
                            # 회원가입 및 로그인 시 게스트 임시 보고서/대화 안전하게 파기
                            cleanup_guest_data()
                            st.session_state.auth_user = {"user_id": signup_id.strip(), "username": signup_name.strip()}
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)


def render_chat_page():
    # DB 초기화
    db_manager.init_db()

    # 상단 헤더 & 우측 상단 인증 UI 렌더링
    render_auth_header()

    auth_user = st.session_state.get("auth_user")
    is_guest = auth_user is None

    # 1. 왼쪽 사이드바 구성 (회원 vs 게스트 분기)
    with st.sidebar:
        if is_guest:
            st.header("👤 게스트 모드")
            st.info("""
            **현재 게스트 모드로 접속 중입니다.**
            
            - 게스트 분석 대화 및 생성된 PDF 보고서는 **영구 저장되지 않으며**, 브라우저를 닫거나 로그인/초기화 시 **자동으로 영구 파기**됩니다.
            - 분석 보고서와 대화 내역을 계속 보존하고 관리하시려면 **우측 상단 [로그인/회원가입]**을 진행해주세요.
            """)
            if st.button("🧹 현재 분석 비우기", use_container_width=True):
                cleanup_guest_data()
                st.rerun()
        else:
            st.header(f"🗂️ {auth_user['username']} 분석가의 분석실")
            current_user_id = auth_user["user_id"]
            sessions = db_manager.get_sessions(current_user_id)

            if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
                if sessions:
                    st.session_state.current_session_id = sessions[0]["session_id"]
                else:
                    init_sid = str(uuid.uuid4())
                    db_manager.create_session(current_user_id, init_sid, "새로운 기업 분석")
                    st.session_state.current_session_id = init_sid
                    sessions = db_manager.get_sessions(current_user_id)

            # 새 기업 분석 시작
            if st.button("➕ 새 기업 분석 시작", use_container_width=True, type="primary"):
                new_sid = str(uuid.uuid4())
                db_manager.create_session(current_user_id, new_sid, "새로운 기업 분석")
                st.session_state.current_session_id = new_sid
                st.rerun()

            # 이전 분석 목록 라디오
            session_titles = {s["session_id"]: s["title"] for s in sessions}
            if session_titles:
                current_idx = list(session_titles.keys()).index(st.session_state.current_session_id) \
                    if st.session_state.current_session_id in session_titles else 0
                
                selected_sid = st.radio(
                    "분석 목록",
                    options=list(session_titles.keys()),
                    format_func=lambda sid: session_titles[sid],
                    index=current_idx
                )
                if selected_sid != st.session_state.current_session_id:
                    st.session_state.current_session_id = selected_sid
                    st.rerun()

            # 현재 분석 삭제
            if st.session_state.get("current_session_id"):
                if st.button("🗑️ 현재 분석 삭제", use_container_width=True):
                    sid = st.session_state.current_session_id
                    db_manager.delete_session(sid)
                    sess_report_dir = OUTPUT_DIR / sid
                    if sess_report_dir.exists():
                        shutil.rmtree(sess_report_dir, ignore_errors=True)
                    st.session_state.current_session_id = None
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
        current_session_id = st.session_state.get("current_session_id")
        if not current_session_id:
            st.info("왼쪽 사이드바에서 분석을 선택하거나 새 분석을 시작하세요.")
            return
        messages = db_manager.get_messages(current_session_id)
        thread_id = current_session_id

    # 메시지 화면 렌더링
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                verdict = extract_verdict(msg["content"])
                if verdict:
                    render_verdict_badge(verdict)

            display_content = re.sub(r"```json_financial_data\s*\{.*?\}\s*```", "", msg["content"], flags=re.DOTALL)
            st.markdown(display_content)
            
            fin_data = extract_financial_data(msg["content"])
            if fin_data:
                render_financial_chart(fin_data)

    # 3. 사용자 질문 입력 및 에이전트 실행
    prompt = st.chat_input("분석할 기업명이나 종목코드를 입력하세요... (예: 삼성전자 최근 재무제표 및 투자 분석해줘)")

    if prompt:
        # 사용자 메시지 저장 (회원: DB, 게스트: session_state)
        if is_guest:
            st.session_state.guest_messages.append({"role": "user", "content": prompt})
        else:
            db_manager.add_message(current_session_id, auth_user["user_id"], "user", prompt)
            if len(messages) == 0:
                short_title = prompt[:20] + ("..." if len(prompt) > 20 else "")
                db_manager.update_session_title(current_session_id, short_title)

        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 에이전트 실행 (스레드 격리 비동기 루프로 안전하게 실행)
        with st.chat_message("assistant"):
            try:
                with st.spinner("🐂 불곰 투자 분석가(상승론 Bull vs 하락론 Bear vs CRO)가 DART 공시 팩트를 정밀 교차 검증 중입니다..."):
                    response_text = run_async_in_isolated_thread(
                        execute_agent,
                        prompt,
                        thread_id,
                    )

                if response_text:
                    # 심의 판정 배지 표출
                    verdict = extract_verdict(response_text)
                    if verdict:
                        render_verdict_badge(verdict)

                    # 화면 표출
                    display_content = re.sub(r"```json_financial_data\s*\{.*?\}\s*```", "", response_text, flags=re.DOTALL)
                    st.markdown(display_content)

                    # 재무 데이터 차트 렌더링
                    fin_data = extract_financial_data(response_text)
                    if fin_data:
                        render_financial_chart(fin_data)

                    # 응답 저장
                    if is_guest:
                        st.session_state.guest_messages.append({"role": "assistant", "content": response_text})
                    else:
                        db_manager.add_message(current_session_id, auth_user["user_id"], "assistant", response_text)
                else:
                    err_msg = "⚠️ 불곰 투자 분석가가 응답을 생성하지 못했습니다. 질문을 다시 입력해주세요."
                    st.warning(err_msg)
                    if is_guest:
                        st.session_state.guest_messages.append({"role": "assistant", "content": err_msg})
                    else:
                        db_manager.add_message(current_session_id, auth_user["user_id"], "assistant", err_msg)

            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Ctrl+C detected.")
                raise
            except asyncio.CancelledError:
                print("\n[SHUTDOWN] Task cancelled.")
                raise
            except Exception as e:
                err_msg = f"⚠️ 기업 분석 실행 중 오류가 발생했습니다: {str(e)}"
                st.error(err_msg)
                if is_guest:
                    st.session_state.guest_messages.append({"role": "assistant", "content": err_msg})
                else:
                    db_manager.add_message(current_session_id, auth_user["user_id"], "assistant", err_msg)

        st.rerun()

    # 4. 하단: 투자 분석 보고서 섹션 (당사자 소유권 격리 & PDF 전용)
    current_session_dir = OUTPUT_DIR / thread_id
    current_files = []
    if current_session_dir.exists():
        current_files = sorted(
            list(current_session_dir.glob("*.pdf")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

    st.markdown("---")
    # A. 현재 분석 보고서 섹션
    with st.expander(f"📁 현재 분석 투자 보고서 ({len(current_files)}건)", expanded=bool(current_files)):
        if is_guest:
            st.caption("🔒 *게스트 모드 안내: 보고서는 현재 세션에만 임시 보관되며, 사이트를 닫거나 로그인/초기화 시 영구 파기됩니다.*")

        if current_files:
            for sf in current_files:
                cols = st.columns([3, 1.2, 0.8])
                with cols[0]:
                    st.markdown(f"📑 **{sf.name}**")
                    st.caption(f"형식: PDF 문서 | 크기: {sf.stat().st_size:,} bytes")
                
                with open(sf, "rb") as f:
                    pdf_bytes = f.read()

                with cols[1]:
                    st.download_button(
                        label="📥 PDF 다운로드",
                        data=pdf_bytes,
                        file_name=sf.name,
                        mime="application/pdf",
                        key=f"down_pdf_{thread_id}_{sf.name}",
                        use_container_width=True
                    )
                with cols[2]:
                    if st.button("🗑️ 삭제", key=f"del_{thread_id}_{sf.name}", use_container_width=True):
                        sf.unlink(missing_ok=True)
                        st.toast(f"'{sf.name}' 보고서가 삭제되었습니다.", icon="🗑️")
                        st.rerun()
        else:
            st.caption("현재 분석에서 생성된 PDF 보고서가 없습니다. (기업 분석 질문 시 자동으로 고품질 PDF 보고서가 생성됩니다.)")

    # B. 내 이전 분석 보고서 목록 (로그인 회원 본인의 세션 보고서만 조회)
    if not is_guest and auth_user:
        my_sessions = db_manager.get_sessions(auth_user["user_id"])
        my_session_map = {s["session_id"]: s["title"] for s in my_sessions}
        
        my_other_files = []
        for sid, stitle in my_session_map.items():
            if sid == thread_id:
                continue
            s_dir = OUTPUT_DIR / sid
            if s_dir.exists():
                for pf in s_dir.glob("*.pdf"):
                    my_other_files.append((pf, sid, stitle))

        if my_other_files:
            my_other_files.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
            with st.expander(f"🗂️ 내 이전 분석 보고서 목록 ({len(my_other_files)}건)"):
                for sf, sid, stitle in my_other_files:
                    cols = st.columns([3, 1.2, 0.8])
                    with cols[0]:
                        st.markdown(f"📑 **{sf.name}**  *(분석: `{stitle[:12]}...`)*" if len(stitle) > 12 else f"📑 **{sf.name}**  *(분석: `{stitle}`)*")
                        st.caption(f"형식: PDF 문서 | 크기: {sf.stat().st_size:,} bytes")

                    with open(sf, "rb") as f:
                        pdf_bytes = f.read()

                    with cols[1]:
                        st.download_button(
                            label="📥 PDF 다운로드",
                            data=pdf_bytes,
                            file_name=sf.name,
                            mime="application/pdf",
                            key=f"down_other_pdf_{sid}_{sf.name}",
                            use_container_width=True
                        )
                    with cols[2]:
                        if st.button("🗑️ 삭제", key=f"del_other_{sid}_{sf.name}", use_container_width=True):
                            sf.unlink(missing_ok=True)
                            st.toast(f"'{sf.name}' 보고서가 삭제되었습니다.", icon="🗑️")
                            st.rerun()

render_chat_page()


