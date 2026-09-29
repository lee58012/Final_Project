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
MODEL_NAME = "gemini-3.6-flash"

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
1. **Fact-First 원칙**: 오직 아래 제공된 [Context Data] 내의 팩트, 재무 수치, 공시, 뉴스 내용만을 근거로 분석하세요.
2. **환각 엄금**: [Context Data]에 명시되지 않은 실적 추정치, 매출액, 목표가 등의 숫자를 임의로 추정하거나 지어내지 마세요. 데이터가 부족한 영역은 '데이터 미확인' 또는 '추가 확인 필요'로 표기하세요.
3. **낙관적 분석**: 확인된 팩트를 바탕으로 기업의 성장 촉매(Catalyst), 경제적 해자(Moat), 밸류에이션 리레이팅 가능성을 분석하세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data (공시, 재무, 뉴스 등)]:
{context_data}

# 출력 형식
## 🟢 Bull Case 분석 보고서
1. **핵심 성장 동력 (Catalyst)**: (데이터에 명시된 팩트 기반 2~3가지)
2. **경쟁 우위 및 해자**: (제품력, 시장 점유율, 고객 락인 등)
3. **단기/중기 실적 모멘텀**: (확인된 재무 지표 및 가이던스 기반)
4. **미확인/추가 검증 필요 지표**: (데이터 부재로 확인되지 않은 잠재 변수)
"""

# [노드 2: Bear Analyst 프롬프트]
BEAR_PROMPT_TEMPLATE = """# 역할
당신은 냉철한 숏(Short) 포지션 전문 헤지펀드 매니저입니다.

# 핵심 원칙 및 제약 사항
1. **Fact-First 원칙**: 오직 제공된 [Context Data]와 [Bull Case 분석]에 근거하여 비판하세요. 없는 악재를 상상으로 지어내지 마세요.
2. **논리적 허점 공략**: Bull Case에서 지나치게 낙관적으로 해석된 지표, 간과된 하방 리스크(경쟁 심화, 마진 훼손, 지분 희석, 부채 만기 등)를 날카롭게 짚어내세요.
3. **숫자 엄밀성**: 데이터에 없는 수치를 인용하지 말고, 불확실성이 존재하는 항목은 '추정 불가' 또는 '리스크 요인'으로 분류하세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data (공시, 재무, 뉴스 등)]:
{context_data}

[Bull Case 분석]:
{bull_analysis}

# 출력 형식
## 🔴 Bear Case 반박 보고서
1. **Bull Case 논리 반박**: (상승 논리 중 가장 취약하거나 과장된 전제 지적)
2. **핵심 하방 리스크 (Downside Risk)**: (재무 건전성, 희석 리스크, 매크로 영향 등)
3. **최악의 시나리오 (Worst-case)**: (실적 둔화 시 발생 가능한 충격)
4. **리스크 불확실성 항목**: (데이터가 부족하여 하방 폭을 가늠하기 어려운 지점)
"""

# [노드 3: Chief Risk Officer (CRO) 프롬프트]
CRO_PROMPT_TEMPLATE = """# 역할
당신은 자산 보전과 리스크-리워드 밸런스를 책임지는 최고 위험 관리 책임자(CRO)입니다.

# 엄격한 가드레일 (환각 방지)
- **절대적 원칙**: [Context Data], [Bull Case], [Bear Case]에 직접 언급되거나 계산 가능한 수치 외에, **새로운 실적 추정치, 목표 주가, 밸류에이션 배수(PER 등)를 임의로 창작하는 행위를 절대 금지**합니다.
- 데이터가 부족하여 특정 리스크나 밸류에이션을 산정하기 어렵다면 숫자를 지어내지 말고 반드시 **"데이터 미제공으로 확인 불가 (Unverified)"**로 명시하세요.
- 양비론적 절충을 지양하고, 확인된 데이터의 신뢰도와 감내 가능한 위험 수준을 바탕으로 명확한 의사결정을 내리세요.

# 입력 데이터
[종목명/티커]: {ticker}
[Context Data (공시, 재무, 뉴스 등)]:
{context_data}

[Bull Case]:
{bull_analysis}

[Bear Case]:
{bear_analysis}

# 출력 형식
## ⚖️ 최종 투자 심의 위원회 의결서
1. **종합 평가 요약**: (양측 주장의 타당성과 팩트 정합성 비교)
2. **최종 투자 판정**: [적극 매수 / 분할 매수 / 중립(관망) / 비중 축소(매도)] 중 택1
3. **권장 포트폴리오 비중**: (0% ~ 10% 범위 내 제시, 불확실성이 크면 0% 또는 최소 비중 권고)
4. **위험 관리 가이드라인**:
   - 목표 및 익절 기준
   - 손절(Stop-loss) 가이드라인
   - 즉시 포지션 축소/청산 트리거 (조건 명시)
5. **데이터 한계 및 모니터링 필요 항목**: (데이터 미제공으로 결론에서 배제된 주요 미확인 지표)
"""

# 하위 호환용 전체 프롬프트
SYSTEM_PROMPT = BULL_PROMPT_TEMPLATE + "\n" + BEAR_PROMPT_TEMPLATE + "\n" + CRO_PROMPT_TEMPLATE

def validate_environment() -> Tuple[bool, list]:
    """시스템 필수 환경 구성 유효성 검사"""
    issues = []
    if not GEMINI_API_KEY:
        issues.append("GEMINI_API_KEY가 누락되었습니다.")
    if not DART_API_KEY:
        issues.append("DART_API_KEY가 누락되었습니다.")
    return len(issues) == 0, issues
