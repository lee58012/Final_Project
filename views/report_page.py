import base64
import os
import shutil
from datetime import datetime
from pathlib import Path
import streamlit as st

import db_manager
from config import OUTPUT_DIR


def render_report_header():
    """상단 헤더 타이틀 (우측 상단 인증 UI는 완전히 삭제되고 사이드바로 이동됨)"""
    st.markdown("### 📑 보고서 관리 (Report Center)")
    st.caption("불곰(Bull-Gom) AI가 심의 후 생성한 기업 분석 PDF 보고서를 열람하고 다운로드합니다.")


def get_user_reports(user_id: str):
    """로그인 사용자의 모든 세션에서 생성된 PDF 보고서 목록 수집"""
    db_manager.init_db()
    sessions = db_manager.get_sessions(user_id)
    reports = []

    for sess in sessions:
        sid = sess["session_id"]
        stitle = sess["title"]
        s_dir = OUTPUT_DIR / sid
        if s_dir.exists():
            for pf in s_dir.glob("*.pdf"):
                stat = pf.stat()
                reports.append({
                    "path": pf,
                    "filename": pf.name,
                    "session_id": sid,
                    "session_title": stitle,
                    "size_bytes": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime)
                })

    reports.sort(key=lambda r: r["updated_at"], reverse=True)
    return reports


def get_guest_reports(guest_session_id: str):
    """게스트 세션의 임시 PDF 보고서 목록 수집"""
    if not guest_session_id:
        return []
    g_dir = OUTPUT_DIR / guest_session_id
    reports = []
    if g_dir.exists():
        for pf in g_dir.glob("*.pdf"):
            stat = pf.stat()
            reports.append({
                "path": pf,
                "filename": pf.name,
                "session_id": guest_session_id,
                "session_title": "게스트 임시 세션",
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime)
            })
    reports.sort(key=lambda r: r["updated_at"], reverse=True)
    return reports


def render_pdf_preview(pdf_path: Path):
    """PDF 파일을 브라우저에 임베드하여 미리보기 제공"""
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf" style="border-radius: 8px; border: 1px solid #e5e7eb;"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)


def render_report_page():
    # 새로고침 시 로그인 복원: query_params에 토큰이 있으면 자동 로그인
    if st.session_state.get("auth_user") is None:
        token = st.query_params.get("token")
        if token:
            restored_user = db_manager.verify_login_token(token)
            if restored_user:
                st.session_state.auth_user = restored_user
            else:
                del st.query_params["token"]

    auth_user = st.session_state.get("auth_user")

    with st.sidebar:
        st.header("📑 보고서 보관소 안내")
        if auth_user:
            st.success(f"👤 **{auth_user['username']}**님의 보관함")
            user_cols = st.columns([1.7, 1.3])
            with user_cols[0]:
                st.caption(f"아이디: `{auth_user['user_id']}`")
            with user_cols[1]:
                if st.button("로그아웃", key="rep_sb_logout", use_container_width=True):
                    db_manager.delete_login_token(auth_user["user_id"])
                    if "token" in st.query_params:
                        del st.query_params["token"]
                    st.session_state.auth_user = None
                    if "current_session_id" in st.session_state:
                        del st.session_state["current_session_id"]
                    st.rerun()
            st.caption("기업 분석 진행 시 생성된 모든 고품질 PDF 보고서가 회원 계정에 안전하게 보관됩니다.")
        else:
            st.info("🔒 **게스트 임시 보관함**\n\n브라우저 종료 또는 세션 초기화 시 임시 파일은 파기되므로, 영구 보관을 원하시면 아래에서 로그인 또는 회원가입하세요.")
            with st.popover("🔑 로그인 / 회원가입", use_container_width=True):
                tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

                with tab_login:
                    with st.form("rep_login_form"):
                        st.markdown("##### 기존 회원 로그인")
                        login_id = st.text_input("아이디", key="rep_login_id")
                        login_pw = st.text_input("비밀번호", type="password", key="rep_login_pw")
                        if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                            user_info = db_manager.login_user(login_id, login_pw)
                            if user_info:
                                st.session_state.auth_user = user_info
                                token = db_manager.create_login_token(user_info["user_id"])
                                st.query_params["token"] = token
                                st.success(f"{user_info['username']}님 환영합니다!")
                                st.rerun()
                            else:
                                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

                with tab_signup:
                    with st.form("rep_signup_form"):
                        st.markdown("##### 신규 회원가입")
                        signup_id = st.text_input("새 아이디", key="rep_signup_id")
                        signup_name = st.text_input("닉네임", key="rep_signup_name")
                        signup_pw = st.text_input("새 비밀번호", type="password", key="rep_signup_pw")
                        if st.form_submit_button("회원가입", use_container_width=True):
                            success, msg = db_manager.signup_user(signup_id, signup_name, signup_pw)
                            if success:
                                new_user = {"user_id": signup_id.strip(), "username": signup_name.strip()}
                                st.session_state.auth_user = new_user
                                token = db_manager.create_login_token(new_user["user_id"])
                                st.query_params["token"] = token
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    render_report_header()
    st.markdown("---")

    if not auth_user:
        # 게스트 모드
        guest_sid = st.session_state.get("guest_session_id", "")
        reports = get_guest_reports(guest_sid)

        st.warning(
            "🔒 **현재 게스트 모드로 접속 중입니다.**\n\n"
            "게스트 상태에서 생성된 보고서는 현재 브라우저 세션에만 임시 보관되며, "
            "로그인하거나 브라우저를 닫으면 자동으로 영구 삭제됩니다.\n\n"
            "보고서를 영구 보관하고 관리하시려면 좌측 사이드바에서 **로그인 또는 회원가입**을 진행해주세요."
        )

        if not reports:
            st.info("💡 아직 생성된 임시 보고서가 없습니다. **[투자 분석하기]** 탭에서 관심 기업에 대한 분석을 시작해보세요!")
            return
    else:
        # 회원 모드
        reports = get_user_reports(auth_user["user_id"])

    # 요약 통계 카드
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("총 저장 보고서", f"{len(reports)}건")
    with col_stat2:
        recent_date = reports[0]["updated_at"].strftime("%Y-%m-%d %H:%M") if reports else "-"
        st.metric("최근 생성 일시", recent_date)
    with col_stat3:
        total_size = sum(r["size_bytes"] for r in reports) / (1024 * 1024) if reports else 0
        st.metric("저장 용량", f"{total_size:.2f} MB")

    st.markdown("---")

    if not reports:
        st.info("💡 저장된 투자 분석 보고서가 없습니다. **[투자 분석하기]** 메뉴에서 기업 분석을 요청하시면 고품질 A4 PDF 보고서가 자동 생성됩니다.")
        return

    # 검색 필터
    search_keyword = st.text_input("🔍 보고서 파일명 또는 세션 검색", placeholder="예: 삼성전자, 현대차, 005930").strip().lower()

    filtered_reports = [
        r for r in reports
        if not search_keyword or search_keyword in r["filename"].lower() or search_keyword in r["session_title"].lower()
    ]

    st.markdown(f"총 **{len(filtered_reports)}**개의 보고서가 검색되었습니다.")

    # 보고서 카드 목록
    for idx, rep in enumerate(filtered_reports):
        with st.container():
            cols = st.columns([3, 1.2, 1, 0.8])
            with cols[0]:
                st.markdown(f"#### 📑 {rep['filename']}")
                st.caption(
                    f"분석 주제: **{rep['session_title']}** | "
                    f"생성 일시: `{rep['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}` | "
                    f"용량: `{rep['size_bytes']:,} bytes`"
                )

            with open(rep["path"], "rb") as f:
                pdf_bytes = f.read()

            with cols[1]:
                st.download_button(
                    label="📥 PDF 다운로드",
                    data=pdf_bytes,
                    file_name=rep["filename"],
                    mime="application/pdf",
                    key=f"rep_down_{rep['session_id']}_{idx}",
                    use_container_width=True
                )

            with cols[2]:
                view_key = f"view_pdf_{rep['session_id']}_{idx}"
                is_viewing = st.toggle("👁️ 미리보기", key=view_key)

            with cols[3]:
                if st.button("🗑️ 삭제", key=f"rep_del_{rep['session_id']}_{idx}", use_container_width=True):
                    rep["path"].unlink(missing_ok=True)
                    st.toast(f"'{rep['filename']}' 보고서가 삭제되었습니다.", icon="🗑️")
                    st.rerun()

            if is_viewing:
                with st.expander("📄 PDF 미리보기 창", expanded=True):
                    render_pdf_preview(rep["path"])

            st.markdown("<hr style='margin: 0.5rem 0; border: none; border-top: 1px solid #f0f2f6;'/>", unsafe_allow_html=True)


render_report_page()
