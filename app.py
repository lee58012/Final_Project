import streamlit as st

st.set_page_config(
    page_title="불곰 (Bull-Gom) | AI 투자 분석가",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 페이지 라우팅
index_page = st.Page("pages/index_page.py", title="홈 / 불곰 소개", icon="🏠")
chat_page = st.Page("pages/chat_page.py", title="투자 분석가", icon="📊")

pg = st.navigation([index_page, chat_page])
pg.run()
