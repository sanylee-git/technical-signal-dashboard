"""
기술적 신호 스캐너 (Technical Signal Dashboard)
- 즐겨찾기 종목/ETF의 BB·RSI 신호를 한눈에 스캔
- 개별 종목 BB·RSI 차트 상세 보기
- 탭2: 시장 내부지표 (균일가중지수 · 상승종목수)

실행:
  pip install streamlit pandas plotly yfinance
  pip install pykrx        # 탭2 시장 내부지표 (선택)
  streamlit run technical_signal_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf
import json
import os
import re
import warnings
import traceback
warnings.filterwarnings('ignore')

try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False


# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="기술적 신호 스캐너",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <meta name="google-adsense-account" content="ca-pub-9688338422874533">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9688338422874533"
         crossorigin="anonymous"></script>
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    [data-testid="stHeader"]               { display: none !important; }
    [data-testid="stToolbar"]              { display: none !important; }
    [data-testid="stDecoration"]           { display: none !important; }
    [data-testid="stStatusWidget"]         { display: none !important; }
    #MainMenu                              { display: none !important; }
    footer                                 { display: none !important; }
    [data-testid="stBottom"]              { display: none !important; }
    [data-testid="embeddedAppMetaInfoBar"] { display: none !important; }
    [class*="embeddedAppMetaInfoBar"]      { display: none !important; }
    [class*="EmbedToolbar"]               { display: none !important; }
    .stApp                                 { background-color: #0D0D0E !important; }
    [data-testid="stAppViewContainer"]     { background-color: #0D0D0E !important; }
    [data-testid="stVerticalBlock"]        { background-color: transparent !important; }
    [data-testid="stMainBlockContainer"]   { padding-top: 0rem !important; }
    .modebar                               { display: none !important; }
    </style>
""", unsafe_allow_html=True)


# ============================================================
# 상수
# ============================================================
_DIR = os.path.dirname(os.path.abspath(__file__))
FAVORITES_FILE = os.path.join(_DIR, "signal_favorites.json")

DEFAULT_FAVORITES = [
    {"code": "441800.KS",  "name": "TIME Korea플러스배당액티브 (441800)"},
    {"code": "446770.KS",  "name": "ACE 글로벌반도체TOP4 Plus (446770)"},
    {"code": "456600.KS",  "name": "TIME 글로벌AI인공지능액티브 (456600)"},
    {"code": "487240.KS",  "name": "KODEX AI전력핵심설비 (487240)"},
    {"code": "0041D0.KS",  "name": "KODEX 미국AI소프트웨어TOP10 (0041D0)"},
    {"code": "0173Y0.KS",  "name": "KODEX 미국AI광통신네트워크 (0173Y0)"},
    {"code": "251600.KS",  "name": "PLUS 고배당주채권혼합 (251600)"},
    {"code": "284430.KS",  "name": "KODEX 200미국채혼합 (284430)"},
    {"code": "448330.KS",  "name": "KODEX 삼성전자채권혼합 (448330)"},
    {"code": "0019K0.KS",  "name": "TIME 미국나스닥100채권혼합50액티브 (0019K0)"},
    {"code": "0025N0.KS",  "name": "TIGER TDF2045 적격 (0025N0)"},
    {"code": "442570.KS",  "name": "RISE TDF2050액티브 적격 (442570)"},
    {"code": "472170.KS",  "name": "TIGER 미국테크TOP10채권혼합 (472170)"},
    {"code": "491010.KS",  "name": "TIGER 글로벌AI전력인프라액티브 (491010)"},
    {"code": "0195S0.KS",  "name": "TIGER SK하이닉스단일종목레버리지 (0195S0)"},
    {"code": "0195R0.KS",  "name": "TIGER 삼성전자단일종목레버리지 (0195R0)"},
    {"code": "005930.KS",  "name": "삼성전자 (005930)"},
    {"code": "000660.KS",  "name": "SK하이닉스 (000660)"},
    {"code": "373220.KS",  "name": "LG에너지솔루션 (373220)"},
]

STOCK_SEARCH_LIST = [
    # 주요 국내 ETF
    {"code": "069500.KS", "name": "KODEX 200"},
    {"code": "091160.KS", "name": "KODEX 반도체"},
    {"code": "305720.KS", "name": "KODEX 2차전지산업"},
    {"code": "463250.KS", "name": "TIGER K방산&우주"},
    {"code": "244580.KS", "name": "KODEX 바이오"},
    {"code": "091170.KS", "name": "KODEX 은행"},
    {"code": "091180.KS", "name": "KODEX 자동차"},
    {"code": "365000.KS", "name": "TIGER 인터넷TOP10"},
    {"code": "494670.KS", "name": "TIGER 조선TOP10"},
    {"code": "434730.KS", "name": "HANARO 원자력iSelect"},
    {"code": "487240.KS", "name": "KODEX AI전력핵심설비"},
    {"code": "441800.KS", "name": "TIME Korea플러스배당액티브"},
    {"code": "446770.KS", "name": "ACE 글로벌반도체TOP4 Plus"},
    {"code": "456600.KS", "name": "TIME 글로벌AI인공지능액티브"},
    {"code": "0041D0.KS", "name": "KODEX 미국AI소프트웨어TOP10"},
    {"code": "0173Y0.KS", "name": "KODEX 미국AI광통신네트워크"},
    {"code": "251600.KS", "name": "PLUS 고배당주채권혼합"},
    {"code": "284430.KS", "name": "KODEX 200미국채혼합"},
    {"code": "448330.KS", "name": "KODEX 삼성전자채권혼합"},
    {"code": "0019K0.KS", "name": "TIME 미국나스닥100채권혼합50액티브"},
    {"code": "0025N0.KS", "name": "TIGER TDF2045 적격"},
    {"code": "442570.KS", "name": "RISE TDF2050액티브 적격"},
    {"code": "472170.KS", "name": "TIGER 미국테크TOP10채권혼합"},
    {"code": "445290.KS", "name": "KODEX K-로봇액티브"},
    {"code": "228790.KS", "name": "TIGER 화장품"},
    {"code": "300950.KS", "name": "KODEX 게임산업"},
    {"code": "102970.KS", "name": "KODEX 증권"},
    {"code": "117680.KS", "name": "KODEX 철강"},
    {"code": "377990.KS", "name": "TIGER Fn신재생에너지"},
    {"code": "266420.KS", "name": "KODEX 헬스케어"},
    {"code": "117700.KS", "name": "KODEX 건설"},
    {"code": "102110.KS", "name": "TIGER 200"},
    {"code": "266360.KS", "name": "KODEX K콘텐츠"},
    {"code": "228800.KS", "name": "TIGER 여행레저"},
    {"code": "438900.KS", "name": "HANARO Fn K-푸드"},
    # 주요 국내 종목
    {"code": "005930.KS", "name": "삼성전자"},
    {"code": "000660.KS", "name": "SK하이닉스"},
    {"code": "005380.KS", "name": "현대차"},
    {"code": "000270.KS", "name": "기아"},
    {"code": "329180.KS", "name": "HD현대중공업"},
    {"code": "012450.KS", "name": "한화에어로스페이스"},
    {"code": "042660.KS", "name": "한화오션"},
    {"code": "373220.KS", "name": "LG에너지솔루션"},
    {"code": "207940.KS", "name": "삼성바이오로직스"},
    {"code": "068270.KS", "name": "셀트리온"},
    {"code": "105560.KS", "name": "KB금융"},
    {"code": "055550.KS", "name": "신한지주"},
    {"code": "035420.KS", "name": "NAVER"},
    {"code": "035720.KS", "name": "카카오"},
    {"code": "066570.KS", "name": "LG전자"},
    {"code": "352820.KS", "name": "하이브"},
    {"code": "259960.KS", "name": "크래프톤"},
    {"code": "042700.KS", "name": "한미반도체"},
    {"code": "010130.KS", "name": "고려아연"},
    {"code": "003670.KS", "name": "포스코퓨처엠"},
    {"code": "196170.KQ", "name": "알테오젠"},
    {"code": "028300.KQ", "name": "HLB"},
    {"code": "247540.KQ", "name": "에코프로비엠"},
    {"code": "086520.KQ", "name": "에코프로"},
    {"code": "403870.KQ", "name": "HPSP"},
    {"code": "058470.KQ", "name": "리노공업"},
    {"code": "214150.KQ", "name": "클래시스"},
    {"code": "214450.KQ", "name": "파마리서치"},
    {"code": "041510.KQ", "name": "에스엠"},
    {"code": "035900.KQ", "name": "JYP Ent."},
    {"code": "067160.KQ", "name": "SOOP"},
    {"code": "189300.KQ", "name": "인텔리안테크"},
    {"code": "357780.KQ", "name": "솔브레인"},
    # 미국 ETF/지수/종목
    {"code": "^KS11", "name": "코스피"},
    {"code": "^KQ11", "name": "코스닥"},
    {"code": "^IXIC", "name": "나스닥"},
    {"code": "^GSPC", "name": "S&P500"},
    {"code": "SMH", "name": "반에크 반도체 ETF"},
    {"code": "NVDA", "name": "엔비디아"},
    {"code": "AMD", "name": "AMD"},
    {"code": "TSLA", "name": "테슬라"},
    {"code": "META", "name": "메타"},
    {"code": "GOOG", "name": "구글"},
    {"code": "AMZN", "name": "아마존"},
    {"code": "MSFT", "name": "마이크로소프트"},
    {"code": "AAPL", "name": "애플"},
    {"code": "TSM", "name": "TSMC"},
]

# 시장 내부지표용 대형주 바스켓 (pykrx API 호환 불가로 yfinance 대체)
_KOSPI_BASKET = [
    "005930.KS", "000660.KS", "207940.KS", "005380.KS", "000270.KS",
    "068270.KS", "035420.KS", "051910.KS", "028260.KS", "012330.KS",
    "066570.KS", "003550.KS", "035720.KS", "086790.KS", "055550.KS",
    "105560.KS", "032830.KS", "003490.KS", "034730.KS", "015760.KS",
    "009150.KS", "000810.KS", "010130.KS", "024110.KS", "096770.KS",
]
_KOSDAQ_BASKET = [
    "247540.KQ", "086520.KQ", "196170.KQ", "214150.KQ", "039030.KQ",
    "357780.KQ", "066970.KQ", "121600.KQ", "145020.KQ", "178920.KQ",
    "041510.KQ", "035900.KQ", "122870.KQ", "263720.KQ", "112040.KQ",
    "091990.KQ", "058470.KQ", "236200.KQ", "048410.KQ", "060310.KQ",
]

PERIOD_OPTIONS = {
    "1개월":   21,
    "3개월":   63,
    "6개월":   126,
    "9개월":   189,
    "1년":     252,
    "1년 6개월": 378,
    "2년":     504,
}


# ============================================================
# 다크 테마 CSS (기존 대시보드와 동일)
# ============================================================
DARK_CSS = """
<style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }
    .stApp { background-color: #0D0D0E !important; }
    .main .block-container { padding: 1rem 2rem; max-width: 1400px; }

    section[data-testid="stSidebar"] {
        width: 260px !important; background: #111113 !important;
        border-right: 1px solid rgba(255,255,255,0.08) !important; }
    div[data-testid="stSidebarContent"] { padding: 6px 12px; }
    div[data-testid="stSidebarContent"] p strong {
        color: #777 !important; font-size: 14px !important;
        line-height: 20px !important; font-weight: 600 !important; }
    div[data-testid="stSidebarContent"] hr { margin: 4px 0 !important; border-color: rgba(255,255,255,0.06); }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0; background: transparent;
        border-bottom: 1px solid rgba(255,255,255,0.08); border-radius: 0; padding: 0; }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px; font-weight: 500; font-size: 13px; border-radius: 0;
        color: #666; border-bottom: 2px solid transparent; transition: color 0.15s ease;
        background: transparent !important; }
    .stTabs [data-baseweb="tab"]:hover { color: #9B9B9B; background: transparent !important; }
    .stTabs [aria-selected="true"] {
        color: #EDEDED !important; border-bottom-color: #787EE7 !important;
        background: transparent !important; }
    .stTabs [data-baseweb="tab-highlight"] { background-color: #787EE7 !important; }
    .stTabs [data-baseweb="tab-border"] { display: none; }

    .stRadio > div { gap: 0px !important; }
    section[data-testid="stSidebar"] .stRadio [data-testid="stWidgetLabel"] { display: none !important; }
    .stRadio label {
        padding: 3px 10px !important; border-radius: 6px !important; font-size: 11px !important;
        font-weight: 500 !important; line-height: 14px !important; min-height: 26px !important;
        display: flex !important; align-items: center !important;
        background: transparent; border: none; transition: all 0.12s ease; }
    .stRadio label p, .stRadio label span, .stRadio label div { font-size: 11px !important; line-height: 14px !important; }
    .stRadio label:hover { background: rgba(255,255,255,0.04); }
    .stRadio label[data-checked="true"] { background: rgba(120,126,231,0.12) !important; color: #EDEDED !important; }

    div[data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.06); background: transparent;
        border-radius: 8px; margin-bottom: 0px !important; }
    div[data-testid="stExpander"] details summary { padding: 3px 8px !important; min-height: 28px !important; }
    div[data-testid="stExpander"] details summary p,
    div[data-testid="stExpander"] details summary span {
        font-size: 12px !important; font-weight: 500 !important;
        line-height: 16px !important; color: #9B9B9B !important; }

    .stCheckbox { padding: 0 !important; margin: 0 !important; min-height: 20px !important; }
    .stCheckbox label {
        font-size: 11px !important; font-weight: 500 !important; line-height: 14px !important;
        padding: 2px 10px !important; gap: 6px !important; min-height: 26px !important;
        display: flex !important; align-items: center !important;
        border-radius: 6px; transition: background 0.12s ease; }
    .stCheckbox label:hover { background: rgba(255,255,255,0.04); }

    div[data-testid="stMetric"] {
        background: #161618; border-radius: 8px; padding: 16px 20px;
        border: 1px solid rgba(255,255,255,0.08); box-shadow: none; }
    div[data-testid="stMetric"] label {
        font-size: 11px; color: #666 !important; text-transform: uppercase;
        letter-spacing: 0.5px; font-weight: 500; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 20px; font-weight: 600; color: #EDEDED; }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] { font-size: 12px; }

    .stDataFrame { border-radius: 8px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }

    .stButton button {
        border-radius: 6px; font-weight: 500; font-size: 11px; height: 28px; padding: 0 12px;
        border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03);
        color: #9B9B9B; transition: all 0.12s ease; }
    .stButton button:hover {
        background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.12); color: #EDEDED; }

    [data-baseweb="menu"] [role="option"], [data-baseweb="popover"] [role="option"],
    [data-baseweb="menu"] li, [data-baseweb="select"] [role="option"], ul[role="listbox"] li {
        font-size: 11px !important; padding: 4px 10px !important;
        min-height: 26px !important; line-height: 14px !important; }
    [data-baseweb="popover"], [data-baseweb="menu"] { font-size: 11px !important; }

    .stSlider { padding-top: 0 !important; margin-bottom: -4px !important; }
    .stSlider label { font-size: 10px !important; font-weight: 500 !important; color: #555 !important; line-height: 14px !important; }
    .stSelectbox label { font-size: 10px !important; font-weight: 500 !important; color: #555 !important; line-height: 14px !important; }
    .stSelectbox [data-baseweb="select"] { font-size: 11px !important; }
    .stSelectbox [data-baseweb="select"] > div { min-height: 26px !important; border-radius: 6px !important; }
    .stTextInput input { height: 26px !important; font-size: 11px !important; border-radius: 6px !important; }

    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div { gap: 0px !important; }
    section[data-testid="stSidebar"] .stMarkdown { margin-bottom: 2px !important; }
    section[data-testid="stSidebar"] .stMarkdown p { font-size: 13px !important; line-height: 18px !important; }

    [data-baseweb="radio"] div[aria-checked="true"] > div:first-child,
    [data-baseweb="radio"] [aria-checked="true"] > div:first-child,
    [role="radio"][aria-checked="true"] > div:first-child,
    [role="radio"][aria-checked="true"] > div > div {
        background-color: #787EE7 !important; border-color: #787EE7 !important; }
    [data-baseweb="radio"] div:not([aria-checked="true"]) > div:first-child,
    [role="radio"]:not([aria-checked="true"]) > div:first-child {
        border-color: rgba(255,255,255,0.2) !important; }
    .stCheckbox svg { fill: #787EE7 !important; }
    [data-baseweb="checkbox"] [aria-checked="true"] > span:first-child,
    [data-baseweb="checkbox"] [aria-checked="true"] > div:first-child,
    [role="checkbox"][aria-checked="true"] > span:first-child {
        background-color: #787EE7 !important; border-color: #787EE7 !important; }
    [data-baseweb="checkbox"] span:first-child,
    [data-baseweb="checkbox"] > div:first-child {
        border-color: rgba(255,255,255,0.2) !important; border-radius: 4px !important; }
    .stSlider [data-baseweb="slider"] div[role="slider"] { background-color: #787EE7 !important; }
    .stSlider [data-testid="stThumbValue"] { color: #787EE7 !important; }
    .stMultiSelect [data-baseweb="tag"] svg { fill: #787EE7 !important; }
    [style*="rgb(255, 75, 75)"] { color: #787EE7 !important; }
    [style*="background-color: rgb(255, 75, 75)"] { background-color: #787EE7 !important; }
    [style*="border-color: rgb(255, 75, 75)"] { border-color: #787EE7 !important; }

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
</style>
"""


# ============================================================
# 즐겨찾기 관리 (JSON 파일 영구 저장)
# ============================================================
def load_favorites():
    if not os.path.exists(FAVORITES_FILE):
        # 파일 없으면 DEFAULT로 즉시 생성
        favs = DEFAULT_FAVORITES.copy()
        save_favorites(favs)
        return favs
    try:
        with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
            favs = json.load(f)
        if not isinstance(favs, list) or len(favs) == 0:
            raise ValueError("빈 리스트 또는 잘못된 형식")
        # 마이그레이션: (종목코드) 없는 한국 종목에 자동 추가
        changed = False
        for fav in favs:
            raw = fav['code'].split('.')[0]
            if re.match(r'^[0-9A-Z]{6}$', raw) and '(' not in fav['name']:
                fav['name'] = f"{fav['name']} ({raw})"
                changed = True
        if changed:
            save_favorites(favs)
        return favs
    except Exception as e:
        # 파일 손상 시 DEFAULT로 복구 후 에러를 session_state에 기록
        st.session_state['_fav_load_err'] = str(e)
        favs = DEFAULT_FAVORITES.copy()
        save_favorites(favs)
        return favs


def save_favorites(favs):
    try:
        with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
            json.dump(favs, f, ensure_ascii=False, indent=2)
        st.session_state.pop('_fav_load_err', None)
    except Exception as e:
        st.session_state['_fav_save_err'] = str(e)


@st.cache_data(ttl=7200)
def _get_krx_name_map(mkt_type: str) -> dict:
    """KRX KIND에서 {6자리코드: 한국어종목명} 딕셔너리 반환"""
    try:
        import requests as _req, io as _io
        url = "http://kind.krx.co.kr/corpgeneral/corpList.do"
        params  = {"method": "download", "searchType": "13", "marketType": mkt_type}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://kind.krx.co.kr/"}
        resp = _req.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        df = pd.read_html(_io.BytesIO(resp.content), encoding="euc-kr")[0]
        # 컬럼명 정규화: '회사명' 또는 '종목명'
        name_col = next((c for c in df.columns if '명' in c and '코드' not in c), None)
        if name_col is None:
            return {}
        result = {}
        for _, row in df.iterrows():
            raw = str(row["종목코드"])
            if re.match(r"^\d+$", raw):
                code6 = str(int(raw)).zfill(6)
                result[code6] = str(row[name_col])
        return result
    except Exception:
        return {}


@st.cache_data(ttl=7200)
def _naver_stock_name(code6: str) -> str:
    """Naver Finance 모바일 API로 한국어 종목명 조회 (ETF 포함)"""
    try:
        import requests as _req
        r = _req.get(
            f"https://m.stock.naver.com/api/stock/{code6}/basic",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=6,
        )
        data = r.json()
        return data.get('stockName') or data.get('name') or ''
    except Exception:
        return ''


def _lookup_ticker_name(ticker_code: str) -> str:
    """KRX 코드(.KS/.KQ)의 한국어 이름 조회
    지원: 6자리 숫자(일반주식·ETF) + 영숫자(ETN 등, 예: 0041D0)
    순서: KRX KIND(일반주식) → Naver Finance(ETF·ETN 전체) → yfinance(영어 fallback)
    """
    m = re.match(r"^([0-9A-Z]{6})\.(KS|KQ)$", ticker_code)
    if m:
        code6, suffix = m.group(1), m.group(2)
        # 1) KRX KIND 상장법인 목록 (숫자코드 일반주식에 빠름)
        if code6.isdigit():
            mkt_type = "stockMkt" if suffix == "KS" else "kosdaqMkt"
            name_map = _get_krx_name_map(mkt_type)
            if code6 in name_map:
                return name_map[code6]
        # 2) Naver Finance (ETF·ETN·리츠 모두 커버)
        naver_name = _naver_stock_name(code6)
        if naver_name:
            return naver_name
    # 3) yfinance fallback (영어 이름)
    try:
        info = yf.Ticker(ticker_code).info
        return info.get('shortName') or info.get('longName') or ''
    except Exception:
        return ''


# ============================================================
# 데이터 수집
# ============================================================
def _strip_tz(idx):
    idx = pd.to_datetime(idx)
    if hasattr(idx, 'tz') and idx.tz is not None:
        return idx.tz_convert(None)
    return idx


_OHLCV_FIELDS = {'Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close'}


def _normalize_yf_ohlcv(raw):
    """yfinance 단일 종목 download 결과 → 깔끔한 OHLCV DataFrame.

    처리 항목:
    - MultiIndex 컬럼 (field, ticker) / (ticker, field) 두 레이아웃 모두 처리
    - 중복 컬럼 제거 (flatten 후 이름 충돌)
    - 각 컬럼을 반드시 Series로 보장 (DataFrame 컬럼 방지)
    - 타임존 제거
    """
    if raw is None or (hasattr(raw, 'empty') and raw.empty):
        return pd.DataFrame()
    try:
        df = raw.copy()
        if isinstance(df.columns, pd.MultiIndex):
            l0 = set(df.columns.get_level_values(0))
            l1 = set(df.columns.get_level_values(1))
            if l0 & _OHLCV_FIELDS:          # (field, ticker) 레이아웃
                df.columns = df.columns.get_level_values(0)
            elif l1 & _OHLCV_FIELDS:        # (ticker, field) 레이아웃
                df.columns = df.columns.get_level_values(1)
            else:
                df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]      # 중복 컬럼 제거
        df.index = _strip_tz(df.index)
        for col in list(df.columns):                  # 컬럼 Series 보장
            if isinstance(df[col], pd.DataFrame):
                df[col] = df[col].iloc[:, 0]
        return df
    except Exception:
        return pd.DataFrame()


def _extract_close_df(raw, tickers):
    """yfinance 다중 종목 download 결과 → 종목별 종가 DataFrame (컬럼=ticker).

    group_by='ticker' (ticker, field) 레이아웃과
    기본 (field, ticker) 레이아웃 모두 처리.
    """
    if raw is None or (hasattr(raw, 'empty') and raw.empty):
        return pd.DataFrame()
    try:
        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            l0 = set(raw.columns.get_level_values(0))
            if l0 & _OHLCV_FIELDS:          # (field, ticker) 레이아웃
                close_block = raw.get('Close', pd.DataFrame())
                if isinstance(close_block, pd.Series):
                    if len(tickers) == 1:
                        result[tickers[0]] = close_block
                elif isinstance(close_block, pd.DataFrame):
                    for t in tickers:
                        if t in close_block.columns:
                            result[t] = close_block[t]
            else:                            # (ticker, field) 레이아웃
                for t in tickers:
                    try:
                        block = raw[t]
                        s = block['Close'] if isinstance(block, pd.DataFrame) else block
                        result[t] = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
                    except Exception:
                        pass
        else:
            if 'Close' in raw.columns and len(tickers) == 1:
                s = raw['Close']
                result[tickers[0]] = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
        if not result:
            return pd.DataFrame()
        out = pd.DataFrame(result)
        out.index = _strip_tz(out.index)
        return out
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900)
def fetch_ohlcv(ticker, start_str, end_str):
    """단일 종목 OHLCV (BB·RSI 차트용)"""
    try:
        raw = yf.download(ticker, start=start_str, end=end_str, progress=False)
        df = _normalize_yf_ohlcv(raw)
        if df.empty:
            return pd.DataFrame()
        cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        return df[cols].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900)
def fetch_close_batch(tickers_tuple, start_str, end_str):
    """다중 종목 종가 일괄 다운로드 (신호 스캔용)"""
    tickers = list(tickers_tuple)
    if not tickers:
        return pd.DataFrame()

    result = pd.DataFrame()

    # 배치 시도
    try:
        raw = yf.download(tickers, start=start_str, end=end_str,
                          progress=False, group_by='ticker', threads=False)
        result = _extract_close_df(raw, tickers)
    except Exception:
        pass

    # 배치 누락 개별 보완
    for t in tickers:
        if t not in result.columns or result[t].isna().all():
            try:
                raw = yf.download(t, start=start_str, end=end_str, progress=False)
                df = _normalize_yf_ohlcv(raw)
                if not df.empty and 'Close' in df.columns:
                    result[t] = df['Close']
            except Exception:
                pass

    if not result.empty:
        result.index = _strip_tz(result.index)
    return result


@st.cache_data(ttl=60)
def fetch_intraday(ticker, interval):
    """분봉 OHLCV (5m/15m/30m/60m). TTL=60s → 새로고침 시 최신 분봉 반영."""
    try:
        raw = yf.download(ticker, period='60d', interval=interval, progress=False)
        df = _normalize_yf_ohlcv(raw)
        if df.empty:
            return pd.DataFrame()
        # KS/KQ: _normalize_yf_ohlcv 이후 UTC-naive → KST-naive 로 변환
        # (hour-based rangebreak이 09:00-15:30 로 정확히 동작하도록)
        if ticker.endswith(('.KS', '.KQ')):
            try:
                df.index = (pd.to_datetime(df.index)
                            .tz_localize('UTC')
                            .tz_convert('Asia/Seoul')
                            .tz_localize(None))
            except Exception:
                pass
        cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        return df[cols].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def fetch_intraday_batch(tickers_tuple, interval):
    """분봉 Close 일괄 조회 (스캐너용). 각 ticker 순차 fetch 후 DataFrame으로 합산."""
    tickers = list(tickers_tuple)
    if not tickers:
        return pd.DataFrame()
    frames = {}
    for ticker in tickers:
        try:
            df = fetch_intraday(ticker, interval)
            if not df.empty and 'Close' in df.columns:
                frames[ticker] = df['Close']
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    result = pd.DataFrame(frames)
    result.index = _strip_tz(result.index)
    return result


# ============================================================
# 기술지표 계산
# ============================================================
def calculate_bb(close, window=20, num_std=2.0):
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    return sma, sma + num_std * std, sma - num_std * std


def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))


def calculate_dynamic_rsi_thresholds(rsi_series, lookback=60):
    """
    동적 RSI 임계값: 최근 lookback일 RSI의 상/하위 퍼센타일.
    - 하위 10% → 이 종목의 과매도 기준 (동적 하단)
    - 상위 90% → 이 종목의 과열 기준 (동적 상단)
    """
    min_p = max(lookback // 2, 10)
    dyn_lower = rsi_series.rolling(lookback, min_periods=min_p).quantile(0.10)
    dyn_upper = rsi_series.rolling(lookback, min_periods=min_p).quantile(0.90)
    return dyn_lower, dyn_upper


def calculate_parkour_signals(close, high, low, upper, lower, rsi,
                               rsi_buy_thr, rsi_sell_thr, rsi_band=5, persist=2,
                               phase2_rsi=False):
    """
    BB 파쿠르 신호 (2단계).

    rsi_buy_thr / rsi_sell_thr: pd.Series (동적) 또는 float (고정)
    rsi_band: 동적 RSI는 0 전달 (추가 마진 없음), 고정 밴드는 5 전달
    persist : 밴드 재진입 후 N일 연속 유지해야 확정

    매수:
      Phase1 플래그 ON  : RSI <= thr - band  AND  Low <= BB_Lower
      Phase2 확정       : 플래그 ON 상태에서 Close > BB_Lower N일 연속
      카운터 리셋       : 플래그 ON 중 Close <= BB_Lower 이면 카운터 0

    매도:
      Phase1 플래그 ON  : RSI >= thr + band  AND  High >= BB_Upper
      Phase2 확정       : 플래그 ON 상태에서 Close < BB_Upper N일 연속
    """
    if not isinstance(rsi_buy_thr, pd.Series):
        rsi_buy_thr  = pd.Series(float(rsi_buy_thr),  index=rsi.index)
    if not isinstance(rsi_sell_thr, pd.Series):
        rsi_sell_thr = pd.Series(float(rsi_sell_thr), index=rsi.index)

    oversold_flag  = pd.Series(False, index=close.index)
    buy_confirmed  = pd.Series(False, index=close.index)
    overheat_flag  = pd.Series(False, index=close.index)
    sell_confirmed = pd.Series(False, index=close.index)

    of = oh = False
    buy_cnt = sell_cnt = 0

    for i in range(len(close)):
        def _f(s): return float(s.iloc[i]) if not pd.isna(s.iloc[i]) else float('nan')
        c, h, l = _f(close), _f(high), _f(low)
        ub, lb   = _f(upper), _f(lower)
        r        = _f(rsi)
        bt, st   = _f(rsi_buy_thr), _f(rsi_sell_thr)

        if any(v != v for v in [c, h, l, ub, lb, r, bt, st]):  # nan check
            continue

        # ── 매수
        if not of and r <= bt - rsi_band and l <= lb:
            of = True
            buy_cnt = 0
        if of:
            # phase2_rsi=True: BB 복귀 AND RSI 회복 동시 충족
            # phase2_rsi=False: BB 복귀만 (기본)
            bb_ok  = l > lb
            rsi_ok = r > bt - rsi_band if phase2_rsi else True
            if bb_ok and rsi_ok:
                buy_cnt += 1
                if buy_cnt >= persist:
                    buy_confirmed.iloc[i] = True
                    of = False
                    buy_cnt = 0
            else:
                buy_cnt = 0
        oversold_flag.iloc[i] = of

        # ── 매도
        if not oh and r >= st + rsi_band and h >= ub:
            oh = True
            sell_cnt = 0
        if oh:
            bb_ok  = h < ub
            rsi_ok = r < st + rsi_band if phase2_rsi else True
            if bb_ok and rsi_ok:
                sell_cnt += 1
                if sell_cnt >= persist:
                    sell_confirmed.iloc[i] = True
                    oh = False
                    sell_cnt = 0
            else:
                sell_cnt = 0
        overheat_flag.iloc[i] = oh

    return oversold_flag, buy_confirmed, overheat_flag, sell_confirmed


def calculate_band_signals(close, high, low, upper, lower, rsi,
                           rsi_buy_center=40, rsi_sell_center=80, rsi_band=5):
    """
    밴드+BB 신호 (B안):
      매수 Phase1 : RSI < (buy_center - band)  = 35  AND  저가 <= BB 하단
      매수 Phase2 : RSI > (buy_center + band)  = 45  (RSI 회복만, BB 조건 없음)
      매도 Phase1 : RSI > (sell_center + band) = 85  AND  고가 >= BB 상단
      매도 Phase2 : RSI < (sell_center - band) = 75  (RSI 회복만, BB 조건 없음)
    """
    buy_enter  = rsi_buy_center  - rsi_band   # 35
    buy_exit   = rsi_buy_center  + rsi_band   # 45
    sell_enter = rsi_sell_center + rsi_band   # 85
    sell_exit  = rsi_sell_center - rsi_band   # 75

    oversold_flag  = pd.Series(False, index=close.index)
    buy_confirmed  = pd.Series(False, index=close.index)
    overheat_flag  = pd.Series(False, index=close.index)
    sell_confirmed = pd.Series(False, index=close.index)

    of = oh = False

    for i in range(len(close)):
        def _f(s): return float(s.iloc[i]) if not pd.isna(s.iloc[i]) else float('nan')
        l  = _f(low)
        h  = _f(high)
        ub = _f(upper)
        lb = _f(lower)
        r  = _f(rsi)

        if any(v != v for v in [l, h, ub, lb, r]):
            continue

        # 매수: RSI가 35 아래로 진입하면서 저가가 BB하단 터치 → 플래그
        # RSI가 45 위로 회복 → 확정 (가격 조건 없음)
        if not of and r < buy_enter and l <= lb:
            of = True
        if of and r > buy_exit:
            buy_confirmed.iloc[i] = True
            of = False
        oversold_flag.iloc[i] = of

        # 매도: RSI가 85 위로 진입하면서 고가가 BB상단 터치 → 플래그
        # RSI가 75 아래로 회복 → 확정 (가격 조건 없음)
        if not oh and r > sell_enter and h >= ub:
            oh = True
        if oh and r < sell_exit:
            sell_confirmed.iloc[i] = True
            oh = False
        overheat_flag.iloc[i] = oh

    return oversold_flag, buy_confirmed, overheat_flag, sell_confirmed


def get_current_signals(close, bb_window=20, bb_std=2.0, rsi_period=14,
                        rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                        rsi_lookback=60, persist=2, phase2_rsi=False):
    """
    현재(오늘) 신호 계산 (스캔 테이블용).
    Close를 High/Low 대용으로 사용 (배치 스캔 속도 유지).

    반환:
      dyn_buy/sell  : 동적 RSI(±0) + BB 파쿠르 확정 신호
      band_buy/sell : 고정 RSI 밴드(±5) + BB 파쿠르 확정 신호
    """
    close = close.dropna()
    if len(close) < bb_window + rsi_period + rsi_lookback // 2:
        return None

    sma, upper, lower = calculate_bb(close, bb_window, bb_std)
    rsi = calculate_rsi(close, rsi_period)
    dyn_lower, dyn_upper = calculate_dynamic_rsi_thresholds(rsi, rsi_lookback)

    # 동적 파쿠르: rsi_band=0 (동적 퍼센타일 자체가 임계값)
    dyn_of, dyn_buy, dyn_oh, dyn_sell = calculate_parkour_signals(
        close, close, close, upper, lower, rsi,
        dyn_lower, dyn_upper, rsi_band=0, persist=persist, phase2_rsi=phase2_rsi,
    )
    # 밴드+BB (B안): Phase1=BB터치+RSI극단, Phase2=RSI회복 (persist 없음)
    band_of, band_buy, band_oh, band_sell = calculate_band_signals(
        close, close, close, upper, lower, rsi,
        rsi_buy_center, rsi_sell_center, rsi_band,
    )

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_close
    pct        = (last_close / prev_close - 1) * 100 if prev_close else 0.0

    # 보유 중: 마지막 매수확정 이후 매도확정이 없는 상태
    def _is_holding(buy_ser, sell_ser):
        last_buy_idx  = buy_ser[buy_ser].index[-1]  if buy_ser.any()  else None
        last_sell_idx = sell_ser[sell_ser].index[-1] if sell_ser.any() else None
        in_pos = last_buy_idx is not None and (last_sell_idx is None or last_buy_idx > last_sell_idx)
        # 오늘 매수/매도 신호가 뜬 날은 별도 카테고리로 표시
        return in_pos and not bool(buy_ser.iloc[-1]) and not bool(sell_ser.iloc[-1])

    dyn_holding  = _is_holding(dyn_buy,  dyn_sell)
    band_holding = _is_holding(band_buy, band_sell)

    return {
        'close':      last_close,
        'pct_change': pct,
        'rsi':        float(rsi.iloc[-1]),
        'bb_upper_touch': last_close >= float(upper.iloc[-1]),
        'bb_lower_touch': last_close <= float(lower.iloc[-1]),
        # 확정 신호 (오늘)
        'dyn_buy_signal':   bool(dyn_buy.iloc[-1]),
        'dyn_sell_signal':  bool(dyn_sell.iloc[-1]),
        'band_buy_signal':  bool(band_buy.iloc[-1]),
        'band_sell_signal': bool(band_sell.iloc[-1]),
        # Phase 1 플래그 (매수/매도 관심 시점)
        'dyn_buy_flag':    bool(dyn_of.iloc[-1]),
        'dyn_sell_flag':   bool(dyn_oh.iloc[-1]),
        'band_buy_flag':   bool(band_of.iloc[-1]),
        'band_sell_flag':  bool(band_oh.iloc[-1]),
        # 보유 중 (매수확정 후 매도확정 전)
        'dyn_holding':     dyn_holding,
        'band_holding':    band_holding,
    }


# ============================================================
# 차트 공통 스타일
# ============================================================
_BG = "#0D0D0E"
_GRID = "rgba(255,255,255,0.05)"
_TEXT = "#9B9B9B"


def _base_layout(**extra):
    base = dict(
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(family="system-ui, sans-serif", size=11, color=_TEXT),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1A1A1C", bordercolor="rgba(255,255,255,0.1)", font_size=11),
    )
    base.update(extra)
    return base


def _axis_kw():
    return dict(showgrid=True, gridcolor=_GRID, zeroline=False, showline=False,
                tickfont=dict(size=10))


# ============================================================
# BB·RSI 디테일 차트 (3개 서브플롯)
# ============================================================


def make_detail_chart(ohlcv, name, period_days,
                      bb_window=20, bb_std=2.0,
                      rsi_period=14, rsi_lookback=60,
                      rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                      persist=2, phase2_rsi=False,
                      display_bars=None,
                      intraday_session=None):
    """
    차트 1: 가격 + BB  (확정 ★ 동적, ● 밴드 마커)
    차트 2: 동적 RSI   (0.10/0.90 percentile 기준선, rsi_band=0)
    차트 3: RSI 밴드   (고정 40/80 수평 밴드, rsi_band=5)
    """
    if ohlcv.empty or 'Close' not in ohlcv.columns:
        return None

    # fetch_ohlcv → _normalize_yf_ohlcv 를 거쳐 오므로 모든 컬럼은 Series 보장
    close = ohlcv['Close'].dropna()
    high  = ohlcv['High'].reindex(close.index).fillna(close) if 'High' in ohlcv.columns else close
    low   = ohlcv['Low'].reindex(close.index).fillna(close)  if 'Low'  in ohlcv.columns else close

    if len(close) < bb_window + rsi_period + rsi_lookback // 2:
        return None

    # ── 지표 계산 (전체 히스토리)
    sma, upper, lower = calculate_bb(close, bb_window, bb_std)
    rsi = calculate_rsi(close, rsi_period)
    dyn_lower, dyn_upper = calculate_dynamic_rsi_thresholds(rsi, rsi_lookback)

    # 파쿠르 신호 - 동적 RSI (rsi_band=0: 퍼센타일 자체가 임계값)
    dyn_of, dyn_buy, dyn_oh, dyn_sell = calculate_parkour_signals(
        close, high, low, upper, lower, rsi,
        dyn_lower, dyn_upper, rsi_band=0, persist=persist, phase2_rsi=phase2_rsi,
    )
    # 밴드+BB (B안): Phase1=BB터치+RSI극단, Phase2=RSI회복
    band_of, band_buy, band_oh, band_sell = calculate_band_signals(
        close, high, low, upper, lower, rsi,
        rsi_buy_center, rsi_sell_center, rsi_band,
    )

    # ── 표시 기간 슬라이싱 (display_bars 지정 시 우선, 없으면 period_days 사용)
    _n_disp = display_bars if display_bars is not None else period_days
    disp = close.index[-_n_disp:]

    # BB 터치
    upper_touch = disp[(close[disp] >= upper[disp]).values]
    lower_touch = disp[(close[disp] <= lower[disp]).values]

    # 동적 RSI 파쿠르 플래그 + 확정
    dyn_flag_buy_idx  = disp[dyn_of[disp].values]
    dyn_flag_sell_idx = disp[dyn_oh[disp].values]
    dyn_buy_idx  = disp[dyn_buy[disp].values]
    dyn_sell_idx = disp[dyn_sell[disp].values]

    # 고정 밴드 RSI 파쿠르
    band_flag_buy_idx  = disp[band_of[disp].values]
    band_flag_sell_idx = disp[band_oh[disp].values]
    band_buy_idx  = disp[band_buy[disp].values]
    band_sell_idx = disp[band_sell[disp].values]

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.50, 0.25, 0.25],
        shared_xaxes=False,
        vertical_spacing=0.08,
        subplot_titles=["", f"동적 RSI (0.10/0.90 Percentile, {rsi_lookback}{'봉' if intraday_session else 'd'})", f"RSI 밴드  매수 {rsi_buy_center-rsi_band}↓플래그 → {rsi_buy_center+rsi_band}↑확정  /  매도 {rsi_sell_center+rsi_band}↑플래그 → {rsi_sell_center-rsi_band}↓확정"],
    )

    # ══════════════════════════════════════════
    # ROW 1: 가격 + BB  + 파쿠르 마커
    # ══════════════════════════════════════════
    fig.add_trace(go.Scatter(x=disp, y=upper[disp],
        line=dict(color="rgba(120,126,231,0.2)", width=1),
        showlegend=False, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=lower[disp],
        line=dict(color="rgba(120,126,231,0.2)", width=1),
        fill='tonexty', fillcolor="rgba(120,126,231,0.04)",
        showlegend=False, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=sma[disp],
        line=dict(color="rgba(120,126,231,0.4)", width=1, dash='dot'),
        showlegend=False, name="SMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=close[disp],
        name=name, line=dict(color="#EDEDED", width=1.5)), row=1, col=1)

    # 동적+BB 확정 ★ (초록=매수, 빨강=매도)
    if len(dyn_buy_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_buy_idx, y=close[dyn_buy_idx],
            mode='markers',
            marker=dict(symbol='star', color='#4BFFB3', size=10,
                        line=dict(color='rgba(75,255,179,0.4)', width=1)),
            name="★ 동적+BB 매수"), row=1, col=1)
    if len(dyn_sell_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_sell_idx, y=close[dyn_sell_idx],
            mode='markers',
            marker=dict(symbol='star', color='#FF4B6E', size=10,
                        line=dict(color='rgba(255,75,110,0.4)', width=1)),
            name="★ 동적+BB 매도"), row=1, col=1)

    # 밴드+BB 확정 ● (초록=매수, 빨강=매도)
    if len(band_buy_idx) > 0:
        fig.add_trace(go.Scatter(x=band_buy_idx, y=close[band_buy_idx],
            mode='markers',
            marker=dict(symbol='circle-open', color='#4BFFB3', size=12,
                        line=dict(color='#4BFFB3', width=2.5)),
            name="● 밴드+BB 매수"), row=1, col=1)
    if len(band_sell_idx) > 0:
        fig.add_trace(go.Scatter(x=band_sell_idx, y=close[band_sell_idx],
            mode='markers',
            marker=dict(symbol='circle-open', color='#FF4B6E', size=12,
                        line=dict(color='#FF4B6E', width=2.5)),
            name="● 밴드+BB 매도"), row=1, col=1)

    # ══════════════════════════════════════════
    # ROW 2: 동적 RSI
    # ══════════════════════════════════════════
    # quantile 사이 중립 구간 음영
    fig.add_trace(go.Scatter(x=disp, y=dyn_upper[disp],
        line=dict(color="rgba(255,215,0,0.2)", width=1),
        showlegend=False, hoverinfo='skip'), row=2, col=1)
    fig.add_trace(go.Scatter(x=disp, y=dyn_lower[disp],
        line=dict(color="rgba(75,255,179,0.2)", width=1),
        fill='tonexty', fillcolor="rgba(255,255,255,0.02)",
        showlegend=False, hoverinfo='skip'), row=2, col=1)

    fig.add_trace(go.Scatter(x=disp, y=rsi[disp],
        line=dict(color="#787EE7", width=1.5), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=disp, y=dyn_upper[disp],
        name="동적 상단 (90th)", line=dict(color="#FFD700", width=1, dash='dash')), row=2, col=1)
    fig.add_trace(go.Scatter(x=disp, y=dyn_lower[disp],
        name="동적 하단 (10th)", line=dict(color="#4BFFB3", width=1, dash='dash')), row=2, col=1)
    fig.add_hline(y=50, line_color="rgba(255,255,255,0.08)", line_width=0.7,
                  line_dash="dot", row=2, col=1)

    # 동적+BB 확정 ★ (Row2: 초록=매수, 빨강=매도)
    if len(dyn_buy_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_buy_idx, y=rsi[dyn_buy_idx], mode='markers',
            marker=dict(symbol='star', color='#4BFFB3', size=8),
            showlegend=False), row=2, col=1)
    if len(dyn_sell_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_sell_idx, y=rsi[dyn_sell_idx], mode='markers',
            marker=dict(symbol='star', color='#FF4B6E', size=8),
            showlegend=False), row=2, col=1)

    # ══════════════════════════════════════════
    # ROW 3: RSI 밴드 (수평선만, 채움 없음)
    # ══════════════════════════════════════════
    # add_hline 대신 Scatter로 수평선 → shared_xaxes=False 환경에서 확실하게 렌더링
    x0, x1 = disp[0], disp[-1]
    for lvl, c, w, dash in [
        (rsi_buy_center  - rsi_band, "#4BFFB3", 1.2, "dash"),   # 35
        (rsi_buy_center  + rsi_band, "#4BFFB3", 0.8, "dash"),   # 45
        (rsi_sell_center - rsi_band, "#FF4B6E", 0.8, "dash"),   # 75
        (rsi_sell_center + rsi_band, "#FF4B6E", 1.2, "dash"),   # 85
        (50,               "rgba(255,255,255,0.08)", 0.7, "dot"),
    ]:
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[lvl, lvl], mode='lines',
            line=dict(color=c, width=w, dash=dash),
            showlegend=False, hoverinfo='skip',
        ), row=3, col=1)

    fig.add_trace(go.Scatter(x=disp, y=rsi[disp],
        line=dict(color="#787EE7", width=1.5), showlegend=False), row=3, col=1)

    # 밴드+BB 확정 ● (Row3: 초록=매수, 빨강=매도)
    if len(band_buy_idx) > 0:
        fig.add_trace(go.Scatter(x=band_buy_idx, y=rsi[band_buy_idx], mode='markers',
            marker=dict(symbol='circle-open', color='#4BFFB3', size=12,
                        line=dict(color='#4BFFB3', width=2.5)),
            name="● 밴드+BB 매수", showlegend=False), row=3, col=1)
    if len(band_sell_idx) > 0:
        fig.add_trace(go.Scatter(x=band_sell_idx, y=rsi[band_sell_idx], mode='markers',
            marker=dict(symbol='circle-open', color='#FF4B6E', size=12,
                        line=dict(color='#FF4B6E', width=2.5)),
            name="● 밴드+BB 매도", showlegend=False), row=3, col=1)

    # ── 레이아웃
    fig.update_layout(
        height=820,
        title=dict(text=f"<b>{name}</b>", font=dict(size=14, color="#EDEDED"), x=0,
                   y=0.98, yanchor="top"),
        legend=dict(orientation="h", yanchor="top", y=0.97, xanchor="right", x=1,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)", traceorder="normal"),
        **_base_layout(margin=dict(l=10, r=10, t=70, b=10)),
    )
    fig.update_xaxes(**_axis_kw())
    fig.update_yaxes(**_axis_kw())
    # X축 연동 (matches='x': 모든 서브플롯 X 동기화, Y는 각자 독립 스케일)
    fig.update_xaxes(matches='x')
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    # X축 날짜 레이블 기울기 제거
    fig.update_xaxes(tickangle=0, row=1, col=1)
    fig.update_xaxes(tickangle=0, row=3, col=1)
    # RSI 차트 Y축: 고정 범위 + 20단위 눈금
    fig.update_yaxes(range=[0, 100], dtick=20, row=2, col=1)
    fig.update_yaxes(range=[0, 100], dtick=20, row=3, col=1)
    # 가격 차트 Y축: 표시 구간 실제 데이터 범위로 명시 설정 (전체 기간 데이터로 늘어나는 현상 방지)
    _disp_high = high.reindex(disp).dropna()
    _disp_low  = low.reindex(disp).dropna()
    _disp_ub   = upper.reindex(disp).dropna()
    _disp_lb   = lower.reindex(disp).dropna()
    _y_max = float(max(_disp_high.max(), _disp_ub.max()))
    _y_min = float(min(_disp_low.min(),  _disp_lb.min()))
    _y_pad = (_y_max - _y_min) * 0.04
    fig.update_yaxes(range=[_y_min - _y_pad, _y_max + _y_pad], row=1, col=1)
    for ann in fig.layout.annotations:
        ann.font.color = "#555"
        ann.font.size = 10
    # 분봉 모드: 주말 + 야간 갭 숨김
    if intraday_session is not None:
        close_h, open_h = intraday_session
        fig.update_xaxes(rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(bounds=[close_h, open_h], pattern="hour"),
        ])
    return fig


# ============================================================
# 신호 스캔 테이블 (HTML 렌더링)
# ============================================================
def _badge(text, fg, bg, border):
    return (f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;'
            f'font-size:10px;border:1px solid {border};display:inline-block;'
            f'line-height:18px;white-space:nowrap;">{text}</span>')


def signal_badges_html(dyn_buy, dyn_sell, band_buy, band_sell,
                       dyn_buy_flag=False, dyn_sell_flag=False,
                       band_buy_flag=False, band_sell_flag=False,
                       dyn_holding=False, band_holding=False):
    parts = []
    # 확정 신호 (오늘)
    if dyn_buy:
        parts.append(_badge("★ 동적+BB 매수", "#4BFFB3", "#0a2b1e", "rgba(75,255,179,0.3)"))
    if dyn_sell:
        parts.append(_badge("★ 동적+BB 매도", "#FF4B6E", "#2d0d1a", "rgba(255,75,110,0.25)"))
    if band_buy:
        parts.append(_badge("● 밴드+BB 매수", "#4BFFB3", "#0a2b1e", "rgba(75,255,179,0.2)"))
    if band_sell:
        parts.append(_badge("● 밴드+BB 매도", "#FF4B6E", "#250813", "rgba(255,75,110,0.15)"))
    # 보유 중 (매수확정 후 매도확정 전)
    if dyn_holding:
        parts.append(_badge("★ 보유 중", "#C8C850", "#1c1c08", "rgba(200,200,80,0.3)"))
    if band_holding:
        parts.append(_badge("● 보유 중", "#50C878", "#081c10", "rgba(80,200,120,0.25)"))
    # Phase 1 플래그 (관심 시점)
    if dyn_buy_flag and not dyn_buy:
        parts.append(_badge("★ 매수 플래그", "#7AAFD4", "#0a1520", "rgba(120,175,212,0.2)"))
    if dyn_sell_flag and not dyn_sell:
        parts.append(_badge("★ 매도 플래그", "#D47A9F", "#200a14", "rgba(212,120,160,0.2)"))
    if band_buy_flag and not band_buy:
        parts.append(_badge("● 매수 플래그", "#7AAFD4", "#0a1520", "rgba(120,175,212,0.15)"))
    if band_sell_flag and not band_sell:
        parts.append(_badge("● 매도 플래그", "#D47A9F", "#200a14", "rgba(212,120,160,0.15)"))
    if not parts:
        return '<span style="color:#333;font-size:12px;">─</span>'
    return " ".join(parts)


def render_signal_table(signal_rows):
    rows_html = []
    for row in signal_rows:
        dyn_buy       = row.get('dyn_buy_signal',  False)
        dyn_sell      = row.get('dyn_sell_signal', False)
        band_buy      = row.get('band_buy_signal',  False)
        band_sell     = row.get('band_sell_signal', False)
        dyn_buy_flag   = row.get('dyn_buy_flag',   False)
        dyn_sell_flag  = row.get('dyn_sell_flag',  False)
        band_buy_flag  = row.get('band_buy_flag',  False)
        band_sell_flag = row.get('band_sell_flag', False)
        dyn_holding    = row.get('dyn_holding',    False)
        band_holding   = row.get('band_holding',   False)
        any_signal  = dyn_buy or dyn_sell or band_buy or band_sell
        any_holding = dyn_holding or band_holding
        any_flag    = dyn_buy_flag or dyn_sell_flag or band_buy_flag or band_sell_flag
        row_bg = ("rgba(120,126,231,0.07)" if any_signal
                  else "rgba(200,200,80,0.04)" if any_holding
                  else "rgba(120,126,231,0.02)" if any_flag
                  else "transparent")

        close_val = row.get('close')
        pct_val   = row.get('pct_change')
        rsi_val   = row.get('rsi')

        close_str = f"{close_val:,.0f}" if close_val is not None else "─"
        pct_color = "#4BFFB3" if (pct_val or 0) > 0 else "#FF4B6E" if (pct_val or 0) < 0 else "#555"
        pct_str   = f"{pct_val:+.2f}%" if pct_val is not None else "─"

        if rsi_val is None:
            rsi_str, rsi_color = "─", "#555"
        elif rsi_val < 35:
            rsi_str, rsi_color = f"{rsi_val:.1f}", "#4BFFB3"
        elif rsi_val > 75:
            rsi_str, rsi_color = f"{rsi_val:.1f}", "#FF4B6E"
        else:
            rsi_str, rsi_color = f"{rsi_val:.1f}", "#9B9B9B"

        star = "★&nbsp;" if any_signal else ""
        badges = signal_badges_html(
            dyn_buy, dyn_sell, band_buy, band_sell,
            dyn_buy_flag, dyn_sell_flag, band_buy_flag, band_sell_flag,
            dyn_holding=dyn_holding, band_holding=band_holding,
        )

        rows_html.append(f"""
        <tr style="background:{row_bg};border-bottom:1px solid rgba(255,255,255,0.04);">
            <td style="padding:10px 14px;font-size:13px;color:#EDEDED;font-weight:500;white-space:nowrap;">{star}{row['name']}</td>
            <td style="padding:10px 14px;font-size:13px;color:#EDEDED;text-align:right;font-variant-numeric:tabular-nums;">{close_str}</td>
            <td style="padding:10px 14px;font-size:13px;color:{pct_color};text-align:right;font-variant-numeric:tabular-nums;">{pct_str}</td>
            <td style="padding:10px 14px;font-size:13px;color:{rsi_color};text-align:right;font-variant-numeric:tabular-nums;">{rsi_str}</td>
            <td style="padding:10px 14px;">{badges}</td>
        </tr>""")

    return f"""
    <div style="overflow-x:auto;margin-bottom:8px;">
    <table style="width:100%;border-collapse:collapse;background:#111113;
                  border-radius:10px;overflow:hidden;border:1px solid rgba(255,255,255,0.07);">
        <thead>
            <tr style="border-bottom:1px solid rgba(255,255,255,0.07);">
                <th style="padding:8px 14px;font-size:10px;color:#555;font-weight:600;text-align:left;text-transform:uppercase;letter-spacing:0.8px;">종목</th>
                <th style="padding:8px 14px;font-size:10px;color:#555;font-weight:600;text-align:right;text-transform:uppercase;letter-spacing:0.8px;">현재가</th>
                <th style="padding:8px 14px;font-size:10px;color:#555;font-weight:600;text-align:right;text-transform:uppercase;letter-spacing:0.8px;">등락률</th>
                <th style="padding:8px 14px;font-size:10px;color:#555;font-weight:600;text-align:right;text-transform:uppercase;letter-spacing:0.8px;">RSI</th>
                <th style="padding:8px 14px;font-size:10px;color:#555;font-weight:600;text-align:left;text-transform:uppercase;letter-spacing:0.8px;">신호</th>
            </tr>
        </thead>
        <tbody>{''.join(rows_html)}</tbody>
    </table>
    </div>"""


# ============================================================
# 탭 2: 시장 내부지표
# ============================================================
_WIKI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
_INDEX_CODE = {
    "코스피": "^KS11", "코스닥": "^KQ11",
    "S&P 500": "^GSPC", "나스닥 100": "^NDX",
}


@st.cache_data(ttl=7200)
def get_full_ticker_list(market):
    """전체 종목 코드 조회.
    한국: KRX KIND 상장법인목록 (requests)
    미국: Wikipedia S&P 500 / NASDAQ-100 구성 종목
    실패 시 None 반환."""
    try:
        import requests, io, re, warnings
        warnings.filterwarnings("ignore")

        # ── 미국 시장 ──────────────────────────────────────────
        if market == "S&P 500":
            r = requests.get(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                headers=_WIKI_HEADERS, verify=False, timeout=15)
            tables = pd.read_html(io.StringIO(r.text), flavor="lxml")
            tickers = (tables[0]["Symbol"]
                       .str.replace(".", "-", regex=False)
                       .dropna().tolist())
            return tickers if len(tickers) > 10 else None

        if market == "나스닥 100":
            r = requests.get(
                "https://en.wikipedia.org/wiki/Nasdaq-100",
                headers=_WIKI_HEADERS, verify=False, timeout=15)
            tables = pd.read_html(io.StringIO(r.text), flavor="lxml")
            for t in tables:
                for col in ["Ticker", "Symbol"]:
                    if col in t.columns and len(t) > 50:
                        return t[col].dropna().tolist()
            return None

        # ── 한국 시장 ──────────────────────────────────────────
        mkt_type = "stockMkt" if market == "코스피" else "kosdaqMkt"
        suffix   = ".KS"      if market == "코스피" else ".KQ"
        url = "http://kind.krx.co.kr/corpgeneral/corpList.do"
        params  = {"method": "download", "searchType": "13", "marketType": mkt_type}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://kind.krx.co.kr/"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        df = pd.read_html(io.BytesIO(resp.content), encoding="euc-kr")[0]
        codes = [str(int(c)).zfill(6) for c in df["종목코드"]
                 if re.match(r"^\d+$", str(c))]
        tickers = [f"{c}{suffix}" for c in codes if len(c) == 6]
        return tickers if len(tickers) > 50 else None

    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_market_internals(market, lookback_days=60):
    try:
        full_tickers  = get_full_ticker_list(market)
        _fallback     = _KOSPI_BASKET if market == "코스피" else _KOSDAQ_BASKET
        basket        = full_tickers if full_tickers else (
                            _fallback if market in ("코스피", "코스닥") else None)
        if basket is None:
            return None, f"{market} 종목 리스트 조회 실패"
        index_yf_code = _INDEX_CODE.get(market, "^KS11")
        vix_code      = "^VKOSPI" if market in ("코스피", "코스닥") else "^VIX"

        end_dt   = datetime.now()
        # 200일선 계산을 위해 항상 충분한 히스토리 확보 (200 거래일 ≈ 300 캘린더일)
        extra    = max(lookback_days + 320, lookback_days * 2 + 10)
        start_dt = end_dt - timedelta(days=extra)
        yf_start = start_dt.strftime("%Y-%m-%d")
        yf_end   = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        # ── 시총가중 지수
        idx_df = _normalize_yf_ohlcv(
            yf.download(index_yf_code, start=yf_start, end=yf_end,
                        progress=False, auto_adjust=True))
        if idx_df.empty or 'Close' not in idx_df.columns:
            return None, f"지수 데이터 없음 ({index_yf_code})"
        cap_close = idx_df['Close'].dropna()

        # ── VIX / VKOSPI
        vix_series = pd.Series(dtype=float)
        try:
            vix_df = _normalize_yf_ohlcv(
                yf.download(vix_code, start=yf_start, end=yf_end,
                            progress=False, auto_adjust=True))
            if not vix_df.empty and 'Close' in vix_df.columns:
                vix_series = vix_df['Close'].dropna()
        except Exception:
            pass

        # ── 전체 종목 종가 다운로드 (청크 100개씩)
        chunk_size = 100
        chunks = [basket[i:i+chunk_size] for i in range(0, len(basket), chunk_size)]
        close_parts = []
        for chunk in chunks:
            try:
                raw_c = yf.download(chunk, start=yf_start, end=yf_end,
                                    progress=False, auto_adjust=True)
                c_df = _extract_close_df(raw_c, chunk)
                if not c_df.empty:
                    close_parts.append(c_df)
            except Exception:
                continue

        if not close_parts:
            return None, "바스켓 종목 데이터 없음"
        closes_full = pd.concat(close_parts, axis=1)

        # 유효 종목 필터 (전체 기간 기준 30% 이상)
        valid_cols = closes_full.columns[closes_full.notna().mean() >= 0.3]
        if len(valid_cols) < 3:
            return None, "유효 바스켓 종목 부족 (< 3개)"
        closes_full = closes_full[valid_cols].dropna(how='all')

        # ── 200일선 상위 비율 (전체 데이터로 계산)
        ma200       = closes_full.rolling(200, min_periods=100).mean()
        above_200   = (closes_full > ma200)
        total_valid = closes_full.notna()
        pct_above_200 = (above_200.sum(axis=1) / total_valid.sum(axis=1) * 100).round(1)

        # ── 맥클렐란: 전체 기간 EMA가 정확하도록 full 데이터로 계산
        daily_chg_full = closes_full.diff() / closes_full.shift(1)
        adv_full = (daily_chg_full > 0).sum(axis=1)
        dec_full = (daily_chg_full < 0).sum(axis=1)
        net_full = (adv_full - dec_full).astype(float)
        ema19_full    = net_full.ewm(span=19, adjust=False).mean()
        ema39_full    = net_full.ewm(span=39, adjust=False).mean()
        mcclellan_full = ema19_full - ema39_full
        summation_full = mcclellan_full.cumsum()

        # ── 표시 구간으로 트림
        closes_df = closes_full.iloc[-lookback_days:]

        # 균일가중 지수
        first_prices = closes_df.apply(
            lambda col: col.dropna().iloc[0] if col.notna().any() else float('nan'))
        ew_index = closes_df.div(first_prices).mul(100).mean(axis=1)

        # 시총가중 지수 정렬
        cap_aligned    = cap_close.reindex(closes_df.index, method='ffill')
        cap_normalized = cap_aligned / cap_aligned.dropna().iloc[0] * 100

        # 상승/하락 집계
        daily_chg = closes_df.diff() / closes_df.shift(1)
        advancing = (daily_chg > 0).sum(axis=1)
        declining = (daily_chg < 0).sum(axis=1)
        total     = daily_chg.notna().sum(axis=1)
        adv_ratio = (advancing / total.replace(0, float('nan')) * 100).round(1)

        # ADL (표시 구간 누적)
        net_adv = (advancing - declining).astype(float)
        adl     = net_adv.cumsum()

        # 표시 구간 트림
        mcclellan      = mcclellan_full.reindex(closes_df.index).round(1)
        summation      = summation_full.reindex(closes_df.index).round(1)
        adv_ratio_ma20 = adv_ratio.rolling(20, min_periods=5).mean().round(1)
        pct_200_trim   = pct_above_200.reindex(closes_df.index)
        vix_aligned    = (vix_series.reindex(closes_df.index, method='ffill')
                          if not vix_series.empty
                          else pd.Series(float('nan'), index=closes_df.index))

        result = pd.DataFrame({
            '시총가중':    cap_normalized,
            '균일가중':    ew_index,
            '상승종목수':  advancing,
            '하락종목수':  declining,
            '전체종목수':  total,
            '상승비율':    adv_ratio,
            '상승비율MA20': adv_ratio_ma20,
            'ADL':         adl,
            '맥클렐란':    mcclellan,
            '서머레이션':  summation,
            'VIX':         vix_aligned,
            '200MA상위':   pct_200_trim,
        }).dropna(subset=['균일가중'])

        return result, None
    except Exception as e:
        return None, traceback.format_exc()


def _market_sentiment_html(df, market_name):
    """8개 지표 기반 시장 강세/약세 종합 요약 HTML"""
    if df is None or len(df) < 6:
        return ""
    latest = df.iloc[-1]
    n = len(df)
    ago10 = df.iloc[max(0, n - 11)]   # 10거래일 전
    ago5  = df.iloc[max(0, n - 6)]    # 5거래일 전

    def _trend(col, ref):
        try:
            return float(df[col].iloc[-1]) > float(ref[col])
        except Exception:
            return True

    def _val_bull(col, threshold, invert=False):
        v = latest[col]
        if not pd.notna(v):
            return None
        return (float(v) < threshold) if invert else (float(v) > threshold)

    sigs = [
        ("시총가중", _trend('시총가중', ago10),
         f"{'↑' if _trend('시총가중', ago10) else '↓'}{latest['시총가중']:.1f}"),
        ("균일가중", _trend('균일가중', ago10),
         f"{'↑' if _trend('균일가중', ago10) else '↓'}{latest['균일가중']:.1f}"),
        ("ADL", _trend('ADL', ago5),
         f"{'↑' if _trend('ADL', ago5) else '↓'}"),
        ("오실레이터", float(latest['맥클렐란']) > 0,
         f"{float(latest['맥클렐란']):+.0f}"),
        ("서머레이션", float(latest['서머레이션']) > 0,
         f"{float(latest['서머레이션']):+.0f}"),
        ("VIX", _val_bull('VIX', 25, invert=True),       # VIX < 25 = bull
         f"{float(latest['VIX']):.1f}" if pd.notna(latest['VIX']) else "N/A"),
        ("상승비율", _val_bull('상승비율MA20', 50),
         f"{float(latest['상승비율MA20']):.0f}%" if pd.notna(latest['상승비율MA20']) else "N/A"),
        ("200MA상위", _val_bull('200MA상위', 50),
         f"{float(latest['200MA상위']):.0f}%" if pd.notna(latest['200MA상위']) else "N/A"),
    ]

    # None(데이터없음) 제외하고 집계
    valid  = [(n, b, v) for n, b, v in sigs if b is not None]
    bull_n = sum(1 for _, b, _ in valid if b)
    total  = len(valid)
    pct    = bull_n / total if total else 0.5

    if pct >= 0.875:   label, accent = "강한 강세",  "#00FF7F"
    elif pct >= 0.625: label, accent = "강세",        "#4BFFB3"
    elif pct >= 0.375: label, accent = "중립",        "#C8C850"
    elif pct >= 0.125: label, accent = "약세",        "#FF8C69"
    else:              label, accent = "강한 약세",   "#FF4B6E"

    bar_w = int(pct * 100)
    vix_lbl = "VKOSPI" if market_name in ("코스피", "코스닥") else "VIX"
    # VIX 라벨 교체
    sigs_display = []
    for nm, bull, val in sigs:
        display_nm = vix_lbl if nm == "VIX" else nm
        sigs_display.append((display_nm, bull, val))

    pills = "".join(
        f'<span style="background:{"rgba(75,255,179,0.13)" if b else "rgba(255,75,110,0.10)"};'
        f'color:{"#4BFFB3" if b else "#FF4B6E"};border-radius:4px;'
        f'padding:2px 8px;font-size:10px;margin:2px 2px;display:inline-block;'
        f'border:1px solid {"#4BFFB322" if b else "#FF4B6E22"};white-space:nowrap;">'
        f'{"▲" if b else "▼"} {nm} {val}</span>'
        for nm, b, val in sigs_display if b is not None
    )

    return (
        f'<div style="background:#0f1117;border:1px solid {accent}30;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:10px;">'
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:7px;">'
        f'<span style="font-size:17px;font-weight:700;color:{accent};letter-spacing:0.5px;">'
        f'{label}</span>'
        f'<span style="font-size:11px;color:#555;">{bull_n}/{total} 강세</span>'
        f'<div style="flex:1;background:rgba(255,75,110,0.15);border-radius:3px;height:5px;overflow:hidden;">'
        f'<div style="width:{bar_w}%;background:{accent};height:100%;border-radius:3px;"></div>'
        f'</div></div>'
        f'<div style="line-height:1.8;">{pills}</div>'
        f'</div>'
    )


def make_market_chart(df, market_name):
    vix_label = "VKOSPI" if market_name in ("코스피", "코스닥") else "VIX"
    has_vix   = df['VIX'].notna().any()
    has_200   = df['200MA상위'].notna().any()
    has_summ  = df['서머레이션'].notna().any()
    x0, x1   = df.index[0], df.index[-1]

    def _hl(row, col, y, color, dash='dot', width=0.9):
        """데이터 범위 안에서만 그리는 수평 참조선 (Scatter 방식 → y축 auto-scale 보호)"""
        return go.Scatter(
            x=[x0, x1], y=[y, y], mode='lines',
            line=dict(color=color, width=width, dash=dash),
            showlegend=False, hoverinfo='skip',
        )

    fig = make_subplots(
        rows=4, cols=2,
        row_heights=[0.22, 0.22, 0.28, 0.28],
        subplot_titles=[
            "시총가중 vs 균일가중 (기준=100)",
            "시총가중 ÷ 균일가중 비율",
            "ADL — 등락 누적선",
            "맥클렐란 오실레이터",
            "맥클렐란 서머레이션 인덱스",
            f"{vix_label} — 공포지수",
            "상승비율 & 20일 이동평균",
            "200일선 상위 종목 비율 (%)",
        ],
        vertical_spacing=0.09,
        horizontal_spacing=0.08,
    )

    # ── Row 1 left: 시총가중 vs 균일가중
    fig.add_trace(go.Scatter(x=df.index, y=df['시총가중'],
        name="시총가중", line=dict(color="#00FF7F", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['균일가중'],
        name="균일가중", line=dict(color="#FFD700", width=1.5)), row=1, col=1)

    # ── Row 1 right: 비율
    ratio = (df['시총가중'] / df['균일가중']).round(4)
    fig.add_trace(go.Scatter(x=df.index, y=ratio,
        line=dict(color="#787EE7", width=1.5), showlegend=False), row=1, col=2)
    fig.add_trace(_hl(1, 2, float(ratio.mean()),
        "rgba(255,255,255,0.12)", 'dot'), row=1, col=2)

    # ── Row 2 left: ADL
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ADL'],
        line=dict(color="#787EE7", width=1.8),
        fill='tozeroy', fillcolor="rgba(120,126,231,0.06)",
        showlegend=False,
    ), row=2, col=1)
    fig.add_trace(_hl(2, 1, 0, "rgba(255,255,255,0.15)", 'dot'), row=2, col=1)

    # ── Row 2 right: 맥클렐란 오실레이터 (y축 데이터 기반 auto-scale)
    mcc = df['맥클렐란'].dropna()
    bar_colors = ["#4BFFB3" if v >= 0 else "#FF4B6E" for v in mcc]
    fig.add_trace(go.Bar(x=mcc.index, y=mcc,
        marker_color=bar_colors, showlegend=False), row=2, col=2)
    fig.add_trace(_hl(2, 2, 0, "rgba(255,255,255,0.20)", 'solid', 1.0), row=2, col=2)
    # ±60 참조선: 데이터가 해당 레벨에 근접할 때만 의미 있으므로 Scatter로 그려 축 강제 확장 방지
    mcc_bound = max(abs(float(mcc.max())), abs(float(mcc.min())), 5) * 1.25
    for lvl, c in [(60, "rgba(255,75,110,0.45)"), (-60, "rgba(75,255,179,0.45)")]:
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[lvl, lvl], mode='lines',
            line=dict(color=c, width=0.9, dash='dot'),
            showlegend=False, hoverinfo='skip',
        ), row=2, col=2)
    fig.update_yaxes(range=[-mcc_bound, mcc_bound], row=2, col=2)

    # ── Row 3 left: 서머레이션 (y축 데이터 기반 auto-scale)
    if has_summ:
        summ = df['서머레이션'].dropna()
        summ_color = ["#4BFFB3" if v >= 0 else "#FF4B6E" for v in summ]
        fig.add_trace(go.Bar(x=summ.index, y=summ,
            marker_color=summ_color, showlegend=False), row=3, col=1)
        fig.add_trace(_hl(3, 1, 0, "rgba(255,255,255,0.20)", 'solid', 1.0), row=3, col=1)
        summ_bound = max(abs(float(summ.max())), abs(float(summ.min())), 50) * 1.25
        for lvl, c in [(1000, "rgba(255,75,110,0.45)"), (-1000, "rgba(75,255,179,0.45)")]:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[lvl, lvl], mode='lines',
                line=dict(color=c, width=0.9, dash='dot'),
                showlegend=False, hoverinfo='skip',
            ), row=3, col=1)
        fig.update_yaxes(range=[-summ_bound, summ_bound], row=3, col=1)

    # ── Row 3 right: VIX — 라인만, 25 중심 y축
    if has_vix:
        vix = df['VIX'].dropna()
        fig.add_trace(go.Scatter(
            x=vix.index, y=vix,
            line=dict(color="#FFB347", width=1.8),
            showlegend=False,                          # fill 제거
        ), row=3, col=2)
        # 25 중심 대칭 y축
        vix_center = 25.0
        half = max(abs(float(vix.max()) - vix_center),
                   abs(vix_center - float(vix.min())), 6) * 1.3
        fig.update_yaxes(range=[vix_center - half, vix_center + half], row=3, col=2)
        # 20/30 참조선
        for lvl, c in [(20, "rgba(75,255,179,0.45)"), (25, "rgba(255,255,255,0.10)"),
                       (30, "rgba(255,75,110,0.45)")]:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[lvl, lvl], mode='lines',
                line=dict(color=c, width=0.9, dash='dot'),
                showlegend=False, hoverinfo='skip',
            ), row=3, col=2)

    # ── Row 4 left: 상승비율 & MA20
    fig.add_trace(go.Scatter(
        x=df.index, y=df['상승비율'],
        name="상승비율", line=dict(color="rgba(120,126,231,0.35)", width=1),
    ), row=4, col=1)
    if df['상승비율MA20'].notna().any():
        fig.add_trace(go.Scatter(
            x=df.index, y=df['상승비율MA20'],
            name="MA20", line=dict(color="#787EE7", width=2),
        ), row=4, col=1)
    for lvl, c in [(60, "rgba(75,255,179,0.45)"),
                   (50, "rgba(255,255,255,0.12)"),
                   (40, "rgba(255,75,110,0.45)")]:
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[lvl, lvl], mode='lines',
            line=dict(color=c, width=0.9, dash='dot'),
            showlegend=False, hoverinfo='skip',
        ), row=4, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)

    # ── Row 4 right: 200MA 상위 비율 — 라인만, 50 중심 y축
    if has_200:
        p200 = df['200MA상위'].dropna()
        fig.add_trace(go.Scatter(
            x=p200.index, y=p200,
            line=dict(color="#C8C850", width=1.8),
            showlegend=False,                          # fill 제거
        ), row=4, col=2)
        p200_center = 50.0
        half = max(abs(float(p200.max()) - p200_center),
                   abs(p200_center - float(p200.min())), 10) * 1.3
        fig.update_yaxes(range=[p200_center - half, p200_center + half], row=4, col=2)
        for lvl, c in [(70, "rgba(75,255,179,0.45)"),
                       (50, "rgba(255,255,255,0.12)"),
                       (30, "rgba(255,75,110,0.45)")]:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[lvl, lvl], mode='lines',
                line=dict(color=c, width=0.9, dash='dot'),
                showlegend=False, hoverinfo='skip',
            ), row=4, col=2)

    fig.update_layout(
        height=1100,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        **_base_layout(),
    )
    fig.update_xaxes(**_axis_kw())
    fig.update_yaxes(**_axis_kw())
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    for ann in fig.layout.annotations:
        ann.font.color = "#777"
        ann.font.size  = 11
    return fig


# ============================================================
# 전역 RSI 임계값 (render_signal_table에서 참조)
# ============================================================
rsi_buy_lower_global = 35    # 기본: 40 - 5
rsi_sell_lower_global = 75   # 기본: 80 - 5


# ============================================================
# 메인 앱
# ============================================================
def main():
    global rsi_buy_lower_global, rsi_sell_lower_global

    st.markdown(DARK_CSS, unsafe_allow_html=True)

    # 항상 파일에서 읽음 → 외부 수정·추가 즉시 반영, 삭제도 정확히 유지됨
    st.session_state.favorites = load_favorites()
    favorites = st.session_state.favorites

    # ─── 사이드바 ─────────────────────────────────────────────
    with st.sidebar:
        # 즐겨찾기 파일 오류가 있을 때만 경고 표시
        if st.session_state.get('_fav_load_err'):
            st.error(f"즐겨찾기 읽기 오류: {st.session_state['_fav_load_err']}")
        if st.session_state.get('_fav_save_err'):
            st.error(f"즐겨찾기 저장 오류: {st.session_state['_fav_save_err']}")
        st.markdown(
            f"<p style='font-size:11px;color:#555;margin:0 0 12px;'>기준일 {datetime.now().strftime('%Y-%m-%d')}</p>",
            unsafe_allow_html=True,
        )
        st.markdown("**📅 차트 기간**")
        period_name = st.radio(
            "기간", list(PERIOD_OPTIONS.keys()), index=1,
            label_visibility="collapsed",
        )
        period_days = PERIOD_OPTIONS[period_name]

        st.divider()

        st.markdown("**📊 BB 기간**")
        bb_window = st.select_slider(
            "bb_window",
            options=[10, 15, 20, 25],
            value=20,
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("**📐 동적 RSI Lookback**")
        rsi_lookback = st.select_slider(
            "lookback",
            options=[20, 30, 40, 60, 120],
            value=40,
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("**⏱ 재진입 유지일 (persist)**")
        persist = st.select_slider(
            "persist",
            options=[1, 2, 3],
            value=2,
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("**⚙ 동적+BB Phase 2 조건**")
        phase2_mode = st.radio(
            "phase2_mode",
            ["BB 선행 진입", "BB·RSI 동시 회복"],
            index=0,
            label_visibility="collapsed",
            help="BB 선행: BB 복귀만 확인 (빠름) | BB·RSI 동시: 둘 다 회복해야 확정 (보수적)",
        )
        phase2_rsi = (phase2_mode == "BB·RSI 동시 회복")

        st.divider()

        st.markdown("**⭐ 즐겨찾기 추가**")
        search_kw = st.text_input(
            "검색", label_visibility="collapsed",
            placeholder="종목명 / 티커 / 종목코드(6자리)...",
        )
        if search_kw and len(search_kw) >= 1:
            import re as _re
            _is_code = bool(_re.fullmatch(r"[0-9A-Z]{6}", search_kw.strip().upper()))
            if _is_code:
                # ── 6자리 코드 직접 입력 ──
                _raw_code = search_kw.strip().upper()
                _mkt_sel = st.radio(
                    "시장", ["코스피(.KS)", "코스닥(.KQ)", "미국(직접입력)"],
                    horizontal=True, label_visibility="collapsed",
                    key="direct_mkt_sel",
                )
                if _mkt_sel == "코스피(.KS)":
                    _direct_code = f"{_raw_code}.KS"
                elif _mkt_sel == "코스닥(.KQ)":
                    _direct_code = f"{_raw_code}.KQ"
                else:
                    _direct_code = _raw_code

                # 1) STOCK_SEARCH_LIST 먼저
                _match = next(
                    (s for s in STOCK_SEARCH_LIST if s['code'] == _direct_code),
                    None
                )
                if _match:
                    _fetched_name = _match['name']
                else:
                    # 2) KRX 한국어 이름 조회 (캐시됨, fallback yfinance)
                    with st.spinner("종목명 조회 중..."):
                        _fetched_name = _lookup_ticker_name(_direct_code)

                # 표시 형식: 종목명 (종목코드)
                if _fetched_name and _fetched_name != _direct_code:
                    _display_name = f"{_fetched_name} ({_raw_code})"
                else:
                    _display_name = _raw_code  # 이름 조회 실패 시 코드만

                st.caption(f"추가 예정: **{_display_name}**")
                if st.button("➕ 직접 추가", use_container_width=True, key="direct_add_btn"):
                    if not any(f['code'] == _direct_code for f in favorites):
                        favorites.append({"code": _direct_code, "name": _display_name})
                        save_favorites(favorites)
                        st.rerun()
                    else:
                        st.caption("이미 추가됨")
            else:
                # ── 이름/티커 검색 ──
                hits = [
                    s for s in STOCK_SEARCH_LIST
                    if search_kw.lower() in s['name'].lower()
                    or search_kw.upper() in s['code'].upper()
                ][:10]
                if hits:
                    sel = st.selectbox(
                        "결과", hits,
                        format_func=lambda x: x['name'],
                        label_visibility="collapsed",
                    )
                    if st.button("➕ 추가", use_container_width=True):
                        if not any(f['code'] == sel['code'] for f in favorites):
                            # (종목코드) 형식으로 저장
                            _sel_raw = sel['code'].split('.')[0]
                            _sel_name = (
                                f"{sel['name']} ({_sel_raw})"
                                if re.match(r'^[0-9A-Z]{6}$', _sel_raw) and '(' not in sel['name']
                                else sel['name']
                            )
                            favorites.append({"code": sel['code'], "name": _sel_name})
                            save_favorites(favorites)
                            st.rerun()
                        else:
                            st.caption("이미 추가됨")
                else:
                    st.caption("검색 결과 없음")

        if favorites:
            st.divider()
            st.markdown("**📋 즐겨찾기 목록**")
            to_remove = None
            for i, fav in enumerate(favorites):
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.caption(fav['name'])
                with c2:
                    if st.button("✕", key=f"rm_{i}"):
                        to_remove = i
            if to_remove is not None:
                favorites.pop(to_remove)
                save_favorites(favorites)
                st.rerun()

    # RSI 임계값 전역 업데이트
    rsi_buy_lower_global = 35   # 40 - 5
    rsi_sell_lower_global = 75  # 80 - 5

    # ─── 타이틀 ───────────────────────────────────────────────
    st.markdown("""
        <div style='margin-bottom:16px;'>
            <p style='color:#555;font-size:11px;text-transform:uppercase;
                      letter-spacing:2px;margin:0 0 4px;font-weight:500;'>
                TECHNICAL SIGNAL SCANNER
            </p>
            <h2 style='margin:0;font-size:22px;font-weight:600;color:#EDEDED;line-height:1.3;'>
                🎯 기술적 신호 스캐너
            </h2>
        </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📊 신호 스캐너", "🌐 시장 내부지표"])

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — 신호 스캐너
    # ═══════════════════════════════════════════════════════════
    with tab1:
        if not favorites:
            st.markdown("""
            <div style='background:#111113;border:1px solid rgba(255,255,255,0.06);
                        border-radius:10px;padding:40px;text-align:center;margin:24px 0;'>
                <p style='color:#555;font-size:14px;margin:0;'>
                    왼쪽 사이드바에서 종목을 검색해서 즐겨찾기에 추가해주세요.
                </p>
            </div>""", unsafe_allow_html=True)
            return

        today = datetime.now().date()
        data_end = str(today + timedelta(days=1))
        # 표시기간 + 워밍업(RSI14 + BB + 동적RSI lookback + 여유) 합산
        data_start = str(today - timedelta(days=period_days + 400))

        # 사이드바에서 이미 bb_window, rsi_lookback, persist 받음
        bb_std         = 2.0
        rsi_period     = 14
        rsi_buy_center = 40
        rsi_sell_center= 80
        rsi_band       = 5

        tickers_tuple = tuple(f['code'] for f in favorites)

        # ── 차트 모드 선택 (스캐너 + 차트 공용) ───────────────────────
        _intra_interval_map = {"5분": "5m", "15분": "15m", "30분": "30m", "60분": "60m"}
        _intra_bars_per_day = {"5m": 78, "15m": 26, "30m": 13, "60m": 7}
        _mode_hdr_col, _intra_hdr_col = st.columns([1, 3])
        with _mode_hdr_col:
            chart_mode = st.radio(
                "차트모드", ["일봉", "분봉"], horizontal=True,
                label_visibility="collapsed", key="chart_mode",
            )
        if chart_mode == "분봉":
            with _intra_hdr_col:
                intra_interval_label = st.radio(
                    "분봉", list(_intra_interval_map.keys()), horizontal=True,
                    label_visibility="collapsed", key="intra_interval",
                )
            yf_interval = _intra_interval_map[intra_interval_label]
        else:
            intra_interval_label = None
            yf_interval = None

        with st.spinner("📡 데이터 로딩..."):
            if chart_mode == "분봉":
                closes = fetch_intraday_batch(tickers_tuple, yf_interval)
            else:
                closes = fetch_close_batch(tickers_tuple, data_start, data_end)

        # 신호 계산
        signal_rows = []
        for fav in favorites:
            code = fav['code']
            row = {
                'code': code, 'name': fav['name'],
                'close': None, 'pct_change': None, 'rsi': None,
                'bb_upper_touch': False, 'bb_lower_touch': False,
                'dyn_buy_signal': False, 'dyn_sell_signal': False,
                'band_buy_signal': False, 'band_sell_signal': False,
                'dyn_buy_flag': False, 'dyn_sell_flag': False,
                'band_buy_flag': False, 'band_sell_flag': False,
                'dyn_holding': False, 'band_holding': False,
            }
            if code in closes.columns:
                series = closes[code].dropna()
                sig = get_current_signals(
                    series,
                    bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
                    rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
                    rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
                    phase2_rsi=phase2_rsi,
                )
                if sig:
                    row.update(sig)
                elif len(series) >= 2:
                    # 신호 계산 불가(데이터 부족)이어도 가격·등락률은 표시
                    last = float(series.iloc[-1])
                    prev = float(series.iloc[-2])
                    row['close'] = last
                    row['pct_change'] = (last / prev - 1) * 100 if prev else 0.0
            signal_rows.append(row)

        # 확정 신호 > 보유 중 > 플래그 > 없음 순 정렬
        def sort_key(r):
            confirmed = r.get('dyn_buy_signal') or r.get('dyn_sell_signal') or \
                        r.get('band_buy_signal') or r.get('band_sell_signal')
            holding   = r.get('dyn_holding') or r.get('band_holding')
            flagging  = r.get('dyn_buy_flag') or r.get('dyn_sell_flag') or \
                        r.get('band_buy_flag') or r.get('band_sell_flag')
            return (0 if confirmed else 1 if holding else 2 if flagging else 3)

        signal_rows.sort(key=sort_key)

        # 신호 요약 카운트 (5가지 상태 × 2전략)
        n_dyn_buy_flag  = sum(1 for r in signal_rows if r.get('dyn_buy_flag')  and not r.get('dyn_buy_signal'))
        n_dyn_buy       = sum(1 for r in signal_rows if r.get('dyn_buy_signal'))
        n_dyn_hold      = sum(1 for r in signal_rows if r.get('dyn_holding'))
        n_dyn_sell_flag = sum(1 for r in signal_rows if r.get('dyn_sell_flag') and not r.get('dyn_sell_signal'))
        n_dyn_sell      = sum(1 for r in signal_rows if r.get('dyn_sell_signal'))

        n_band_buy_flag  = sum(1 for r in signal_rows if r.get('band_buy_flag')  and not r.get('band_buy_signal'))
        n_band_buy       = sum(1 for r in signal_rows if r.get('band_buy_signal'))
        n_band_hold      = sum(1 for r in signal_rows if r.get('band_holding'))
        n_band_sell_flag = sum(1 for r in signal_rows if r.get('band_sell_flag') and not r.get('band_sell_signal'))
        n_band_sell      = sum(1 for r in signal_rows if r.get('band_sell_signal'))

        def _mini_card(label, value, accent="#787EE7"):
            return (f'<div style="flex:1;min-width:0;background:#141416;'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:6px;'
                    f'padding:5px 10px 6px;">'
                    f'<div style="font-size:9px;color:#444;text-transform:uppercase;'
                    f'letter-spacing:0.7px;white-space:nowrap;overflow:hidden;'
                    f'text-overflow:ellipsis;">{label}</div>'
                    f'<div style="font-size:17px;font-weight:600;color:{accent};'
                    f'margin-top:1px;font-variant-numeric:tabular-nums;">{value}</div>'
                    f'</div>')

        def _mini_row(prefix, items):
            cards = "".join(_mini_card(f"{prefix} {lbl}", val, acc) for lbl, val, acc in items)
            return (f'<div style="display:flex;gap:5px;margin-bottom:5px;">'
                    f'{cards}</div>')

        st.markdown(_mini_row("★", [
            ("매수 플래그", f"{n_dyn_buy_flag}",  "#7AAFD4"),
            ("매수 신호",   f"{n_dyn_buy}",        "#4BFFB3"),
            ("보유 중",     f"{n_dyn_hold}",       "#C8C850"),
            ("매도 플래그", f"{n_dyn_sell_flag}",  "#D47A9F"),
            ("매도 신호",   f"{n_dyn_sell}",       "#FF4B6E"),
        ]), unsafe_allow_html=True)
        st.markdown(_mini_row("●", [
            ("매수 플래그", f"{n_band_buy_flag}",  "#7AAFD4"),
            ("매수 신호",   f"{n_band_buy}",        "#4BFFB3"),
            ("보유 중",     f"{n_band_hold}",       "#50C878"),
            ("매도 플래그", f"{n_band_sell_flag}",  "#D47A9F"),
            ("매도 신호",   f"{n_band_sell}",       "#FF4B6E"),
        ]), unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown(render_signal_table(signal_rows), unsafe_allow_html=True)

        # ── 디테일 차트 구분선
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("""
            <p style='font-size:10px;color:#444;text-transform:uppercase;
                      letter-spacing:1.5px;margin:0 0 6px;'>DETAIL CHART</p>
        """, unsafe_allow_html=True)

        fav_names = [f['name'] for f in favorites]
        selected_name = st.selectbox(
            "종목 선택", fav_names, index=0,
            label_visibility="collapsed",
        )
        selected_fav = next((f for f in favorites if f['name'] == selected_name), favorites[0])

        # ── 일봉 차트 ──────────────────────────────────────
        if chart_mode == "일봉":
            with st.spinner("차트 로딩..."):
                ohlcv = fetch_ohlcv(selected_fav['code'], data_start, data_end)

            if ohlcv.empty:
                st.warning(f"⚠️ {selected_name} 데이터를 가져올 수 없습니다.")
            else:
                fig = make_detail_chart(
                    ohlcv, selected_name, period_days,
                    bb_window=bb_window, rsi_lookback=rsi_lookback,
                    rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                    persist=persist, phase2_rsi=phase2_rsi,
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                else:
                    close = ohlcv['Close'].dropna()
                    have  = len(close)
                    need  = bb_window + 14 + rsi_lookback // 2
                    first_date = close.index[0].strftime('%Y-%m-%d') if have > 0 else '—'
                    st.markdown(
                        f'<div style="background:#141416;border:1px solid rgba(255,140,0,0.3);'
                        f'border-radius:8px;padding:10px 16px;margin-bottom:10px;font-size:12px;color:#FFB347;">'
                        f'⏳ 신호 계산 데이터 부족 — 현재 <b>{have}일</b> / 필요 <b>{need}일</b> '
                        f'(상장: {first_date})</div>',
                        unsafe_allow_html=True,
                    )
                    if have >= 3:
                        price_fig = go.Figure()
                        price_fig.add_trace(go.Scatter(
                            x=close.index, y=close,
                            line=dict(color="#787EE7", width=1.8), showlegend=False,
                        ))
                        price_fig.update_layout(
                            height=320, title=dict(text=selected_name, font=dict(size=13, color="#9B9B9B")),
                            **_base_layout(),
                        )
                        price_fig.update_xaxes(**_axis_kw())
                        price_fig.update_yaxes(**_axis_kw())
                        st.plotly_chart(price_fig, use_container_width=True, config={"displayModeBar": False})

        # ── 분봉 차트 ──────────────────────────────────────
        else:
            _disp_opts = {3: "3일", 5: "5일", 10: "10일", 20: "20일", 30: "30일"}
            intra_disp_days = st.select_slider(
                "표시기간", options=list(_disp_opts.keys()),
                value=5, format_func=lambda x: _disp_opts[x],
                label_visibility="collapsed", key="intra_disp_days",
            )
            _ticker = selected_fav['code']
            with st.spinner(f"분봉 로딩... ({intra_interval_label}, 최근 60일 기준)"):
                ohlcv_intra = fetch_intraday(_ticker, yf_interval)

            if ohlcv_intra.empty:
                st.warning(f"⚠️ {selected_name} 분봉 데이터를 가져올 수 없습니다.")
            else:
                _disp_bars = _intra_bars_per_day[yf_interval] * intra_disp_days
                _session   = (15.5, 9.0) if _ticker.endswith(('.KS', '.KQ')) else None
                fig_intra  = make_detail_chart(
                    ohlcv_intra, f"{selected_name} ({intra_interval_label})", period_days,
                    bb_window=bb_window, rsi_lookback=rsi_lookback,
                    rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                    persist=persist, phase2_rsi=phase2_rsi,
                    display_bars=_disp_bars,
                    intraday_session=_session,
                )
                if fig_intra:
                    st.plotly_chart(fig_intra, use_container_width=True, config={"displayModeBar": False})
                else:
                    close_intra = ohlcv_intra['Close'].dropna()
                    have  = len(close_intra)
                    need  = bb_window + 14 + rsi_lookback // 2
                    st.markdown(
                        f'<div style="background:#141416;border:1px solid rgba(255,140,0,0.3);'
                        f'border-radius:8px;padding:10px 16px;margin-bottom:10px;font-size:12px;color:#FFB347;">'
                        f'⏳ 분봉 신호 계산 데이터 부족 — 현재 <b>{have}봉</b> / 필요 <b>{need}봉</b></div>',
                        unsafe_allow_html=True,
                    )
                    if have >= 3:
                        pf = go.Figure()
                        pf.add_trace(go.Scatter(
                            x=close_intra.index, y=close_intra,
                            line=dict(color="#787EE7", width=1.5), showlegend=False,
                        ))
                        pf.update_layout(
                            height=320,
                            title=dict(text=f"{selected_name} ({intra_interval_label})",
                                       font=dict(size=13, color="#9B9B9B")),
                            **_base_layout(),
                        )
                        pf.update_xaxes(**_axis_kw())
                        pf.update_yaxes(**_axis_kw())
                        if _session:
                            close_h, open_h = _session
                            pf.update_xaxes(rangebreaks=[
                                dict(bounds=["sat", "mon"]),
                                dict(bounds=[close_h, open_h], pattern="hour"),
                            ])
                        st.plotly_chart(pf, use_container_width=True, config={"displayModeBar": False})

        # 신호 설명
        with st.expander("📖 신호 해석 가이드"):
            st.markdown("""
            **BB 신호**
            - 🟢 **BB↓ 하단**: 종가가 볼린저밴드 하단에 접촉 → 과매도 구간, 반등 가능성 모니터링
            - 🔴 **BB↑ 상단**: 종가가 볼린저밴드 상단에 접촉 → 과열 구간, 조정 가능성 모니터링

            **RSI 신호** (기준: 매수 40±5, 매도 80±5)
            - 🟢 **RSI 매수존**: RSI가 35~45 구간 진입 → 눌림/저점 구간
            - 🔴 **RSI 매도존**: RSI가 75~85 구간 진입 → 과열/고점 구간

            **⭐ 복합 신호**: BB 하단 터치 + RSI 매수존 동시 발생 (또는 BB 상단 + RSI 매도존)
            → 두 지표가 같은 방향을 가리킬 때 신호 신뢰도가 높아짐

            > 이 신호는 참고 지표이며, 실제 매매 결정은 추가 분석 후 본인 판단으로 하세요.
            """)

    # ═══════════════════════════════════════════════════════════
    # TAB 2 — 시장 내부지표
    # ═══════════════════════════════════════════════════════════
    with tab2:
        col_mkt, col_period, _ = st.columns([2, 2, 2])
        with col_mkt:
            market_choice = st.radio(
                "시장", ["코스피", "코스닥", "S&P 500", "나스닥 100"],
                horizontal=True,
                label_visibility="collapsed",
            )
        with col_period:
            _mkt_labels = {
                20: "20일", 40: "40일", 60: "60일",
                63: "3개월", 126: "6개월", 189: "9개월",
                252: "1년", 378: "1년 6개월",
                504: "2년", 756: "3년", 1008: "4년",
            }
            mkt_lookback = st.select_slider(
                "기간", options=list(_mkt_labels.keys()),
                value=63, format_func=lambda x: _mkt_labels[x],
                label_visibility="collapsed",
            )

        with st.spinner("📡 시장 데이터 로딩 중... (전체 종목 첫 로딩 시 1분 소요, 이후 1시간 캐시)"):
            market_df, err = get_market_internals(market_choice, lookback_days=mkt_lookback)

        if err:
            st.error("데이터 로드 실패 — 아래 에러 전문을 복사해서 공유해주세요")
            st.code(err, language="python")
        elif market_df is not None and not market_df.empty:
            latest = market_df.iloc[-1]
            prev = market_df.iloc[-2] if len(market_df) >= 2 else latest

            # ── 시장 감성 요약 (맨 위)
            st.markdown(
                _market_sentiment_html(market_df, market_choice),
                unsafe_allow_html=True,
            )

            # ── 소형 메트릭 카드 (신호 스캐너와 동일 스타일)
            def _mkt_card(label, value, delta="", accent="#787EE7"):
                dlt = (f'<div style="font-size:9px;color:#555;margin-top:1px;">{delta}</div>'
                       if delta else "")
                return (
                    f'<div style="flex:1;min-width:0;background:#141416;'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:6px;'
                    f'padding:5px 10px 6px;">'
                    f'<div style="font-size:9px;color:#444;text-transform:uppercase;'
                    f'letter-spacing:0.6px;white-space:nowrap;overflow:hidden;'
                    f'text-overflow:ellipsis;">{label}</div>'
                    f'<div style="font-size:15px;font-weight:600;color:{accent};'
                    f'margin-top:1px;font-variant-numeric:tabular-nums;">{value}</div>'
                    f'{dlt}</div>'
                )

            def _mkt_row(cards_html):
                return (f'<div style="display:flex;gap:5px;margin-bottom:5px;">'
                        f'{cards_html}</div>')

            mcc_val  = float(latest['맥클렐란'])
            summ_val = float(latest['서머레이션'])
            vix_val  = latest['VIX']
            ma20_val = latest['상승비율MA20']
            p200_val = latest['200MA상위']
            adl_chg  = float(latest['ADL'] - prev['ADL'])
            vix_lbl  = "VKOSPI" if market_choice in ("코스피", "코스닥") else "VIX"

            row1 = "".join([
                _mkt_card("시총가중",
                    f"{latest['시총가중']:.1f}",
                    f"{latest['시총가중']-prev['시총가중']:+.2f}",
                    "#00FF7F" if latest['시총가중'] > prev['시총가중'] else "#FF4B6E"),
                _mkt_card("균일가중",
                    f"{latest['균일가중']:.1f}",
                    f"{latest['균일가중']-prev['균일가중']:+.2f}",
                    "#FFD700" if latest['균일가중'] > prev['균일가중'] else "#FF4B6E"),
                _mkt_card("ADL",
                    f"{latest['ADL']:.0f}",
                    f"{adl_chg:+.0f}",
                    "#4BFFB3" if adl_chg >= 0 else "#FF4B6E"),
                _mkt_card("오실레이터",
                    f"{mcc_val:+.1f}",
                    "과열" if mcc_val > 60 else ("침체" if mcc_val < -60 else "중립"),
                    "#4BFFB3" if mcc_val > 0 else "#FF4B6E"),
                _mkt_card("서머레이션",
                    f"{summ_val:+.0f}",
                    "강세구간" if summ_val > 0 else "약세구간",
                    "#4BFFB3" if summ_val > 0 else "#FF4B6E"),
                _mkt_card(vix_lbl,
                    f"{vix_val:.1f}" if pd.notna(vix_val) else "—",
                    "공포" if (pd.notna(vix_val) and float(vix_val) > 30)
                    else ("탐욕" if (pd.notna(vix_val) and float(vix_val) < 20) else "중립"),
                    "#FFB347"),
                _mkt_card("상승비율MA20",
                    f"{ma20_val:.1f}%" if pd.notna(ma20_val) else "—",
                    "",
                    "#4BFFB3" if (pd.notna(ma20_val) and float(ma20_val) > 50) else "#FF4B6E"),
                _mkt_card("200MA 상위",
                    f"{p200_val:.1f}%" if pd.notna(p200_val) else "—",
                    "강세장" if (pd.notna(p200_val) and float(p200_val) > 70)
                    else ("약세장" if (pd.notna(p200_val) and float(p200_val) < 30) else "중립"),
                    "#C8C850"),
            ])
            st.markdown(_mkt_row(row1), unsafe_allow_html=True)

            n_med  = int(market_df['전체종목수'].median())
            full_t = get_full_ticker_list(market_choice)
            n_full = len(full_t) if full_t else 0
            if n_full:
                src_label = f"전체 {n_full}종목"
            elif market_choice in ("코스피", "코스닥"):
                src_label = "대형주 바스켓 (fallback)"
            else:
                src_label = "구성종목"
            st.caption(
                f"기준: {src_label} | 데이터 유효 (중앙값): {n_med}개 | "
                f"최근 상승: {int(latest['상승종목수'])}개 / {int(latest['전체종목수'])}개"
            )

            st.plotly_chart(
                make_market_chart(market_df, market_choice),
                use_container_width=True,
                config={"displayModeBar": False},
            )

            with st.expander("📖 시장 지표 해석 가이드 — 처음 보는 분도 바로 활용 가능", expanded=False):
                st.markdown("""
<style>
.guide-table { width:100%; border-collapse:collapse; font-size:12px; }
.guide-table th { background:#1a1a2e; color:#787EE7; padding:6px 10px; text-align:left; border-bottom:1px solid #2a2a3e; }
.guide-table td { padding:5px 10px; border-bottom:1px solid #1e1e2e; vertical-align:top; line-height:1.5; }
.guide-table tr:hover td { background:rgba(120,126,231,0.04); }
.bull { color:#4BFFB3; font-weight:600; }
.bear { color:#FF4B6E; font-weight:600; }
.neut { color:#C8C850; font-weight:600; }
</style>

<table class="guide-table">
<tr>
  <th>지표</th><th>측정 대상</th><th>🟢 강세 신호</th><th>🔴 약세 신호</th><th>활용법</th>
</tr>
<tr>
  <td><b>시총가중 지수</b></td>
  <td>대형주 중심 실질 시장</td>
  <td class="bull">우상향</td>
  <td class="bear">우하향</td>
  <td>삼성전자·SK하이닉스 등 대형주가 시장을 끌어올리는지 확인</td>
</tr>
<tr>
  <td><b>균일가중 지수</b></td>
  <td>전체 종목 고른 참여</td>
  <td class="bull">시총가중과 함께 상승</td>
  <td class="bear">시총가중만 오르고 균일은 정체</td>
  <td>두 지수가 같이 오르면 <span class="bull">폭넓은 강세장</span>. 괴리 커지면 <span class="bear">대형주 쏠림</span> 경계</td>
</tr>
<tr>
  <td><b>시총÷균일 비율</b></td>
  <td>대형주 vs 중소형주 힘 싸움</td>
  <td class="bull">평균 이하 (중소형 강세)</td>
  <td class="bear">평균 이상으로 급등 (대형 쏠림)</td>
  <td>비율이 평균보다 높으면 일부 대형주만 끌어올리는 취약한 장세</td>
</tr>
<tr>
  <td><b>ADL (등락누적선)</b></td>
  <td>시장 방향·건강도</td>
  <td class="bull">우상향 추세</td>
  <td class="bear">지수는 오르는데 ADL 하락 (다이버전스)</td>
  <td><b>핵심 선행지표.</b> ADL이 지수보다 먼저 꺾이면 조정 임박 신호. 반대로 ADL이 먼저 올라오면 반등 초입</td>
</tr>
<tr>
  <td><b>맥클렐란 오실레이터</b></td>
  <td>단기 과매수/과매도</td>
  <td class="bull">-60 이하 → 역발상 매수 구간</td>
  <td class="bear">+60 이상 → 단기 과열, 차익실현 주의</td>
  <td>±60선을 절대 기준으로 사용. 0선 위에서 유지되면 상승 모멘텀 지속</td>
</tr>
<tr>
  <td><b>맥클렐란 서머레이션</b></td>
  <td>중기 사이클 위치</td>
  <td class="bull">0 이상 유지, +1000 이상 = 강세장</td>
  <td class="bear">0 이하 전환 = 약세장 진입, -1000 이하 = 침체</td>
  <td>오실레이터의 누적합. <b>내가 지금 강세장에 있는지 약세장에 있는지</b> 가장 빠르게 알려줌. 0선 돌파가 추세 전환 신호</td>
</tr>
<tr>
  <td><b>VIX / VKOSPI (공포지수)</b></td>
  <td>시장 공포·불확실성</td>
  <td class="bull">30 이상 → 극단 공포 = 역발상 매수 타이밍</td>
  <td class="bear">20 이하 유지 후 급등 → 조정 전조</td>
  <td>VIX 20 이하 = 시장 안도, 20~30 = 경계, 30 이상 = 공포 구간. <b>공포 극대 = 바닥 근처</b>가 역사적 경험</td>
</tr>
<tr>
  <td><b>상승비율 & MA20</b></td>
  <td>당일 시장 폭</td>
  <td class="bull">MA20 > 60% 유지</td>
  <td class="bear">MA20 < 40%로 하락</td>
  <td>단일 일수치는 노이즈 많음. <b>20일 평균선</b>이 50% 위면 상승 추세 건강, 아래면 약세 흐름</td>
</tr>
<tr>
  <td><b>200일선 상위 비율</b></td>
  <td>장기 상승추세 종목 비율</td>
  <td class="bull">70% 이상 = 전형적 강세장</td>
  <td class="bear">30% 이하 = 약세장 확인, 20% 이하 = 침체 바닥권</td>
  <td><b>"몇 % 종목이 장기 상승추세 위에 있나".</b> 하락장에서 30% 이하 도달 후 반등하면 강력한 바닥 신호</td>
</tr>
</table>

<br>

**🗺️ 지표 조합으로 시장 읽기 — 4가지 국면**

| 국면 | ADL | 서머레이션 | 200MA상위 | VIX | 대응 |
|------|-----|-----------|-----------|-----|------|
| **강세장 초입** | 반등 시작 | 0선 상향 돌파 | 30→50% 회복 | 30 이상 후 하락 | 적극 매수 구간 |
| **강세장 중반** | 우상향 | +500 이상 | 60~80% | 20 이하 | 보유 유지, 추격 매수 자제 |
| **강세장 말기** | 지수 대비 다이버전스 | +1000 이상 후 정체 | 70% 이상 | 15 이하 과신 | 비중 축소, 차익실현 준비 |
| **약세장** | 우하향 | 0선 이하 | 30% 이하 | 30 이상 | 현금 비중 확대, 반등 시 매도 |

> **균일가중 지수**는 공식 지수가 아니라 전종목 종가로 직접 계산한 참고 지표입니다.
> 데이터 기준일이 최신 거래일 기준이며, 첫 로딩 시 전체 종목 다운로드로 1~2분 소요됩니다.
                """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
