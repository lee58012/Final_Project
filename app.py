import streamlit as st

st.set_page_config(
    page_title="가상 헤지펀드 투자 심의 위원회",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 페이지 라우팅
index_page = st.Page("pages/index_page.py", title="홈 / 위원회 안내", icon="🏠")
chat_page = st.Page("pages/chat_page.py", title="투자 심의 회의실(IC)", icon="⚖️")

pg = st.navigation([index_page, chat_page])
pg.run()
