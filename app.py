import streamlit as st

st.set_page_config(
    page_title="불곰 (Bull-Gom) | AI 투자 분석가",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="expanded"
)

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