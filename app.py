import streamlit as st

st.set_page_config(
    page_title="불곰 (Bull-Gom) | AI 투자 분석가",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 0. 전역 DB 초기화 및 로그인 토큰 자동 복원 (새로고침 시 어느 페이지에서도 로그인 100% 유지)
import db_manager
db_manager.init_db()

if st.session_state.get("auth_user") is None:
    token = st.query_params.get("token")
    if token:
        restored_user = db_manager.verify_login_token(token)
        if restored_user:
            st.session_state.auth_user = restored_user
        else:
            if "token" in st.query_params:
                del st.query_params["token"]

# 로그인된 상태인데 URL에 토큰이 누락된 경우 URL 동기화 (페이지 이동 시 토큰 유실 방지)
if st.session_state.get("auth_user") and "token" not in st.query_params:
    user_id = st.session_state.auth_user.get("user_id")
    if user_id:
        token = db_manager.create_login_token(user_id)
        st.query_params["token"] = token

# 페이지 라우팅 (views 디렉토리 기반 modern st.navigation)
# 서비스 안내(소개) -> 종목 분석(채팅, 보고서) 순서로 배치
index_page = st.Page("views/index_page.py", title="서비스 소개 (불곰)", icon="🏠", default=True, url_path="index_page")
chat_page = st.Page("views/chat_page.py", title="종목 분석", icon="💬", url_path="chat_page")
report_page = st.Page("views/report_page.py", title="보고서 보관소", icon="📑", url_path="report_page")

pg = st.navigation({
    "서비스 안내": [index_page],
    "종목 분석": [chat_page, report_page]
})
pg.run()