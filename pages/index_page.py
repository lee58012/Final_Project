import streamlit as st
from config import GEMINI_API_KEY, DART_API_KEY

def render_index_page():
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0;'>
            <h1 style='color: #1E3A8A; margin-bottom: 0.5rem;'>🐂 불곰 (Bull-Gom) : AI 투자 분석가 🐻</h1>
            <h3 style='color: #2563EB; font-weight: 500; margin-top: 0;'>상승론자(Bull)와 하락론자(Bear/곰)의 찬반 격돌 & 리스크 검증 시스템</h3>
            <p style='color: #4B5563; font-size: 1.15rem; max-width: 800px; margin: 0 auto;'>
                단일 AI의 확증 편향을 깨기 위해, <b>황소(Bull)</b>의 강력한 성장 모멘텀 발굴과 <b>곰(Bear)</b>의 냉혹한 숏 관점 반박을 교차 검증하여<br>
                최고위험관리자(CRO)가 객관적이고 균형 잡힌 최종 투자 판단 및 PDF 보고서를 제공합니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # API 설정 상태 카드
    st.subheader("🔑 시스템 환경 설정 현황")
    col1, col2 = st.columns(2)
    
    with col1:
        if GEMINI_API_KEY:
            st.success("✅ **Google Gemini API**: 연동 완료 (`gemini-3.6-flash`)")
        else:
            st.error("❌ **Google Gemini API**: 미설정 (`.env` 파일에 `GEMINI_API_KEY` 필요)")
            st.caption("AI Studio (https://aistudio.google.com/)에서 무료 키를 발급받으세요.")

    with col2:
        if DART_API_KEY:
            st.success("✅ **Open DART API**: 연동 완료 (공시/재무제표 조회 활성화)")
        else:
            st.warning("⚠️ **Open DART API**: 미설정 (`.env` 파일에 `DART_API_KEY` 필요)")
            st.caption("공시포털 (https://opendart.fss.or.kr/)에서 무료 인증키를 발급받으세요.")

    st.markdown("---")

    # 3인의 투자 심의 위원 소개
    st.subheader("👥 투자 심의 위원회(IC) 3인 구성")
    col_bull, col_bear, col_cro = st.columns(3)

    with col_bull:
        st.markdown("""
        <div style='background: #ECFDF5; padding: 1.2rem; border-radius: 10px; border-left: 5px solid #10B981;'>
            <h4 style='color: #065F46; margin-top:0;'>🟢 1. Bull Analyst</h4>
            <p style='color: #047857; font-size: 0.9rem;'><b>상승론자 관점</b></p>
            <ul style='color: #064E3B; font-size: 0.9rem; padding-left: 1.2rem;'>
                <li>핵심 성장 촉매(Catalyst) 3가지</li>
                <li>밸류에이션 리레이팅(Re-rating) 가능성</li>
                <li>경쟁 우위 요소 및 경제적 해자(Moat)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col_bear:
        st.markdown("""
        <div style='background: #FEF2F2; padding: 1.2rem; border-radius: 10px; border-left: 5px solid #EF4444;'>
            <h4 style='color: #991B1B; margin-top:0;'>🔴 2. Bear Analyst</h4>
            <p style='color: #B91C1C; font-size: 0.9rem;'><b>하락론자 관점</b></p>
            <ul style='color: #7F1D1D; font-size: 0.9rem; padding-left: 1.2rem;'>
                <li>Bull의 핵심 논리 중 가장 취약한 점 반박</li>
                <li>최악의 시나리오 및 마진 악화 요인</li>
                <li>DART 공시 기반 지분 희석(CB/BW/증자) 위험</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col_cro:
        st.markdown("""
        <div style='background: #EFF6FF; padding: 1.2rem; border-radius: 10px; border-left: 5px solid #3B82F6;'>
            <h4 style='color: #1E40AF; margin-top:0;'>⚖️ 3. Chief Risk Officer</h4>
            <p style='color: #1D4ED8; font-size: 0.9rem;'><b>위원장 / 리스크 관리자</b></p>
            <ul style='color: #1E3A8A; font-size: 0.9rem; padding-left: 1.2rem;'>
                <li>기대수익 대비 하방위험(Risk-Reward) 평가</li>
                <li><b>승인 판정</b>: 적극매수/분할매수/중립/매도</li>
                <li>권장 포트폴리오 비중(%) & 손절선 설정</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 빠른 시작 가이드
    st.info("""
    👉 **투자 심의 시작하는 방법**:
    1. 왼쪽 메뉴에서 **'⚖️ 투자 심의 회의실(IC)'** 페이지로 이동하세요.
    2. 게스트 모드로 즉시 분석을 체험하거나, **우측 상단 [로그인 / 회원가입]**을 통해 심의 보고서를 영구 저장할 수 있습니다.
    3. 심의 대상 기업명이나 종목코드를 입력하세요!
       - 예시: *"SK하이닉스에 대해 투자 심의를 진행해줘"*
       - 예시: *"삼성전자 Bull/Bear 격돌 분석 및 최종 비중 판정해줘"*
       - 예시: *"현대차 최근 DART 실적 기반으로 투자 심의 보고서 작성해줘"*
    """)

render_index_page()
