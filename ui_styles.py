import streamlit as st

def inject_global_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0');

:root {
    --md-sys-color-primary: #4edea3;
    --md-sys-color-on-primary: #003823;
    --md-sys-color-primary-container: #005235;
    --md-sys-color-on-primary-container: #6efac0;
    --md-sys-color-secondary: #ffb95f;
    --md-sys-color-on-secondary: #422c00;
    --md-sys-color-secondary-container: #5e4100;
    --md-sys-color-on-secondary-container: #ffddb6;
    --md-sys-color-tertiary: #ffb3ad;
    --md-sys-color-on-tertiary: #68000a;
    --md-sys-color-tertiary-container: #930013;
    --md-sys-color-on-tertiary-container: #ffdad7;
    --md-sys-color-error: #ffb4ab;
    --md-sys-color-error-container: #93000a;
    --md-sys-color-on-error: #690005;
    --md-sys-color-on-error-container: #ffdad6;
    --md-sys-color-background: #0f131c;
    --md-sys-color-on-background: #dfe2ee;
    --md-sys-color-surface: #0f131c;
    --md-sys-color-on-surface: #dfe2ee;
    --md-sys-color-surface-variant: #404854;
    --md-sys-color-on-surface-variant: #c0c7d5;
    --md-sys-color-outline: #8a919e;
    --md-sys-color-inverse-on-surface: #0f131c;
    --md-sys-color-inverse-surface: #dfe2ee;
    --md-sys-color-inverse-primary: #006c47;
    --md-sys-color-surface-tint: #4edea3;
    --md-sys-color-outline-variant: #404854;
    --md-sys-color-scrim: #000000;
    
    /* Custom surface containers from spec */
    --surface-container-lowest: #0a0e16;
    --surface-container-low: #181c24;
    --surface-container: #1c2028;
    --surface-container-high: #262a33;
    --surface-container-highest: #31353e;

    /* Up/Down colors */
    --semantic-up: #ffb3ad; /* Red for up in Korean market */
    --semantic-up-container: #930013;
    --semantic-down: #4edea3; /* Blue/Green for down */
    --semantic-down-container: #005235;
}

/* Global Typography */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: var(--md-sys-color-on-surface);
}

/* Hide Default Streamlit Menu & Footer, but keep Sidebar Collapse/Expand Toggle Button */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background: transparent !important;
    color: var(--md-sys-color-on-surface) !important;
}
header[data-testid="stHeader"] [data-testid="stToolbar"] {
    visibility: hidden;
}
header[data-testid="stHeader"] [data-testid="stDecoration"] {
    display: none;
}
/* Ensure the sidebar collapse / expand button is always visible */
[data-testid="stSidebarCollapseButton"],
button[data-testid="baseButton-headerNoPadding"],
header[data-testid="stHeader"] button {
    visibility: visible !important;
    display: inline-flex !important;
    color: var(--md-sys-color-primary) !important;
    background: transparent !important;
    z-index: 9999 !important;
}

/* Base App Background */
.stApp {
    background-color: var(--md-sys-color-background);
}

/* Sidebar Styling */
section[data-testid="stSidebar"] {
    background-color: var(--surface-container-low);
    border-right: 1px solid var(--md-sys-color-outline-variant);
}
section[data-testid="stSidebar"] > div {
    padding-top: 1rem;
}

/* Chat Message Styling */
.stChatMessage {
    background-color: var(--surface-container);
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 12px;
    border: 1px solid var(--md-sys-color-outline-variant);
}

/* Input Fields */
.stTextInput > div > div > input, 
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background-color: var(--surface-container-high);
    border: 1px solid var(--md-sys-color-outline-variant);
    color: var(--md-sys-color-on-surface);
    border-radius: 8px;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div:focus {
    border-color: var(--md-sys-color-primary);
    box-shadow: 0 0 0 1px var(--md-sys-color-primary);
}

/* Chat Input */
.stChatInputContainer {
    background-color: var(--surface-container-high) !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    border-radius: 16px !important;
}
.stChatInputContainer textarea {

}

/* Metric / Card Styling */
div[data-testid="stMetric"] {
    background-color: var(--surface-container);
    border-radius: 12px;
    padding: 16px;
    border: 1px solid var(--md-sys-color-outline-variant);
}
div[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
}
div[data-testid="stMetricDelta"] svg {
    display: none;
}

/* Buttons */
.stButton > button {
    border-radius: 8px;
    border: 1px solid var(--md-sys-color-outline-variant);
    background-color: var(--surface-container-high);
    color: var(--md-sys-color-on-surface);
    font-weight: 500;
    transition: all 0.2s ease;
}
.stButton > button:hover {
    border-color: var(--md-sys-color-primary);
    color: var(--md-sys-color-primary);
    background-color: var(--surface-container-highest);
}
/* Primary Button */
.stButton > button[data-baseweb="button"][kind="primary"] {
    background-color: var(--md-sys-color-primary);
    color: var(--md-sys-color-on-primary);
    border-color: var(--md-sys-color-primary);
}
.stButton > button[data-baseweb="button"][kind="primary"]:hover {
    background-color: var(--md-sys-color-primary-container);
    color: var(--md-sys-color-on-primary-container);
    border-color: var(--md-sys-color-primary-container);
}

/* Scrollbar Hiding */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: var(--md-sys-color-outline-variant);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--md-sys-color-outline);
}

/* Table Styling */
.stDataFrame {
    background-color: var(--surface-container);
    border-radius: 8px;
    border: 1px solid var(--md-sys-color-outline-variant);
}
.stDataFrame td, .stDataFrame th {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.875rem;
    color: var(--md-sys-color-on-surface);
    border-bottom: 1px solid var(--md-sys-color-outline-variant) !important;
}
.stDataFrame th {
    color: var(--md-sys-color-on-surface-variant);
    font-weight: 600;
    background-color: var(--surface-container-high) !important;
}

/* Expander */
.streamlit-expanderHeader {
    background-color: var(--surface-container);
    border: 1px solid var(--md-sys-color-outline-variant);
    border-radius: 8px;
    color: var(--md-sys-color-on-surface);
}
.streamlit-expanderContent {
    border: 1px solid var(--md-sys-color-outline-variant);
    border-top: none;
    border-radius: 0 0 8px 8px;
    background-color: var(--surface-container-low);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background-color: var(--surface-container-low);
    border-radius: 8px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 6px;
    padding: 8px 16px;
    color: var(--md-sys-color-on-surface-variant);
}
.stTabs [aria-selected="true"] {
    background-color: var(--surface-container-highest);
    color: var(--md-sys-color-on-surface);
}

/* Plotly charts container */
.stPlotlyChart {
    background-color: var(--surface-container);
    border-radius: 12px;
    padding: 16px;
    border: 1px solid var(--md-sys-color-outline-variant);
}

/* Custom CSS Classes */
.metric-up { color: var(--semantic-up); }
.metric-down { color: var(--semantic-down); }
.mono { font-family: 'JetBrains Mono', monospace; }

/* Custom Badge */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    background-color: var(--md-sys-color-primary-container);
    color: var(--md-sys-color-on-primary-container);
}

</style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=120)
def fetch_market_indices():
    """실시간 주요 시장 지수 및 환율 조회 (Yahoo Finance 기반 2분 캐시)"""
    import yfinance as yf
    tickers = {
        'KOSPI': '^KS11',
        'KOSDAQ': '^KQ11',
        'S&P 500': '^GSPC',
        'NASDAQ': '^IXIC',
        'USD/KRW': 'KRW=X'
    }
    defaults = {
        'KOSPI': {'val': '6,889.74', 'chg': '-2.70%', 'is_up': False},
        'KOSDAQ': {'val': '846.58', 'chg': '+0.25%', 'is_up': True},
        'S&P 500': {'val': '7,670.84', 'chg': '-0.17%', 'is_up': False},
        'NASDAQ': {'val': '26,797.54', 'chg': '-0.09%', 'is_up': False},
        'USD/KRW': {'val': '1,353.04', 'chg': '-0.11%', 'is_up': False},
    }
    data = {}
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            h = t.history(period='5d')
            if len(h) >= 2:
                curr = float(h['Close'].iloc[-1])
                prev = float(h['Close'].iloc[-2])
                chg = curr - prev
                pct = (chg / prev) * 100
                data[name] = {
                    'val': f'{curr:,.2f}',
                    'chg': f'{pct:+.2f}%',
                    'is_up': chg >= 0
                }
            elif len(h) == 1:
                curr = float(h['Close'].iloc[-1])
                data[name] = {'val': f'{curr:,.2f}', 'chg': '0.00%', 'is_up': True}
        except Exception:
            data[name] = defaults.get(name)

    for k, v in defaults.items():
        if k not in data or not data[k]:
            data[k] = v
    return data

def render_telemetry_bar():
    indices = fetch_market_indices()
    cols = st.columns(len(indices))
    for col, (name, info) in zip(cols, indices.items()):
        val = info.get('val', '-')
        chg = info.get('chg', '0.00%')
        with col:
            st.metric(
                label=name,
                value=val,
                delta=chg
            )

def render_bull_gom_header():
    header_html = (
        '<div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 2rem;">'
        '<div style="display: flex; align-items: center; gap: 12px;">'
        '<div style="font-size: 2.5rem;">🐻</div>'
        '<h1 style="margin: 0; font-size: 2rem; font-weight: 700; color: var(--md-sys-color-on-surface);">Bull-Gom</h1>'
        '</div>'
        '<p style="margin: 0; color: var(--md-sys-color-on-surface-variant); font-size: 1rem;">'
        '불곰 AI 투자 분석가 — Bull vs Bear 교차 검증 시스템'
        '</p>'
        '</div>'
    )
    st.html(header_html)
def get_icon(name):
    return f'<span class="material-symbols-outlined">{name}</span>'
