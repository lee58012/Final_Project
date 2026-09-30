import os
import sys
from pathlib import Path
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

# 1. 프로젝트 기본 경로 설정
BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

# 2. 데이터베이스 및 저장 폴더 경로 설정
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "financial_agent.db")

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 3. API 키 및 모델 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")
MODEL_LIGHT_NAME = os.getenv("MODEL_LIGHT_NAME", "gemini-3.8-flash")

# 3-0. 네트워크 및 작업 타임아웃 / 파라미터 상수
DEFAULT_HTTP_TIMEOUT = 5.0          # 단일 HTTP/API 요청 타임아웃 (초)
THREAD_POOL_TIMEOUT = 25.0         # 병렬 데이터 수집 쓰레드풀 최대 대기 시간 (초)
MAX_RAW_NEWS_COUNT = 30            # 원천 뉴스 수집 최대 건수
NEWS_RANKING_TOP_K = 5             # 선별할 핵심 뉴스 개수
MAX_SNIPPET_LENGTH = 140           # 토큰 최적화용 뉴스 요약 최대 글자수
NAVER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# 3-1. 국내 주요 상장 종목 은어/약어 사전
STOCK_ALIASES: Dict[str, str] = {
    # 대형 IT / 반도체
    "삼성전자": "삼성전자",
    "삼성전자우": "삼성전자우",
    "삼전": "삼성전자",
    "삼성": "삼성전자",
    "SK하이닉스": "SK하이닉스",
    "에스케이하이닉스": "SK하이닉스",
    "하이닉스": "SK하이닉스",
    "하닉": "SK하이닉스",
    "한미반도체": "한미반도체",
    "한미": "한미반도체",
    "한반": "한미반도체",
    "네이버": "NAVER",
    "카카오": "카카오",
    "카뱅": "카카오뱅크",
    "카카오뱅크": "카카오뱅크",
    "카페": "카카오페이",
    "카카오페이": "카카오페이",
    "엔씨": "엔씨소프트",
    "엔씨소프트": "엔씨소프트",
    "크랩": "크래프톤",
    "크래프톤": "크래프톤",

    # 2차전지
    "LG에너지솔루션": "LG에너지솔루션",
    "엘지에너지솔루션": "LG에너지솔루션",
    "엔솔": "LG에너지솔루션",
    "lg엔솔": "LG에너지솔루션",
    "엘지엔솔": "LG에너지솔루션",
    "에코프로": "에코프로",
    "에코프로비엠": "에코프로비엠",
    "에코비엠": "에코프로비엠",
    "에코머티": "에코프로머티",
    "포스코홀딩스": "POSCO홀딩스",
    "포홀": "POSCO홀딩스",
    "포스코": "POSCO홀딩스",
    "포스코퓨처엠": "포스코퓨처엠",
    "포퓨": "포스코퓨처엠",
    "LG화학": "LG화학",
    "엘지화학": "LG화학",
    "엘화": "LG화학",
    "삼성SDI": "삼성SDI",
    "삼스디": "삼성SDI",

    # 자동차 / 모빌리티
    "현대자동차": "현대자동차",
    "현대차": "현대자동차",
    "현차": "현대자동차",
    "기아": "기아",
    "기아차": "기아",
    "현대모비스": "현대모비스",
    "모비스": "현대모비스",

    # 바이오
    "삼성바이오로직스": "삼성바이오로직스",
    "삼바": "삼성바이오로직스",
    "셀트리온": "셀트리온",
    "셀트": "셀트리온",
    "알테오젠": "알테오젠",
    "알테": "알테오젠",
    "유한양행": "유한양행",
    "유한": "유한양행",

    # 조선 / 방산 / 중공업
    "한화에어로스페이스": "한화에어로스페이스",
    "한화에어로": "한화에어로스페이스",
    "에어로": "한화에어로스페이스",
    "한화오션": "한화오션",
    "한오": "한화오션",
    "삼성중공업": "삼성중공업",
    "삼중": "삼성중공업",
    "HD현대중공업": "HD현대중공업",
    "현대중공업": "HD현대중공업",
    "현중": "HD현대중공업",
    "한국항공우주": "한국항공우주",
    "카이": "한국항공우주",

    # 금융 / 지주
    "KB금융": "KB금융",
    "신한지주": "신한지주",
    "하나금융지주": "하나금융지주",
    "삼성물산": "삼성물산",
}

def normalize_ticker(name: str) -> str:
    """종목 은어/약어를 KOSPI/KOSDAQ 정식 상장 법인명으로 정규화"""
    if not name:
        return name
    clean = name.strip()
    if clean in STOCK_ALIASES:
        return STOCK_ALIASES[clean]
    for alias, official in STOCK_ALIASES.items():
        if alias.lower() == clean.lower():
            return official
    for alias, official in sorted(STOCK_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in clean:
            return official
    return clean

# 4. 파이썬 실행 인터프리터 경로 자동 확인 (가상환경 우선)
def resolve_python_executable() -> str:
    """실행 중인 환경 또는 프로젝트 내 .venv의 파이썬 인터프리터 경로를 안정적으로 반환"""
    if sys.prefix != sys.base_prefix:
        return sys.executable
    
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    exe_name = "python.exe" if os.name == "nt" else "python"
    venv_python = BASE_DIR / ".venv" / scripts_dir / exe_name
    
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

PYTHON_EXECUTABLE = resolve_python_executable()

# 5. MCP 서버 설정
MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "dart_server": {
        "transport": "stdio",
        "command": PYTHON_EXECUTABLE,
        "args": [str(BASE_DIR / "mcp_server" / "dart_server.py")]
    },
    "file_server": {
        "transport": "stdio",
        "command": PYTHON_EXECUTABLE,
        "args": [str(BASE_DIR / "mcp_server" / "file_server.py")]
    }
}

# ============================================================
# 6. 랭그래프(LangGraph) 노드별 전문 프롬프트 템플릿
# ============================================================

# [노드 1: Bull Analyst 프롬프트]
BULL_PROMPT_TEMPLATE = """# 역할
당신은 성장 잠재력과 모멘텀을 발굴하는 시니어 롱(Long) 전문 애널리스트입니다.

# 핵심 원칙 및 제약 사항
1. **Fact-First 원칙**: 오직 아래 제공된 [Context Data] 내의 실시간 시세, 최근 분기 실적(QoQ/YoY), DART 재무제표, 실시간 시장 뉴스만을 근거로 분석하세요.
2. **정량적 팩트 중심**: 데이터에 제시된 매출액, 영업이익률, 현재가, 밸류에이션(PER/PBR), 컨센서스 목표주가 등의 숫자를 적극 인용하여 구체적으로 서술하세요.
3. **성장 촉매 발굴**: 확인된 팩트를 바탕으로 기업의 성장 촉매(Catalyst), 주력 제품/기술 경쟁 우위, 밸류에이션 리레이팅 가능성을 설득력 있게 제시하세요.
4. **기업 가치 제고 요인 분석**: [Context Data]에 나타난 신사업 모멘텀, 자회사 가치, 수급 개선 요인이 기업의 펀더멘털과 밸류에이션에 미치는 긍정적 측면을 팩트에 기반하여 논증하세요.
5. **선별된 핵심 뉴스 및 촉매(Catalyst) 필수 반영**: [Context Data]의 [뉴스 인텔리전스 선별 핵심 촉매 및 리스크]에 제시된 고영향도 Catalyst(자회사 실적 턴어라운드 및 지분 가치, 대규모 수주, 차세대 주력 제품 공급 등)를 반드시 구체적으로 인용하여 롱(Long) 논거와 밸류에이션 리레이팅의 핵심 근거로 제시하세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data (공시, 재무, 실시간 시세, 분기실적, 컨센서스, 뉴스 등)]:
{context_data}

# 출력 형식
## 🟢 Bull Case 분석 보고서
1. **핵심 성장 동력 (Catalyst)**: (선별된 고영향도 뉴스 및 데이터에 명시된 팩트/분기 실적 급증 2~3가지)
2. **경쟁 우위 및 해자**: (주력 제품 경쟁력, 시장 점유율, 고객사 락인, 재무적 체력 등)
3. **단기/중기 실적 모멘텀**: (최근 분기 QoQ/YoY 실적, 사업 가치 재평가 및 연간 컨센서스 기반)
4. **미확인/추가 검증 필요 지표**: (단기 매크로 변수 등 잠재 체크 포인트)
"""

# [노드 2: Bear Analyst 프롬프트]
BEAR_PROMPT_TEMPLATE = """# 역할
당신은 냉철한 숏(Short) 포지션 전문 헤지펀드 매니저입니다.

# 핵심 원칙 및 제약 사항
1. **Fact-First 원칙**: 오직 제공된 [Context Data]와 [Bull Case 분석]에 근거하여 비판하세요.
2. **논리적 허점 공략**: Bull Case에서 낙관한 지표, 업황 사이클 둔화/피크아웃 위험, 부채 규모, 최근 외국인/기관 수급 이탈, 경쟁 심화 요인을 날카롭게 짚어내세요.
3. **단기 급락 및 시장 충격 이슈 집중 공략**: 최근 [Context Data]의 시장 뉴스 및 주가 변동성 데이터에 나타난 주가 하락/급락의 배후 요인(수급 이탈, 언론 보도 이슈, 지배구조/자회사 리스크, 실적 우려 등)을 구체적으로 인용하여 강력히 비판하세요.
4. **선별된 핵심 뉴스 및 리스크(Risk) 필수 공략**: [Context Data]의 [뉴스 인텔리전스 선별 핵심 촉매 및 리스크]에 제시된 고영향도 Risk(자회사 중복상장 논란, 주가 급락 촉발 요인, 대외 규제/지정학적 리스크 등)를 반드시 구체적으로 인용하여 하방 위험과 숏(Short) 논거의 핵심 근거로 비판하세요.
5. **숫자 엄밀성**: 데이터에 명시된 52주 변동폭, 최근 주가 조정 폭, 차입금 및 부채 지표를 정량적으로 인용하여 리스크를 논증하세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data (공시, 재무, 실시간 시세, 분기실적, 컨센서스, 뉴스 등)]:
{context_data}

[Bull Case 분석]:
{bull_analysis}

# 출력 형식
## 🔴 Bear Case 반박 보고서
1. **Bull Case 논리 반박**: (상승 논리 중 과장된 전제나 실적 착시 지적)
2. **핵심 하방 리스크 (Downside Risk)**: (선별된 고영향도 리스크 뉴스, 시장 충격 요인, 주가 급락 원인, 재무 건전성, 부채 부담 등)
3. **최악의 시나리오 (Worst-case)**: (업황 피크아웃 또는 실적 둔화 시 주가 충격 시나리오)
4. **리스크 불확실성 항목**: (지속 관찰이 필요한 주요 하방 변수)
"""

# [노드 3: Chief Investment Analyst 프롬프트]
ANALYST_SUMMARY_PROMPT_TEMPLATE = """# 역할
당신은 자산 운용 및 밸류에이션 전략을 총괄하는 **수석 투자분석가(Chief Investment Analyst)**입니다.

# 핵심 원칙 및 분석 가이드라인
1. **정량적 밸류에이션 결합**: [Context Data]의 **현재가**, **컨센서스 목표주가**, **최근 실적 추이(QoQ/YoY)**, **PER/PBR 밸류에이션**, **선별된 핵심 뉴스 모멘텀**을 종합하여 논리적 투자의견을 제시하세요.
2. **명확한 목표가 및 전략 제시**: 상투적인 표현을 지양하고, 구체적인 수치(목표주가, 기대수익률, 손절 기준 가격, 적정 비중)를 정량적으로 명시하세요.
3. Bull Case와 Bear Case의 쟁점을 균형 있게 종합하여 실전 투자자가 취해야 할 최적의 포트폴리오 전략을 도출하세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data]:
{context_data}

[Bull Case 분석]:
{bull_analysis}

[Bear Case 반박]:
{bear_analysis}

# 출력 형식
## 📊 수석 투자분석가 종합 분석 의견서
1. **투자 포인트 종합 요약**: (성장 촉매와 하방 리스크의 상호 작용 및 현 주가 반영도 평가)
2. **투자의견 (Investment Rating)**: [BUY(적극매수) / Overweight(분할매수) / Hold(중립) / Underweight(비중축소)] 중 택1
3. **권장 포트폴리오 편입 비중**: [X.X%] (사유 및 분할 매매 전략 명시)
4. **목표주가 및 위험관리 가이드라인**:
   - **목표주가 (Target Price)**: X,XXX,000원 (현재가 대비 기대수익률 +XX.X%, 밸류에이션 산정 근거 포함)
   - **손절선 (Stop-loss)**: X,XXX,000원 (현재가 대비 허용 손실률 -XX.X%, 기술적 지지선 기준)
   - **핵심 투자 전략 트리거 3가지**: (비중 확대/축소 조건 명시)
5. **밸류에이션 점검 및 추적 관찰 지표**: (향후 분기 실적 발표 및 주요 모니터링 변수)
"""

# 하위 호환용 별칭
CRO_PROMPT_TEMPLATE = ANALYST_SUMMARY_PROMPT_TEMPLATE

# 하위 호환용 전체 프롬프트
SYSTEM_PROMPT = BULL_PROMPT_TEMPLATE + "\n" + BEAR_PROMPT_TEMPLATE + "\n" + ANALYST_SUMMARY_PROMPT_TEMPLATE

def validate_environment() -> Tuple[bool, list]:
    """시스템 필수 환경 구성 유효성 검사"""
    issues = []
    if not GEMINI_API_KEY:
        issues.append("GEMINI_API_KEY가 누락되었습니다.")
    if not DART_API_KEY:
        issues.append("DART_API_KEY가 누락되었습니다.")
    return len(issues) == 0, issues
