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
    _PYKRX_IMPORT_ERR = None
except Exception as _e:
    PYKRX_AVAILABLE = False
    _PYKRX_IMPORT_ERR = f"{type(_e).__name__}: {_e}"

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False


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
    [data-testid="stHeader"]               { background: transparent !important; border: none !important; height: 0 !important; overflow: visible !important; }
    [data-testid="stToolbar"]              { display: none !important; }
    [data-testid="stDecoration"]           { display: none !important; }
    [data-testid="stStatusWidget"]         { display: none !important; }
    #MainMenu                              { display: none !important; }
    footer                                 { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] {
        position: fixed !important; top: 8px !important; left: 8px !important;
        z-index: 99999 !important; display: flex !important;
        visibility: visible !important; opacity: 1 !important; }
    [data-testid="stSidebarCollapsedControl"] button {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #EDEDED !important; border-radius: 6px !important;
        width: 32px !important; height: 32px !important;
        display: flex !important; align-items: center !important; justify-content: center !important; }
    [data-testid="stSidebarCollapseButton"] { display: flex !important; visibility: visible !important; }
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

# 최후 fallback 바스켓 — pykrx / Wikipedia 둘 다 실패했을 때만 사용
# 한국은 시총 상위 종목, 미국은 Wikipedia 성공 시 전체가 사용되므로 fallback은 참고용
_KOSPI_BASKET = [
    # 시총 1~50위권
    "005930.KS","000660.KS","207940.KS","005380.KS","000270.KS","068270.KS",
    "035420.KS","051910.KS","028260.KS","012330.KS","066570.KS","003550.KS",
    "035720.KS","086790.KS","055550.KS","105560.KS","032830.KS","003490.KS",
    "034730.KS","015760.KS","009150.KS","000810.KS","010130.KS","024110.KS",
    "096770.KS","033780.KS","018260.KS","010950.KS","011200.KS","006400.KS",
    "008770.KS","047050.KS","316140.KS","000100.KS","161390.KS","003670.KS",
    "004020.KS","009540.KS","010140.KS","011070.KS","000720.KS","011780.KS",
    "036460.KS","030200.KS","017670.KS","051600.KS","016360.KS","069960.KS",
    "271560.KS","004170.KS",
    # 시총 51~100위권
    "090430.KS","051900.KS","032640.KS","078930.KS","071050.KS","005940.KS",
    "139480.KS","000080.KS","035250.KS","042660.KS","009830.KS","012450.KS",
    "000120.KS","001040.KS","097950.KS","128940.KS","145990.KS","004990.KS",
    "023530.KS","047810.KS","064350.KS","267250.KS","329180.KS","006260.KS",
    "180640.KS","139130.KS","175330.KS","138930.KS","002380.KS","011790.KS",
    "298040.KS","004000.KS","052690.KS","006360.KS","028670.KS","008300.KS",
    "002790.KS","034220.KS","021240.KS","006280.KS","029780.KS","068760.KS",
    "079550.KS","014680.KS","003030.KS","001230.KS","011210.KS","069620.KS",
    "185750.KS","000210.KS",
    # 시총 101~200위권
    "005490.KS","036570.KS","034020.KS","088350.KS","006800.KS","010120.KS",
    "018880.KS","086280.KS","251270.KS","000150.KS","011170.KS","007310.KS",
    "082640.KS","014820.KS","003410.KS","006650.KS","007070.KS","000070.KS",
    "017960.KS","002350.KS","005830.KS","069260.KS","001450.KS","006110.KS",
    "001800.KS","047040.KS","010060.KS","019170.KS","003620.KS","089470.KS",
    "005387.KS","003240.KS","002240.KS","001740.KS","001680.KS","004560.KS",
    "006120.KS","003690.KS","021080.KS","002310.KS","001060.KS","004430.KS",
    "002600.KS","003160.KS","006370.KS","027390.KS","001720.KS","003100.KS",
    "002780.KS","001510.KS",
]
_KOSDAQ_BASKET = [
    # 시총 1~30위권
    "247540.KQ","086520.KQ","196170.KQ","214150.KQ","039030.KQ","357780.KQ",
    "066970.KQ","121600.KQ","145020.KQ","178920.KQ","041510.KQ","035900.KQ",
    "122870.KQ","263720.KQ","112040.KQ","091990.KQ","058470.KQ","236200.KQ",
    "048410.KQ","060310.KQ","041960.KQ","323410.KQ","206950.KQ","240810.KQ",
    "950130.KQ","096530.KQ","000250.KQ","285130.KQ","086900.KQ","228760.KQ",
    # 시총 31~100위권
    "028300.KQ","141080.KQ","293490.KQ","263750.KQ","053800.KQ","084370.KQ",
    "098460.KQ","056190.KQ","183300.KQ","044820.KQ","298380.KQ","237690.KQ",
    "277810.KQ","095660.KQ","393890.KQ","248070.KQ","079370.KQ","049070.KQ",
    "352480.KQ","319660.KQ","214450.KQ","290650.KQ","310210.KQ","067920.KQ",
    "039200.KQ","095700.KQ","042700.KQ","033240.KQ","024720.KQ","085510.KQ",
    "078160.KQ","338220.KQ","372170.KQ","263860.KQ","253840.KQ","084990.KQ",
    "258790.KQ","376930.KQ","175250.KQ","357880.KQ","394280.KQ","025320.KQ",
    "049580.KQ","232680.KQ","019540.KQ","036540.KQ","108860.KQ","054780.KQ",
    "102940.KQ","069140.KQ","082270.KQ","050120.KQ","039490.KQ","066620.KQ",
    "078520.KQ","067310.KQ","016290.KQ","186230.KQ","051780.KQ","039830.KQ",
    "050760.KQ","093640.KQ","048260.KQ","054450.KQ","089150.KQ","066490.KQ",
    "073190.KQ","033290.KQ","038540.KQ","060900.KQ",
    # 시총 101~200위권
    "145720.KQ","101930.KQ","036030.KQ","131030.KQ","039440.KQ","094360.KQ",
    "007390.KQ","215600.KQ","131290.KQ","064760.KQ","064550.KQ","036800.KQ",
    "900290.KQ","220180.KQ","347890.KQ","068760.KQ","950170.KQ","241170.KQ",
    "035760.KQ","086360.KQ","065500.KQ","038870.KQ","078600.KQ","214610.KQ",
    "090470.KQ","060250.KQ","019180.KQ","032510.KQ","040300.KQ","217270.KQ",
    "025900.KQ","036620.KQ","950160.KQ","119610.KQ","023160.KQ","032640.KQ",
    "043650.KQ","101160.KQ","078130.KQ","026040.KQ","065350.KQ","200130.KQ",
    "078340.KQ","054620.KQ","032500.KQ","114810.KQ","222800.KQ","047560.KQ",
    "048550.KQ","950140.KQ",
]
# S&P 500 fallback — Wikipedia 실패 시. 시총 상위 ~200종
_SP500_BASKET = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AVGO","BRK-B",
    "JPM","LLY","V","UNH","XOM","MA","COST","JNJ","HD","PG",
    "ABBV","MRK","BAC","CRM","CVX","NFLX","KO","ORCL","AMD","PEP",
    "TMO","WMT","ACN","MCD","IBM","CSCO","TXN","QCOM","CAT","GE",
    "DHR","ABT","AMGN","NOW","INTU","GS","BLK","AMAT","SPGI","DE",
    "HON","LMT","ELV","MDT","RTX","SYK","ISRG","AXP","SCHW","DUK",
    "SO","NEE","BMY","GILD","CI","CB","MMC","PLD","AMT","COP",
    "SLB","USB","BK","MS","TJX","MDLZ","ADI","REGN","VRTX","ZTS",
    "CME","AON","ITW","MO","CCI","SHW","MMM","FDX","NSC","UNP",
    "CSX","NKE","SBUX","MCO","ADBE","PANW","KLAC","LRCX","MU","MRVL",
    "CDNS","SNPS","APH","TEL","TT","ETN","PH","ROK","SRE","D",
    "EXC","XEL","WM","RSG","CTAS","PAYX","ADP","ORLY","ROST","TGT",
    "DLTR","DG","EBAY","PYPL","ETSY","SQ","COIN","BKNG","MAR","HLT",
    "MGM","WYNN","LVS","EW","BSX","BDX","IDXX","IQV","CRL","DXCM",
    "A","ILMN","MRNA","BIIB","REGN","HUM","CVS","MCK","CAH","ABC",
    "WBA","RAD","GEHC","HCA","UHS","THC","CNC","MOH","WCG","ANTM",
    "AFL","MET","PRU","AIG","ALL","TRV","HIG","LNC","PFG","GL",
    "PNC","TFC","CFG","KEY","FHN","SNV","CMA","ZION","RF","FITB",
    "MTB","WAL","PACW","FRC","SIVB","VZ","T","TMUS","LUMN","DISH",
]
# 나스닥 200 — NDX-100 + 시총 상위 추가 기술/성장주 (Wikipedia 실패 시 fallback)
_NDX_BASKET = [
    # ── NDX-100
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
    "NFLX","AMD","ADBE","QCOM","CSCO","PEP","AMGN","INTU","TXN","HON",
    "AMAT","SBUX","GILD","MDLZ","REGN","VRTX","MU","KLAC","LRCX","ADI",
    "PANW","MRVL","CDNS","SNPS","CTAS","ORLY","FTNT","MNST","ROST","PAYX",
    "PCAR","ADP","CPRT","KDP","MELI","CEG","DXCM","IDXX","PYPL","ZS",
    "ON","ILMN","VRSK","FAST","GEHC","EXC","FANG","WBD","TTWO","ASML",
    "TEAM","CRWD","DASH","TTD","BIIB","ANSS","APP","WDAY","MCHP","AEP",
    "CCEP","CTSH","FSLR","ODFL","LULU","EA","BKR","XEL","DLTR","ENPH",
    "ALGN","MRNA","AZN","ABNB","GFS","CHTR","ARM","CSX","NXPI","ROP",
    "SMCI","INTC","ISRG","LBTYA","PDD","SGEN","SPLK","MTCH","DDOG","ZI",
    # ── 나스닥 101~200 (시총 기준 추가 기술/성장주)
    "PLTR","COIN","ZM","DOCU","OKTA","SOFI","AFRM","RIVN","LCID","HOOD",
    "NBIX","HOLX","ALNY","BMRN","EXAS","JAZZ","INCY","SRPT","NVAX","NKTR",
    "IBKR","NDAQ","LPLA","MKTX","SEIC","EPAM","GDDY","FFIV","NTAP","KEYS",
    "QRVO","SWKS","ZBRA","CGNX","CHKP","AKAM","CMCSA","PINS","SNAP","RDDT",
    "BILL","TOST","UPST","PAYC","WEX","EXPE","FOXA","SIRI","MDB","CSGP",
    "LBTYK","NIO","LI","XPEV","ARWR","ACAD","CFLT","GTLB","NTNX","MNDY",
    "LYFT","UBER","NET","SNOW","DKNG","WYNN","HIMS","JOBY","PCTY","APPF",
    "PTON","OPEN","RBLX","U","ACHR","WK","NCNO","PSTG","PCOR","GWRE",
    "SMAR","COUP","MQ","FOUR","FLYW","RELY","PAYO","SMWB","RGEN","FOLD",
    "RARE","LEGN","RCKT","KRYS","VERA","PRAX","RXRX","CERE","KRTX","ACMR",
]

PERIOD_OPTIONS = {
    "1일":     1,
    "3일":     3,
    "1주일":   5,
    "2주일":   10,
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
        border-radius: 8px; margin-bottom: 0px !important; margin-top: 0px !important; }
    div[data-testid="stVerticalBlock"] { gap: 4px !important; }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 1rem !important; }
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


def _fetch_intraday_pykrx(krx_code: str, interval: str, lookback_days: int = 10) -> pd.DataFrame:
    """pykrx로 한국 종목 분봉 조회 (yfinance fallback용).
    1분봉을 target interval로 리샘플링해 OHLCV 반환.
    """
    if not PYKRX_AVAILABLE:
        return pd.DataFrame()
    _col_map = {'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'}
    _resample = {'5m': '5min', '15m': '15min', '30m': '30min', '60m': '60min'}
    rule = _resample.get(interval, '5min')

    frames = []
    today = datetime.now().date()
    d = today
    found = 0
    for _ in range(lookback_days * 3):  # 주말·공휴일 고려
        if found >= lookback_days:
            break
        if d.weekday() >= 5:
            d -= timedelta(days=1)
            continue
        try:
            df_1m = pykrx_stock.get_market_ohlcv_by_minute(d.strftime('%Y%m%d'), krx_code)
            if df_1m is not None and not df_1m.empty:
                df_1m = df_1m.rename(columns=_col_map)
                df_1m.index = pd.to_datetime(df_1m.index)
                frames.append(df_1m)
                found += 1
        except Exception:
            pass
        d -= timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames[::-1])  # oldest first

    # 거래 없는 분(체결 공백) ffill → 15:30까지 봉 생성, 확정 안 된 봉도 포함
    try:
        _filled = []
        for _d, _grp in combined.groupby(combined.index.date):
            _d_ts = pd.Timestamp(_d)
            _session = pd.date_range(
                _d_ts + pd.Timedelta('9h'),
                _d_ts + pd.Timedelta('15h29m'),
                freq='1min'
            )
            _grp = _grp.reindex(_session)
            _grp[['Open', 'High', 'Low', 'Close']] = (
                _grp[['Open', 'High', 'Low', 'Close']].ffill()
            )
            _grp['Volume'] = _grp['Volume'].fillna(0)
            _filled.append(_grp.dropna(subset=['Close']))
        if _filled:
            combined = pd.concat(_filled)
    except Exception:
        pass

    ohlcv = (combined
             .resample(rule, label='right', closed='left')
             .agg(Open=('Open', 'first'), High=('High', 'max'),
                  Low=('Low', 'min'), Close=('Close', 'last'),
                  Volume=('Volume', 'sum'))
             .dropna(subset=['Close']))
    return ohlcv[['Open', 'High', 'Low', 'Close', 'Volume']]


# ── KIS API (한국투자증권) 실시간 분봉 ─────────────────────────────────────────

@st.cache_data(ttl=1800)
def _kis_token():
    """KIS OAuth 토큰 발급 (30분 캐시). 실패/미설정 시 None 반환."""
    try:
        import requests as _req
        cfg = dict(st.secrets.get("kis", {}))
        if not cfg.get("app_key"):
            return None
        _base = ("https://openapivts.koreainvestment.com:9443"
                 if cfg.get("is_mock", True)
                 else "https://openapi.koreainvestment.com:9443")
        r = _req.post(f"{_base}/oauth2/tokenP",
                      json={"grant_type": "client_credentials",
                            "appkey": cfg["app_key"],
                            "appsecret": cfg["app_secret"]},
                      timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception:
        return None


@st.cache_data(ttl=30)
def _fetch_kis_today(krx_code: str):
    """KIS 당일 1분봉 조회 (최대 90봉, 3페이지). 실패 시 빈 DataFrame."""
    try:
        import requests as _req
        from datetime import datetime as _dt
        token = _kis_token()
        if not token:
            return pd.DataFrame()
        cfg = dict(st.secrets.get("kis", {}))
        base = ("https://openapivts.koreainvestment.com:9443"
                if cfg.get("is_mock", True)
                else "https://openapi.koreainvestment.com:9443")
        hdrs = {
            "authorization": f"Bearer {token}",
            "appkey": cfg["app_key"],
            "appsecret": cfg["app_secret"],
            "tr_id": "FHKST03010200",
            "custtype": "P",
        }
        from datetime import timezone as _tz, timedelta as _td
        _kst = _tz(_td(hours=9))
        _now_kst = _dt.now(_kst)
        all_bars, qtime = [], _now_kst.strftime("%H%M%S")
        for _ in range(3):
            resp = _req.get(
                f"{base}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                headers=hdrs,
                params={"FID_ETC_CLS_CODE": "",
                        "FID_COND_MRKT_DIV_CODE": "J",
                        "FID_INPUT_ISCD": krx_code,
                        "FID_INPUT_HOUR_1": qtime,
                        "FID_PW_DATA_INCU_YN": "Y"},
                timeout=10)
            rows = resp.json().get("output2") or []
            if not rows:
                break
            all_bars.extend(rows)
            last_t = rows[-1].get("STCK_CNTG_HOUR", "")
            if not last_t or last_t == qtime:
                break
            qtime = last_t
        if not all_bars:
            return pd.DataFrame()
        today = _now_kst.strftime("%Y%m%d")
        df = pd.DataFrame(all_bars)
        date_col = "STCK_BSOP_DATE" if "STCK_BSOP_DATE" in df.columns else None
        df["_dt"] = pd.to_datetime(
            (df[date_col] if date_col else today) + df["STCK_CNTG_HOUR"],
            format="%Y%m%d%H%M%S")
        df = (df.set_index("_dt")
                .rename(columns={"STCK_OPRC": "Open", "STCK_HGPR": "High",
                                 "STCK_LWPR": "Low",  "STCK_PRPR": "Close",
                                 "CNTG_VOL":  "Volume"})
                .sort_index())
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def fetch_intraday(ticker, interval):
    """분봉 OHLCV (5m/15m/30m/60m). TTL=60s → 새로고침 시 최신 분봉 반영.
    반환: (DataFrame, error_str | None)
    """
    errors = []
    _kor = ticker.endswith(('.KS', '.KQ'))

    df_hist = pd.DataFrame()
    try:
        _period = {"5m": "5d", "15m": "7d", "30m": "14d", "60m": "30d"}.get(interval, "60d")
        raw = yf.download(ticker, period=_period, interval=interval, progress=False)
        df_hist = _normalize_yf_ohlcv(raw)
        if not df_hist.empty and _kor:
            try:
                _idx = pd.to_datetime(df_hist.index)
                if _idx.tz is None:
                    _idx = _idx.tz_localize('UTC').tz_convert('Asia/Seoul').tz_localize(None)
                else:
                    _idx = _idx.tz_convert('Asia/Seoul').tz_localize(None)
                df_hist.index = _idx
            except Exception:
                pass
        elif df_hist.empty:
            errors.append(f"yfinance: 빈 결과 (rows={len(raw) if not raw.empty else 0})")
    except Exception as e:
        errors.append(f"yfinance: {type(e).__name__}: {e}")

    # ── KIS 실시간 당일 분봉으로 최신 캔들 보완 (한국 종목 + KIS 설정 시)
    if _kor and not df_hist.empty:
        _krx = ticker.split('.')[0]
        if _krx and _krx[0].isdigit():
            _kis_1m = _fetch_kis_today(_krx)
            if not _kis_1m.empty:
                _rule = {"5m": "5min", "15m": "15min",
                         "30m": "30min", "60m": "60min"}.get(interval, "15min")
                _kis_r = (_kis_1m
                          .resample(_rule, closed='left', label='left')
                          .agg(Open=('Open', 'first'), High=('High', 'max'),
                               Low=('Low', 'min'),   Close=('Close', 'last'),
                               Volume=('Volume', 'sum'))
                          .dropna(subset=['Close']))
                df_hist = (pd.concat([df_hist, _kis_r])
                           .sort_index()
                           .loc[lambda x: ~x.index.duplicated(keep='last')])

    if not df_hist.empty:
        cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df_hist.columns]
        err_str = " | ".join(errors) if errors else None
        return df_hist[cols].copy(), err_str

    return pd.DataFrame(), " | ".join(errors)


@st.cache_data(ttl=60)
def fetch_intraday_batch(tickers_tuple, interval):
    """분봉 Close 일괄 조회 (스캐너용). 각 ticker 순차 fetch 후 DataFrame으로 합산."""
    tickers = list(tickers_tuple)
    if not tickers:
        return pd.DataFrame()
    frames = {}
    for ticker in tickers:
        try:
            df, _ = fetch_intraday(ticker, interval)
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

    # 동적+BB 확정 ★ / 밴드+BB 확정 ● — 시그널 없어도 레전드 항목은 항상 표시
    for _idx, _color, _outline, _sym, _sz, _label in [
        (dyn_buy_idx,  '#4BFFB3', 'rgba(75,255,179,0.4)',  'star',        10, "★ 동적+BB 매수"),
        (dyn_sell_idx, '#FF4B6E', 'rgba(255,75,110,0.4)',  'star',        10, "★ 동적+BB 매도"),
        (band_buy_idx, '#4BFFB3', '#4BFFB3',               'circle-open', 12, "● 밴드+BB 매수"),
        (band_sell_idx,'#FF4B6E', '#FF4B6E',               'circle-open', 12, "● 밴드+BB 매도"),
    ]:
        _x = _idx if len(_idx) > 0 else []
        _y = close[_idx] if len(_idx) > 0 else []
        fig.add_trace(go.Scatter(x=_x, y=_y, mode='markers',
            marker=dict(symbol=_sym, color=_color, size=_sz,
                        line=dict(color=_outline, width=1 if _sym == 'star' else 2.5)),
            name=_label), row=1, col=1)

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
        name="동적 상단 (90th)", line=dict(color="#FFD700", width=1, dash='dash'),
        showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=disp, y=dyn_lower[disp],
        name="동적 하단 (10th)", line=dict(color="#4BFFB3", width=1, dash='dash'),
        showlegend=False), row=2, col=1)
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
        height=900,
        title=dict(text=f"<b>{name}</b>", font=dict(size=14, color="#EDEDED"), x=0,
                   y=0.99, yanchor="top"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)", traceorder="normal"),
        **_base_layout(margin=dict(l=10, r=10, t=150, b=10)),
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
    # 분봉 모드: 주말 + 야간 갭 숨김 (shared_xaxes=False 환경에서 row별 명시 적용)
    if intraday_session is not None:
        close_h, open_h = intraday_session
        _rb = [
            dict(bounds=["sat", "mon"]),
            dict(bounds=[close_h, open_h], pattern="hour"),
        ]
        for _r in [1, 2, 3]:
            fig.update_xaxes(rangebreaks=_rb, row=_r, col=1)
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
    if dyn_buy:
        parts.append(_badge("★ 동적+BB 매수", "#4BFFB3", "#0a2b1e", "rgba(75,255,179,0.3)"))
    if dyn_buy_flag and not dyn_buy:
        parts.append(_badge("★ 매수 플래그", "#7AAFD4", "#0a1520", "rgba(120,175,212,0.2)"))
    if dyn_holding:
        parts.append(_badge("★ 보유 중", "#C8C850", "#1c1c08", "rgba(200,200,80,0.3)"))
    if dyn_sell:
        parts.append(_badge("★ 동적+BB 매도", "#FF4B6E", "#2d0d1a", "rgba(255,75,110,0.25)"))
    if dyn_sell_flag and not dyn_sell:
        parts.append(_badge("★ 매도 플래그", "#D47A9F", "#200a14", "rgba(212,120,160,0.2)"))
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
            <td style="padding:2px 14px;font-size:13px;color:#EDEDED;font-weight:500;white-space:nowrap;">{star}{row['name']}</td>
            <td style="padding:2px 14px;font-size:13px;color:#EDEDED;text-align:right;font-variant-numeric:tabular-nums;">{close_str}</td>
            <td style="padding:2px 14px;font-size:13px;color:{pct_color};text-align:right;font-variant-numeric:tabular-nums;">{pct_str}</td>
            <td style="padding:2px 14px;font-size:13px;color:{rsi_color};text-align:right;font-variant-numeric:tabular-nums;">{rsi_str}</td>
            <td style="padding:2px 14px;">{badges}</td>
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
    "S&P 500": "^GSPC", "나스닥 200": "^NDX",
}


@st.cache_data(ttl=86400)
def get_full_ticker_list(market):
    """전체 종목 코드 조회.
    한국: pykrx(1순위) → KRX KIND 스크래핑(2순위) → fallback 바스켓
    미국: Wikipedia(1순위, flavor 없이 html.parser) → fallback 내장 전체 리스트
    """
    import io, warnings
    warnings.filterwarnings("ignore")

    # ── 한국 시장 ──────────────────────────────────────────────
    if market in ("코스피", "코스닥"):
        suffix  = ".KS" if market == "코스피" else ".KQ"
        krx_mkt = "KOSPI" if market == "코스피" else "KOSDAQ"

        # 1순위: pykrx — 가장 신뢰성 높음 (이미 의존성으로 설치됨)
        if PYKRX_AVAILABLE:
            try:
                today = datetime.now().strftime("%Y%m%d")
                raw = pykrx_stock.get_market_ticker_list(today, market=krx_mkt)
                if raw is not None and len(raw) > 50:
                    return [f"{t}{suffix}" for t in raw]
            except Exception:
                pass

        # 2순위: KRX KIND 스크래핑
        try:
            import requests, re
            mkt_type = "stockMkt" if market == "코스피" else "kosdaqMkt"
            url = "http://kind.krx.co.kr/corpgeneral/corpList.do"
            params  = {"method": "download", "searchType": "13", "marketType": mkt_type}
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://kind.krx.co.kr/"}
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            df_krx = pd.read_html(io.BytesIO(resp.content), encoding="euc-kr")[0]
            codes = [str(int(c)).zfill(6) for c in df_krx["종목코드"]
                     if re.match(r"^\d+$", str(c))]
            tickers = [f"{c}{suffix}" for c in codes if len(c) == 6]
            if len(tickers) > 50:
                return tickers
        except Exception:
            pass

        return None  # fallback 바스켓은 get_market_internals에서 처리

    # ── 미국 시장 ──────────────────────────────────────────────
    if market == "S&P 500":
        try:
            import requests
            r = requests.get(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                headers=_WIKI_HEADERS, verify=False, timeout=20)
            # flavor 지정 없음 → html.parser(기본) 사용, lxml 불필요
            tables = pd.read_html(io.StringIO(r.text))
            tickers = (tables[0]["Symbol"]
                       .str.replace(".", "-", regex=False)
                       .dropna().tolist())
            if len(tickers) > 400:
                return tickers
        except Exception:
            pass
        return _SP500_BASKET  # ~200종 내장 fallback

    if market == "나스닥 200":
        tickers = []
        try:
            import requests
            r = requests.get(
                "https://en.wikipedia.org/wiki/Nasdaq-100",
                headers=_WIKI_HEADERS, verify=False, timeout=20)
            tables = pd.read_html(io.StringIO(r.text))
            for t in tables:
                for col in ["Ticker", "Symbol"]:
                    if col in t.columns and len(t) > 90:
                        tickers = t[col].dropna().tolist()
                        break
                if tickers:
                    break
        except Exception:
            pass
        # _NDX_BASKET으로 200종 보충
        existing = set(tickers)
        for t in _NDX_BASKET:
            if t not in existing:
                tickers.append(t)
                existing.add(t)
            if len(tickers) >= 200:
                break
        return tickers[:200] if tickers else _NDX_BASKET

    return None


@st.cache_data(ttl=3600)
def get_market_internals(market, lookback_days=60):
    try:
        full_tickers  = get_full_ticker_list(market)
        _fallback_map = {
            "코스피":   _KOSPI_BASKET,
            "코스닥":   _KOSDAQ_BASKET,
            "S&P 500":  _SP500_BASKET,
            "나스닥 200": _NDX_BASKET,
        }
        basket = full_tickers if full_tickers else _fallback_map.get(market)
        if basket is None:
            return None, f"{market} 종목 리스트 조회 실패"

        # ── 바스켓 200종 제한 (성능 + 시총 상위 집중)
        _BASKET_LIMIT = 200
        if len(basket) > _BASKET_LIMIT:
            if market in ("코스피", "코스닥") and PYKRX_AVAILABLE:
                try:
                    krx_mkt = "KOSPI" if market == "코스피" else "KOSDAQ"
                    today_str = datetime.now().strftime("%Y%m%d")
                    cap_df = pykrx_stock.get_market_cap(today_str, market=krx_mkt)
                    suffix = ".KS" if market == "코스피" else ".KQ"
                    top_codes = cap_df.nlargest(_BASKET_LIMIT, '시가총액').index.tolist()
                    basket = [f"{c}{suffix}" for c in top_codes]
                except Exception:
                    basket = basket[:_BASKET_LIMIT]
            elif market == "S&P 500":
                basket_set = set(basket)
                ordered = [t for t in _SP500_BASKET if t in basket_set]
                remaining = [t for t in basket if t not in set(_SP500_BASKET)]
                basket = (ordered + remaining)[:_BASKET_LIMIT]
            else:
                basket = basket[:_BASKET_LIMIT]

        index_yf_code = _INDEX_CODE.get(market, "^KS11")
        use_hv20 = market in ("코스피", "코스닥")   # ^VKOSPI는 Yahoo에 없음 → 지수로 HV20 계산
        vix_code = None if use_hv20 else "^VIX"

        end_dt   = datetime.now()
        # 200일선(200td) + 52주 신고가(252td) 계산을 위해 충분한 히스토리 확보
        # (lookback_days + 252td) × 1.5 달력일 + 여유
        extra    = max(int((lookback_days + 252) * 1.5) + 30, lookback_days + 430)
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

        # ── VIX / VKOSPI (한국은 ^VKOSPI 없음 → 나중에 HV20으로 대체)
        vix_series = pd.Series(dtype=float)
        if vix_code:
            try:
                vix_df = _normalize_yf_ohlcv(
                    yf.download(vix_code, start=yf_start, end=yf_end,
                                progress=False, auto_adjust=True))
                if not vix_df.empty and 'Close' in vix_df.columns:
                    vix_series = vix_df['Close'].dropna()
            except Exception:
                pass
            if vix_series.empty:
                try:
                    _t = yf.Ticker(vix_code)
                    _h = _t.history(start=yf_start, end=yf_end, auto_adjust=True)
                    if not _h.empty and 'Close' in _h.columns:
                        _h.index = _strip_tz(_h.index)
                        vix_series = _h['Close'].dropna()
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

        # 유효 종목 필터 (전체 기간 기준 10% 이상 — 긴 lookback에서 신규 상장 종목 포함)
        valid_cols = closes_full.columns[closes_full.notna().mean() >= 0.10]
        if len(valid_cols) < 3:
            return None, "유효 바스켓 종목 부족 (< 3개)"
        closes_full = closes_full[valid_cols].dropna(how='all')

        # ── 100일선 / 20일선 상위 비율 (전체 데이터로 계산)
        total_valid    = closes_full.notna()
        ma100          = closes_full.rolling(100, min_periods=50).mean()
        ma20           = closes_full.rolling(20,  min_periods=10).mean()
        above_100      = (closes_full > ma100)
        above_20       = (closes_full > ma20)
        pct_above_100  = (above_100.sum(axis=1) / total_valid.sum(axis=1) * 100).round(1)
        pct_above_20   = (above_20.sum(axis=1)  / total_valid.sum(axis=1) * 100).round(1)

        # ── 52주 신고가 비율: NH / 전체_유효_종목 × 100
        # min_periods=252: 만 1년 미만 데이터 종목 제외 → 정확한 52주 고저가 사용
        roll_high_252  = closes_full.rolling(252, min_periods=252).max()
        roll_low_252   = closes_full.rolling(252, min_periods=252).min()
        # 분모: 52주 히스토리가 있고 오늘 종가도 유효한 종목 수
        valid_for_nh   = roll_high_252.notna() & closes_full.notna()
        nh_count       = (closes_full >= roll_high_252).sum(axis=1)
        nh_total       = valid_for_nh.sum(axis=1).replace(0, float('nan'))
        nh_ratio       = (nh_count / nh_total * 100).round(1)  # 전체 대비 신고가 비율

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

        # 균일가중 지수: 첫날 유효한 종목만 사용해 일관된 기준점 보장
        start_valid  = closes_df.iloc[0].notna()
        ew_cols      = closes_df.loc[:, start_valid]
        if ew_cols.empty:
            ew_cols = closes_df
        first_prices = ew_cols.iloc[0]
        ew_index     = ew_cols.div(first_prices).mul(100).mean(axis=1)

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
        net_adv  = (advancing - declining).astype(float)
        adl      = net_adv.cumsum()
        adl_ma10 = adl.rolling(10, min_periods=3).mean()

        # ── 한국 시장: ^VKOSPI 없음 → 지수 20일 역사적 변동성으로 대체
        if use_hv20 and vix_series.empty:
            _ret  = cap_close.pct_change()
            _hv20 = (_ret.rolling(20, min_periods=10).std() * (252 ** 0.5) * 100).round(2)
            vix_series = _hv20.dropna()

        # 표시 구간 트림
        mcclellan      = mcclellan_full.reindex(closes_df.index).round(1)
        summation      = summation_full.reindex(closes_df.index).round(1)
        adv_ratio_ma20 = adv_ratio.rolling(20, min_periods=5).mean().round(1)
        pct_100_trim   = pct_above_100.reindex(closes_df.index)
        pct_20_trim    = pct_above_20.reindex(closes_df.index)
        nh_ratio_trim  = nh_ratio.reindex(closes_df.index)
        nh_ratio_ma10_trim = nh_ratio.rolling(10, min_periods=3).mean().round(1).reindex(closes_df.index)
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
            'ADL_MA10':    adl_ma10,
            '맥클렐란':    mcclellan,
            '서머레이션':  summation,
            'VIX':         vix_aligned,
            '100MA상위':   pct_100_trim,
            '20MA상위':    pct_20_trim,
            'NH비율':      nh_ratio_trim,
            'NH비율MA10':   nh_ratio_ma10_trim,
        }).dropna(subset=['균일가중'])

        return result, None
    except Exception as e:
        return None, traceback.format_exc()


# ============================================================
# 시장 강도 점수 시스템 — MA10 기울기 연속성 기반
# ============================================================

# 핵심★ 2배: ADL, 100MA상위 / 나머지 1배
_SCORE_WEIGHTS = {
    "시총가중":   1, "균일가중": 1,
    "ADL":       2, "서머레이션": 1,
    "HV20":      1, "상승비율":  1,
    "20MA상위":  1, "100MA상위": 2,
    "NH비율":    1,
}
# 가중치·연속일수(최대 2점) 기반 최대 점수 자동 계산
_SCORE_MAX = sum(w * 2 for w in _SCORE_WEIGHTS.values())  # 22


def _consec_slope(series, invert=False, already_smooth=False, deadband=0.0):
    """
    MA10 기울기 연속성으로 점수 반환.
      1일 연속 = ±0.5 (임시)
      2일 연속 = ±1   (플래그)
      3일+ 연속 = ±2  (확정)
    invert=True: 하락이 좋음 (HV20/VIX)
    already_smooth=True: 이미 이동평균된 시리즈면 MA10 재계산 없이 직접 사용
    deadband: 이 값 이하의 절대 변화는 횡보로 처리 (노이즈 제거)
    Returns (score, label, n_consecutive, effective_direction)
    """
    if series is None:
        return 0, "데이터 없음", 0, 0
    valid = series.dropna()
    if len(valid) < 4:
        return 0, "데이터 부족", 0, 0

    smoothed = valid if already_smooth else valid.rolling(10, min_periods=3).mean().dropna()
    if len(smoothed) < 2:
        return 0, "데이터 부족", 0, 0

    # 최근 4값 → 최대 3개 기울기 부호 추출
    tail = smoothed.iloc[-4:] if len(smoothed) >= 4 else smoothed
    signs = []
    for i in range(1, len(tail)):
        diff = float(tail.iloc[i]) - float(tail.iloc[i - 1])
        signs.append(0 if abs(diff) <= deadband else (1 if diff > 0 else -1))

    if not signs:
        return 0, "데이터 부족", 0, 0

    latest = signs[-1]
    if latest == 0:
        return 0, "횡보", 0, 0

    consec = 1
    for i in range(len(signs) - 2, -1, -1):
        if signs[i] == latest:
            consec += 1
        else:
            break

    # 1일=0.5(임시), 2일=1(플래그), 3일+=2(확정)
    score = 2 if consec >= 3 else (1 if consec == 2 else 0.5)
    effective = latest if not invert else -latest
    score *= effective

    dir_kr = "상승" if effective > 0 else "하락"
    tag = "확정" if consec >= 3 else ("플래그" if consec == 2 else "임시")
    lbl = f"{dir_kr} {consec}일 ({tag})"
    return score, lbl, consec, effective


# 비율 지표 레벨 경고 임계값 (낮을수록 악화 / 높을수록 과열)
_RATIO_LEVELS = {
    "20MA상위":     {"xlow": 15, "low": 30, "high": 70, "xhigh": 85},
    "100MA상위":    {"xlow": 20, "low": 35, "high": 65, "xhigh": 80},
    "상승비율MA20": {"xlow": 30, "low": 40, "high": 60, "xhigh": 75},
    "NH비율":       {"xlow":  1, "low":  5, "high": 20, "xhigh": 35},
}


def _ratio_level_html(indicator_name, val):
    """비율 지표 레벨 보조 경고 HTML 반환. 정상 범위면 빈 문자열."""
    thr = _RATIO_LEVELS.get(indicator_name)
    if thr is None or val is None:
        return ""
    v = float(val)
    if v <= thr["xlow"]:
        tag, color = "극저 ⚠", "#FF4B6E"
    elif v <= thr["low"]:
        tag, color = "저", "#FF8C69"
    elif v >= thr["xhigh"]:
        tag, color = "과열 ⚠", "#C8C850"
    elif v >= thr["high"]:
        tag, color = "고", "#4BFFB3"
    else:
        return ""
    return f'<br><span style="color:{color};font-size:8px">{v:.0f}% ({tag})</span>'


def _slope_score_all(df_slice):
    """
    MA10 기울기 연속성 기반 9개 지표 점수 계산.
    df_slice: 해당 일자까지의 전체 데이터프레임 슬라이스
    반환: dict[지표명] = {"score": float, "raw": float, "label": str, "level_html": str}
    """
    results = {}

    def col(name):
        return df_slice[name] if name in df_slice.columns else None

    def last(name):
        try:
            v = df_slice[name].iloc[-1]
            return float(v) if pd.notna(v) else None
        except Exception:
            return None

    # ── 1. 시총가중
    cap_s, cap_lbl, _, cap_dir = _consec_slope(col('시총가중'))
    results["시총가중"] = {"score": cap_s, "raw": last('시총가중'), "label": cap_lbl}

    # ── 2. 균일가중
    eqw_s, eqw_lbl, _, _ = _consec_slope(col('균일가중'))

    # 확산비율 = 균일가중 / 시총가중 → MA10 기울기로 쏠림/확산 판단 (라벨만, 점수 오버라이드 없음)
    breadth_html = ""
    cap_vals = col('시총가중')
    eqw_vals = col('균일가중')
    if cap_vals is not None and eqw_vals is not None:
        ratio = eqw_vals / cap_vals.replace(0, float('nan'))
        _, _, _, br_dir = _consec_slope(ratio)
        if br_dir > 0:
            breadth_html = '<br><span style="color:#4BFFB3;font-size:8px">↗ 장세 확산</span>'
        elif br_dir < 0:
            breadth_html = '<br><span style="color:#FF8C69;font-size:8px">⚡ 쏠림</span>'

    results["균일가중"] = {"score": eqw_s, "raw": last('균일가중'), "label": eqw_lbl,
                          "level_html": breadth_html}

    # ── 3. ADL ★ — ADL_MA10 기울기 기반, 다이버전스 시 라벨 경고만 (점수 강제 오버라이드 제거)
    adl_series = col('ADL_MA10') if 'ADL_MA10' in df_slice.columns else col('ADL')
    adl_smooth = 'ADL_MA10' in df_slice.columns
    adl_s, adl_lbl, _, adl_dir = _consec_slope(adl_series, already_smooth=adl_smooth)
    if cap_dir > 0 and adl_dir < 0:
        adl_lbl += " ⚡지수↑ADL↓"
    results["ADL"] = {"score": adl_s, "raw": last('ADL'), "label": adl_lbl}

    # ── 4. 서머레이션 ★
    summ_s, summ_lbl, _, _ = _consec_slope(col('서머레이션'))
    results["서머레이션"] = {"score": summ_s, "raw": last('서머레이션'), "label": summ_lbl}

    # ── 5. HV20/VIX — 하락이 좋음 (invert=True)
    hv_s, hv_lbl, _, _ = _consec_slope(col('VIX'), invert=True)
    results["HV20"] = {"score": hv_s, "raw": last('VIX'), "label": hv_lbl}

    # ── 6. 상승비율 — raw 데이터에 MA10 적용 (available), deadband 0.3%로 노이즈 제거
    adv_src = col('상승비율') if col('상승비율') is not None else col('상승비율MA20')
    adv_already = col('상승비율') is None  # raw 없으면 MA20 그대로
    adv_raw = last('상승비율MA20')
    adv_s, adv_lbl, _, _ = _consec_slope(adv_src, already_smooth=adv_already, deadband=0.3)
    results["상승비율"] = {
        "score": adv_s, "raw": adv_raw, "label": adv_lbl,
        "level_html": _ratio_level_html("상승비율MA20", adv_raw),
    }

    # ── 7. 20MA상위 ★
    m20_raw = last('20MA상위')
    m20_s, m20_lbl, _, _ = _consec_slope(col('20MA상위'))
    results["20MA상위"] = {
        "score": m20_s, "raw": m20_raw, "label": m20_lbl,
        "level_html": _ratio_level_html("20MA상위", m20_raw),
    }

    # ── 8. 100MA상위 ★
    m100_raw = last('100MA상위')
    m100_s, m100_lbl, _, _ = _consec_slope(col('100MA상위'))
    results["100MA상위"] = {
        "score": m100_s, "raw": m100_raw, "label": m100_lbl,
        "level_html": _ratio_level_html("100MA상위", m100_raw),
    }

    # ── 9. NH비율 — 이미 계산된 NH비율MA10 사용
    nh_raw = last('NH비율')
    nh_series = col('NH비율MA10') if 'NH비율MA10' in df_slice.columns else col('NH비율')
    nh_smooth = 'NH비율MA10' in df_slice.columns
    nh_s, nh_lbl, _, _ = _consec_slope(nh_series, already_smooth=nh_smooth)
    results["NH비율"] = {
        "score": nh_s, "raw": nh_raw, "label": nh_lbl,
        "level_html": _ratio_level_html("NH비율", nh_raw),
    }

    return results


def compute_market_score(indicator_scores):
    """가중 합산 후 -100~+100 정규화"""
    total = 0
    for name, info in indicator_scores.items():
        w = _SCORE_WEIGHTS.get(name, 1)
        total += info["score"] * w
    return round(total / _SCORE_MAX * 100)


def compute_indicator_correlations(df):
    """각 지표와 시총가중 지수 간의 Pearson 상관계수. 선택 기간 df 기준."""
    if '시총가중' not in df.columns or df['시총가중'].dropna().shape[0] < 10:
        return {}
    cap = df['시총가중']
    col_map = {
        '균일가중':  '균일가중',
        'ADL':      'ADL_MA10' if 'ADL_MA10' in df.columns else 'ADL',
        '서머레이션': '서머레이션',
        'HV20':     'VIX',
        '상승비율':  '상승비율',
        '20MA상위':  '20MA상위',
        '100MA상위': '100MA상위',
        'NH비율':    'NH비율MA10' if 'NH비율MA10' in df.columns else 'NH비율',
    }
    result = {}
    for key, col in col_map.items():
        if col not in df.columns:
            continue
        try:
            s = df[col].dropna()
            c = cap.reindex(s.index).dropna()
            s = s.reindex(c.index)
            if len(s) >= 10:
                result[key] = round(float(s.corr(c)), 2)
        except Exception:
            pass
    return result


def compute_score_timeseries(market_df):
    """각 날짜별 시장 종합점수 시리즈 반환 (벡터화). 반환: pd.Series[int]"""

    def _vec_score(series, invert=False, already_smooth=False, deadband=0.0):
        if series is None or series.dropna().shape[0] < 4:
            return pd.Series(dtype=float)
        smoothed = series if already_smooth else series.rolling(10, min_periods=3).mean()
        diff = smoothed.diff()
        sign = pd.Series(0.0, index=diff.index)
        sign[diff > deadband] = 1.0
        sign[diff < -deadband] = -1.0
        sign[diff.isna()] = 0.0
        if invert:
            sign = -sign
        s1 = sign.shift(1).fillna(0)
        s2 = sign.shift(2).fillna(0)
        nonzero = sign != 0
        same2 = nonzero & (sign == s1)
        same3 = same2 & (sign == s2)
        sc = pd.Series(0.0, index=sign.index)
        sc[nonzero & ~same2] = 0.5 * sign[nonzero & ~same2]
        sc[same2 & ~same3]   = 1.0 * sign[same2 & ~same3]
        sc[same3]             = 2.0 * sign[same3]
        return sc

    df = market_df
    total = pd.Series(0.0, index=df.index)

    if '시총가중' in df.columns:
        total += _vec_score(df['시총가중']) * _SCORE_WEIGHTS['시총가중']
    if '균일가중' in df.columns:
        total += _vec_score(df['균일가중']) * _SCORE_WEIGHTS['균일가중']

    adl_s  = df['ADL_MA10'] if 'ADL_MA10' in df.columns else df.get('ADL')
    adl_sm = 'ADL_MA10' in df.columns
    if adl_s is not None:
        total += _vec_score(adl_s, already_smooth=adl_sm) * _SCORE_WEIGHTS['ADL']

    if '서머레이션' in df.columns:
        total += _vec_score(df['서머레이션']) * _SCORE_WEIGHTS['서머레이션']
    if 'VIX' in df.columns:
        total += _vec_score(df['VIX'], invert=True) * _SCORE_WEIGHTS['HV20']

    adv_s  = df['상승비율'] if '상승비율' in df.columns else df.get('상승비율MA20')
    adv_sm = '상승비율' not in df.columns
    if adv_s is not None:
        total += _vec_score(adv_s, already_smooth=adv_sm, deadband=0.3) * _SCORE_WEIGHTS['상승비율']

    if '20MA상위' in df.columns:
        total += _vec_score(df['20MA상위']) * _SCORE_WEIGHTS['20MA상위']
    if '100MA상위' in df.columns:
        total += _vec_score(df['100MA상위']) * _SCORE_WEIGHTS['100MA상위']

    nh_s  = df['NH비율MA10'] if 'NH비율MA10' in df.columns else df.get('NH비율')
    nh_sm = 'NH비율MA10' in df.columns
    if nh_s is not None:
        total += _vec_score(nh_s, already_smooth=nh_sm) * _SCORE_WEIGHTS['NH비율']

    return (total / _SCORE_MAX * 100).round().astype(int)


def compute_lead_lag_table(df, lags=(5, 10, 20, 40)):
    """
    각 지표의 지수 선행성 분석.
    corr(indicator[t], 지수[t+lag]) — 오늘 지표가 lag일 후 지수를 얼마나 예측하는가.
    반환: pd.DataFrame (MultiIndex rows=(기간, 선행일), columns=지표)
    """
    if '시총가중' not in df.columns or len(df) < 30:
        return pd.DataFrame()

    cap = df['시총가중']
    col_map = {
        '시총가중':  '시총가중',
        '균일가중':  '균일가중',
        'ADL':      'ADL_MA10' if 'ADL_MA10' in df.columns else 'ADL',
        '서머레이션': '서머레이션',
        'HV20':     'VIX',
        '상승비율':  '상승비율',
        '20MA상위':  '20MA상위',
        '100MA상위': '100MA상위',
        'NH비율':    'NH비율MA10' if 'NH비율MA10' in df.columns else 'NH비율',
    }
    periods = [
        ('1M',  21), ('3M',  63), ('6M', 126),
        ('1Y', 252), ('2Y', 504), ('3Y', 756), ('4Y', 1008),
    ]

    # 종합판단 점수 시계열 (전체 df 기준으로 한 번만 계산)
    score_full = compute_score_timeseries(df).dropna()
    cum_full   = score_full.cumsum()

    rows, index = [], []
    for period_label, n_days in periods:
        if len(df) < n_days + max(lags):
            continue
        df_p  = df.iloc[-n_days:]
        cap_p = df_p['시총가중']
        for lag in lags:
            cap_future = cap_p.shift(-lag)
            row = {}

            # 개별 지표
            for ind_key, col in col_map.items():
                if col not in df_p.columns:
                    row[ind_key] = float('nan')
                    continue
                combined = pd.concat(
                    [df_p[col].rename('ind'), cap_future.rename('cap')], axis=1
                ).dropna()
                row[ind_key] = round(float(combined['ind'].corr(combined['cap'])), 2) \
                    if len(combined) >= 10 else float('nan')

            # 종합판단 점수
            score_p = score_full.reindex(df_p.index)
            combined = pd.concat(
                [score_p.rename('ind'), cap_future.rename('cap')], axis=1
            ).dropna()
            row['종합판단'] = round(float(combined['ind'].corr(combined['cap'])), 2) \
                if len(combined) >= 10 else float('nan')

            # 누적점수
            cum_p = cum_full.reindex(df_p.index)
            combined = pd.concat(
                [cum_p.rename('ind'), cap_future.rename('cap')], axis=1
            ).dropna()
            row['누적점수'] = round(float(combined['ind'].corr(combined['cap'])), 2) \
                if len(combined) >= 10 else float('nan')

            rows.append(row)
            index.append((period_label, f"{lag}일"))

    if not rows:
        return pd.DataFrame()
    mi = pd.MultiIndex.from_tuples(index, names=['기간', '선행일'])
    return pd.DataFrame(rows, index=mi)


def classify_phase(score):
    """점수 → (국면명, 색상코드)"""
    if score >= 65:    return "강한 강세장",   "#00FF7F"
    elif score >= 30:  return "강세 우위",     "#4BFFB3"
    elif score >= -30: return "중립 / 혼조",   "#C8C850"
    elif score >= -65: return "약세 우위",     "#FF8C69"
    else:              return "강한 약세장",   "#FF4B6E"


def get_phase_status(df, market_name):
    """
    오늘 점수로 국면 표시. 어제와 같은 국면이면 '유지', 다르면 '전환'.
    반환: (score_today, indicator_scores, phase_today, continuity_label)
    """
    n = len(df)
    sc_today = _slope_score_all(df)
    score_today = compute_market_score(sc_today)
    phase_today, _ = classify_phase(score_today)

    # 어제 점수 (참고용 연속성 라벨만)
    continuity = "첫날"
    if n >= 6:
        sc_prev = _slope_score_all(df.iloc[: n - 1])
        phase_prev, _ = classify_phase(compute_market_score(sc_prev))
        continuity = "유지 중" if phase_prev == phase_today else "전환"

    return score_today, sc_today, phase_today, continuity


def _build_interpretation(indicator_scores, total_score, market_name):
    """점수 기여도 높은 지표로 동적 해석 문구 생성"""
    is_korean = market_name in ("코스피", "코스닥")
    vix_lbl = "HV20" if is_korean else "VIX"

    display_names = {
        "시총가중": "시총가중 지수", "균일가중": "균일가중 지수",
        "ADL": "ADL 등락선", "서머레이션": "맥클렐란 서머레이션",
        "HV20": vix_lbl, "상승비율": "상승비율",
        "20MA상위": "20MA 상위비율", "100MA상위": "100MA 상위비율",
        "NH비율": "52주 신고가 비율",
    }

    # 기여도 = score × weight (부호 있음)
    contributions = []
    for name, info in indicator_scores.items():
        w = _SCORE_WEIGHTS.get(name, 1)
        contrib = info["score"] * w
        contributions.append((name, contrib, info["label"]))

    pos = sorted([x for x in contributions if x[1] > 0], key=lambda x: -x[1])
    neg = sorted([x for x in contributions if x[1] < 0], key=lambda x: x[1])

    pos_parts, neg_parts = [], []
    for name, contrib, lbl in pos[:2]:
        pos_parts.append(f"{display_names.get(name, name)} {lbl}")
    for name, contrib, lbl in neg[:2]:
        neg_parts.append(f"{display_names.get(name, name)} {lbl}")

    if not pos_parts and not neg_parts:
        return "지표들이 혼재하여 방향성 판단이 어렵습니다."

    lines = []
    if pos_parts:
        lines.append("▲ " + ", ".join(pos_parts))
    if neg_parts:
        lines.append("▼ " + ", ".join(neg_parts))

    if total_score >= 65:
        suffix = "전반적으로 강한 상승 구조입니다."
    elif total_score >= 30:
        suffix = "강세 우위이나 일부 지표 주의가 필요합니다." if neg_parts else "강세 흐름이 지속되고 있습니다."
    elif total_score >= -30:
        suffix = "방향성이 혼재된 중립 구간입니다."
    elif total_score >= -65:
        suffix = "약세 우위이며 리스크 관리가 필요합니다."
    else:
        suffix = "대부분 지표가 약세를 가리킵니다."

    return "  |  ".join(lines) + f"  →  {suffix}"


def render_market_score_ui(df, market_name):
    """시장 강도 점수 UI 렌더링 (기존 sentiment html 대체)"""
    if df is None or len(df) < 5:
        return

    score, indicator_scores, phase, status = get_phase_status(df, market_name)
    _, color = classify_phase(score)
    is_korean = market_name in ("코스피", "코스닥")
    vix_lbl = "HV20" if is_korean else "VIX"

    status_color = {"확정": "#4BFFB3", "플래그": "#C8C850", "임시": "#888"}
    status_icon  = {"확정": "✔", "플래그": "⚑", "임시": "○"}
    s_color = status_color.get(status, "#888")
    s_icon  = status_icon.get(status, "○")

    # 점수 바 (0~100 위치로 변환: -100→0, 0→50, +100→100)
    bar_pos = int((score + 100) / 2)
    bar_color = color

    interp = _build_interpretation(indicator_scores, score, market_name)

    # 종합점수 / 누적점수 ↔ 지수 상관계수
    _score_corr_html = ""
    try:
        _score_ts = compute_score_timeseries(df).dropna()
        _cap_ts   = df['시총가중'].dropna()
        _aligned  = _score_ts.reindex(_cap_ts.index).dropna()
        _cap_al   = _cap_ts.reindex(_aligned.index).dropna()
        _aligned  = _aligned.reindex(_cap_al.index)

        def _corr_span(label, series, cap, prefix=""):
            if len(series) < 10:
                return ""
            rv = round(float(series.corr(cap)), 2)
            ab = abs(rv)
            cc = ("#4BFFB3" if rv > 0 else "#FF4B6E") if ab >= 0.7 else \
                 ("#88D0B3" if rv > 0 else "#FF8C69") if ab >= 0.4 else "#555"
            return (
                f'<span style="font-size:10px;color:#555;margin-left:10px;">{label} </span>'
                f'<span style="font-size:10px;color:{cc};font-weight:600;">{prefix}r={rv:+.2f}</span>'
            )

        if len(_aligned) >= 10:
            _score_corr_html += _corr_span("점수↔지수", _aligned, _cap_al)

        # 누적점수 ↔ 지수
        _cum_ts  = _score_ts.cumsum().reindex(_cap_al.index).dropna()
        _cap_cum = _cap_al.reindex(_cum_ts.index).dropna()
        _cum_ts  = _cum_ts.reindex(_cap_cum.index)
        if len(_cum_ts) >= 10:
            _score_corr_html += _corr_span("누적↔지수", _cum_ts, _cap_cum)

    except Exception:
        pass

    # ── 헤더 카드
    header_html = f"""
<div style="background:#0f1117;border:1px solid {color}40;border-radius:10px;
            padding:14px 18px 12px;margin-bottom:10px;">
  <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
    <div style="font-size:28px;font-weight:800;color:{color};letter-spacing:-0.5px;
                font-variant-numeric:tabular-nums;">
      {score:+d}
    </div>
    <div>
      <div style="font-size:14px;font-weight:700;color:{color};">{phase}</div>
      <div style="font-size:11px;color:{s_color};margin-top:1px;">
        {s_icon} {status} 국면&nbsp;{_score_corr_html}
      </div>
    </div>
    <div style="flex:1;min-width:160px;">
      <div style="position:relative;background:rgba(255,255,255,0.06);
                  border-radius:4px;height:8px;overflow:visible;">
        <div style="position:absolute;left:{bar_pos}%;top:50%;transform:translate(-50%,-50%);
                    width:12px;height:12px;background:{bar_color};border-radius:50%;
                    box-shadow:0 0 6px {bar_color}88;"></div>
        <div style="position:absolute;left:50%;top:-4px;width:1px;height:16px;
                    background:rgba(255,255,255,0.2);"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:9px;
                  color:#444;margin-top:4px;">
        <span>약세 -100</span><span>│ 중립 0 │</span><span>+100 강세</span>
      </div>
    </div>
  </div>
  <div style="font-size:11px;color:#888;margin-top:10px;line-height:1.6;
              border-top:1px solid rgba(255,255,255,0.05);padding-top:8px;">
    {interp}
  </div>
</div>
"""

    # ── 지표별 점수 행
    correlations = compute_indicator_correlations(df)
    score_rows = []
    label_map = {
        "시총가중": "시총가중", "균일가중": "균일가중",
        "ADL": "ADL ★", "서머레이션": "서머레이션",
        "HV20": f"{vix_lbl}", "상승비율": "상승비율",
        "20MA상위": "20MA상위", "100MA상위": "100MA상위 ★",
        "NH비율": "NH비율",
    }
    # 점수 -2~+2 (0.5 단계 포함) → 색상·표시값·바 너비
    score_colors = {
        2: "#00FF7F", 1: "#4BFFB3", 0.5: "#88FFD0",
        0: "#888",
        -0.5: "#FFBBA0", -1: "#FF8C69", -2: "#FF4B6E",
    }
    # 각 점수를 -100~+100 정수로 표시 (×50)
    score_display = {2: 100, 1: 50, 0.5: 25, 0: 0, -0.5: -25, -1: -50, -2: -100}
    bar_widths    = {2: 100, 1: 50, 0.5: 25, 0: 0, -0.5: 25,  -1: 50,  -2: 100}

    for name, info in indicator_scores.items():
        s          = info["score"]
        lbl        = info["label"]
        level_html = info.get("level_html", "")
        c          = score_colors.get(s, "#888")
        disp       = score_display.get(s, 0)
        bw         = bar_widths.get(s, 0)
        is_pos     = s > 0
        bar_html = (
            f'<div style="width:{bw}%;height:100%;background:{c};border-radius:2px;'
            f'{"margin-left:auto;" if not is_pos else ""}"></div>'
        ) if s != 0 else ""
        disp_str = f"+{disp}" if disp > 0 else str(disp)

        # 상관계수 컬럼 (시총가중 자신은 기준이므로 생략)
        rv = correlations.get(name)
        if rv is not None:
            _abs = abs(rv)
            if _abs >= 0.7:
                _cc = "#4BFFB3" if rv > 0 else "#FF4B6E"
            elif _abs >= 0.4:
                _cc = "#88D0B3" if rv > 0 else "#FF8C69"
            else:
                _cc = "#555"
            corr_html = (
                f'<div style="width:52px;font-size:9px;color:{_cc};'
                f'text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums;">'
                f'r={rv:+.2f}</div>'
            )
        else:
            corr_html = '<div style="width:52px;flex-shrink:0;"></div>'

        score_rows.append(
            f'<div style="display:flex;align-items:center;gap:8px;padding:3px 0;'
            f'border-bottom:1px solid rgba(255,255,255,0.04);">'
            f'<div style="width:90px;font-size:10px;color:#888;flex-shrink:0;">'
            f'{label_map.get(name, name)}</div>'
            f'<div style="width:40px;font-size:11px;font-weight:700;color:{c};'
            f'text-align:right;flex-shrink:0;">{disp_str}</div>'
            f'<div style="flex:1;display:flex;align-items:center;">'
            f'<div style="width:50%;height:6px;background:rgba(255,75,110,0.08);'
            f'border-radius:2px 0 0 2px;overflow:hidden;">'
            f'{"" if is_pos or s==0 else bar_html}</div>'
            f'<div style="width:50%;height:6px;background:rgba(75,255,179,0.08);'
            f'border-radius:0 2px 2px 0;overflow:hidden;">'
            f'{"" if not is_pos or s==0 else bar_html}</div>'
            f'</div>'
            f'{corr_html}'
            f'<div style="width:100px;font-size:9px;color:#555;text-align:right;'
            f'flex-shrink:0;line-height:1.4;">{lbl}{level_html}</div>'
            f'</div>'
        )

    detail_html = f"""
<div style="background:#0c0c0e;border:1px solid rgba(255,255,255,0.06);
            border-radius:8px;padding:10px 14px;margin-bottom:10px;">
  <div style="font-size:10px;color:#555;margin-bottom:6px;display:flex;justify-content:space-between;">
    <span>지표별 점수 (-100 ~ +100) &nbsp;★ = 가중치 2배 핵심 지표</span>
    <span style="color:#444;">r = 지수와 상관계수 (선택 기간)</span>
  </div>
  {"".join(score_rows)}
</div>
"""

    import streamlit as st
    st.markdown(header_html + detail_html, unsafe_allow_html=True)


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
        ("서머레이션", float(latest['서머레이션']) > 0,
         f"{float(latest['서머레이션']):+.0f}"),
        ("VIX", _val_bull('VIX', 25, invert=True),
         f"{float(latest['VIX']):.1f}" if pd.notna(latest['VIX']) else "N/A"),
        ("상승비율", _val_bull('상승비율MA20', 50),
         f"{float(latest['상승비율MA20']):.0f}%" if pd.notna(latest['상승비율MA20']) else "N/A"),
        ("20MA상위", _val_bull('20MA상위', 50),
         f"{float(latest['20MA상위']):.0f}%" if pd.notna(latest.get('20MA상위')) else "N/A"),
        ("100MA상위", _val_bull('100MA상위', 50),
         f"{float(latest['100MA상위']):.0f}%" if pd.notna(latest['100MA상위']) else "N/A"),
        ("52주신고가", _val_bull('NH비율', 20),
         f"{float(latest['NH비율']):.0f}%" if pd.notna(latest.get('NH비율')) else "N/A"),
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
    vix_lbl = "변동성(HV20)" if market_name in ("코스피", "코스닥") else "VIX"
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


def make_score_timeseries_chart(market_df, market_name):
    """시장 종합점수 시계열 차트 (전폭).
    y  = 종합점수 (-100~+100)
    y2 = 시총가중 지수 오버레이
    y3 = 누적점수 (ADL 방식) 오버레이
    go.Figure() 직접 사용으로 3축 충돌 방지.
    """
    score_s = compute_score_timeseries(market_df).dropna()
    if len(score_s) < 5:
        return None

    dates  = score_s.index.tolist()
    scores = score_s.tolist()

    def _phase_color(s):
        if s >= 65:   return "#00FF7F"
        if s >= 30:   return "#4BFFB3"
        if s >= -30:  return "#C8C850"
        if s >= -65:  return "#FF8C69"
        return "#FF4B6E"

    fig = go.Figure()

    # 국면 배경 밴드
    for y0, y1, c in [
        ( 65,  100, "#00FF7F"), ( 30,  65, "#4BFFB3"),
        (-30,   30, "#C8C850"), (-65, -30, "#FF8C69"), (-100, -65, "#FF4B6E"),
    ]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, opacity=0.05,
                      layer="below", line_width=0)

    # 경계·0선
    for y in [65, 30, -30, -65]:
        fig.add_hline(y=y, line=dict(color="rgba(255,255,255,0.08)", dash="dot", width=1))
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.2)", width=1))

    # 양수/음수 fill
    fig.add_trace(go.Scatter(
        x=dates, y=[max(0, s) for s in scores],
        mode='lines', line=dict(width=0),
        fill='tozeroy', fillcolor='rgba(75,255,179,0.10)',
        showlegend=False, hoverinfo='skip',
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=[min(0, s) for s in scores],
        mode='lines', line=dict(width=0),
        fill='tozeroy', fillcolor='rgba(255,75,110,0.10)',
        showlegend=False, hoverinfo='skip',
    ))

    # 점수 라인 — 국면별 색상
    for i in range(len(dates) - 1):
        fig.add_trace(go.Scatter(
            x=[dates[i], dates[i+1]], y=[scores[i], scores[i+1]],
            mode='lines', line=dict(color=_phase_color(scores[i]), width=2),
            showlegend=False, hoverinfo='skip',
        ))

    # hover용 투명 마커
    fig.add_trace(go.Scatter(
        x=dates, y=scores,
        mode='markers', marker=dict(size=6, opacity=0),
        name="점수",
        hovertemplate="<b>%{x|%Y-%m-%d}</b>  점수: %{y:+d}<extra></extra>",
    ))

    # 시총가중 지수 오버레이 (y2)
    yaxis2_cfg = dict(overlaying='y', side='right',
                      showgrid=False, showticklabels=False, showline=False)
    idx = market_df['시총가중'].dropna()
    if not idx.empty:
        fig.add_trace(go.Scatter(
            x=idx.index.tolist(), y=idx.tolist(),
            line=dict(color="rgba(255,255,255,0.22)", width=1.1),
            showlegend=False, hoverinfo='skip', yaxis='y2',
        ))
        _i_min = float(idx.min()); _i_max = float(idx.max())
        _i_pad = max((_i_max - _i_min) * 0.12, 1.0)
        yaxis2_cfg['range'] = [_i_min - _i_pad, _i_max + _i_pad]

    # 누적 점수 오버레이 (y3, 보라색 점선)
    cum_s = score_s.cumsum()
    _cs_min = float(cum_s.min()); _cs_max = float(cum_s.max())
    _cs_pad = max((_cs_max - _cs_min) * 0.12, 1.0)
    fig.add_trace(go.Scatter(
        x=cum_s.index.tolist(), y=cum_s.tolist(),
        line=dict(color="rgba(120,126,231,0.55)", width=1.3, dash='dot'),
        showlegend=False, hoverinfo='skip', yaxis='y3',
    ))

    # 기울기 누적 오버레이 (y1 기준 정규화, 주황 점선)
    diff_cum_s = score_s.diff().cumsum().dropna()
    if not diff_cum_s.empty:
        _dc_lo, _dc_hi = float(diff_cum_s.min()), float(diff_cum_s.max())
        if _dc_hi != _dc_lo:
            diff_cum_norm = (diff_cum_s - _dc_lo) / (_dc_hi - _dc_lo) * 200 - 100
        else:
            diff_cum_norm = diff_cum_s * 0
        fig.add_trace(go.Scatter(
            x=diff_cum_norm.index.tolist(), y=diff_cum_norm.tolist(),
            line=dict(color='rgba(255,165,0,0.55)', width=1.1, dash='dot'),
            showlegend=False, hoverinfo='skip',
        ))

    # 우측 국면 라벨
    for y, c, lbl in [(82,"#00FF7F","강한강세"),(47,"#4BFFB3","강세우위"),
                       (0,"#C8C850","중립"),(-47,"#FF8C69","약세우위"),(-82,"#FF4B6E","강한약세")]:
        fig.add_annotation(x=1.005, y=y, xref='paper', yref='y',
                           text=lbl, showarrow=False, xanchor='left',
                           font=dict(size=8, color=c))

    # r 어노테이션
    idx_s = market_df['시총가중'].dropna()
    def _r_sc(a, b):
        al = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna()
        if len(al) < 10: return float('nan')
        return al['a'].corr(al['b'])
    _r1 = _r_sc(score_s, idx_s)
    _r2 = _r_sc(score_s.cumsum(), idx_s)
    _r3 = _r_sc(score_s.diff().cumsum().dropna(), idx_s)
    def _rfmt_sc(r): return f'{r:+.2f}' if not pd.isna(r) else '─'
    fig.add_annotation(
        x=0.01, y=0.97, xref='paper', yref='paper',
        xanchor='left', yanchor='top',
        text=f"지표 {_rfmt_sc(_r1)}  누적 {_rfmt_sc(_r2)}  기울기↑누적 {_rfmt_sc(_r3)}",
        showarrow=False,
        font=dict(size=8, color='#666'),
        bgcolor='rgba(14,14,17,0.75)', borderpad=2,
    )

    fig.update_layout(
        height=220,
        title=dict(text=f"📈 {market_name} 시장 종합판단 추이",
                   font=dict(size=12, color="#9B9B9B"), x=0, y=0.97),
        yaxis=dict(range=[-110, 110], tickformat="+d",
                   tickvals=[-100, -65, -30, 0, 30, 65, 100],
                   gridcolor="rgba(255,255,255,0.04)", zeroline=False,
                   tickfont=dict(size=9)),
        yaxis2=yaxis2_cfg,
        yaxis3=dict(overlaying='y', side='right',
                    showgrid=False, showticklabels=False, showline=False,
                    range=[_cs_min - _cs_pad, _cs_max + _cs_pad]),
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
        margin=dict(l=45, r=70, t=30, b=25),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9B9B9B", size=10),
        hovermode="x unified",
        showlegend=False,
    )
    return fig


def make_market_chart(df, market_name):
    is_korean = market_name in ("코스피", "코스닥")
    vix_label = "역사적 변동성(HV20)" if is_korean else "VIX"
    has_vix   = df['VIX'].notna().any()
    has_200   = df['100MA상위'].notna().any()
    has_50    = '20MA상위' in df.columns and df['20MA상위'].notna().any()
    has_nh    = 'NH비율' in df.columns and df['NH비율'].notna().any()
    has_nh_ma = 'NH비율MA10' in df.columns and df['NH비율MA10'].notna().any()
    has_summ  = df['서머레이션'].notna().any()
    x0, x1   = df.index[0], df.index[-1]

    # 보조 Y축 범위: 시총가중 전체 데이터 기준으로 한 번만 계산
    # (update_yaxes를 _idx_overlay 내부에서 호출하면 이후 global update_yaxes에 덮어씌워짐)
    _idx_full = df['시총가중'].dropna()
    if not _idx_full.empty:
        _i_min = float(_idx_full.min())
        _i_max = float(_idx_full.max())
        _i_pad = max((_i_max - _i_min) * 0.12, 1.0)
        _idx_yr: list = [_i_min - _i_pad, _i_max + _i_pad]
    else:
        _idx_yr = [90, 110]

    # 지수(시총가중) 배경 오버레이 — 보조 Y축(오른쪽), 트레이스만 추가
    # 범위는 함수 밖에서 한 번에 설정 (global update_yaxes 이후에 적용해야 덮어씌워지지 않음)
    def _idx_overlay(fig, row, col):
        idx = df['시총가중'].dropna()
        if idx.empty:
            return
        fig.add_trace(go.Scatter(
            x=idx.index, y=idx,
            line=dict(color="rgba(255,255,255,0.22)", width=1.1),
            showlegend=False, hoverinfo='skip',
        ), row=row, col=col, secondary_y=True)

    def _hl(y, color, dash='dot', width=0.9):
        return go.Scatter(
            x=[x0, x1], y=[y, y], mode='lines',
            line=dict(color=color, width=width, dash=dash),
            showlegend=False, hoverinfo='skip',
        )

    def _cum_overlays(fig, row, col, main_s):
        s = main_s.dropna()
        if len(s) < 10:
            return
        idx_s = df['시총가중'].dropna()
        cum_s    = s.cumsum()
        diff_cum = s.diff().cumsum().dropna()

        def _norm(src):
            s_lo, s_hi = float(s.min()), float(s.max())
            lo, hi = float(src.min()), float(src.max())
            if hi == lo:
                return pd.Series([(s_lo + s_hi) / 2] * len(src), index=src.index)
            return (src - lo) / (hi - lo) * (s_hi - s_lo) + s_lo

        for vals, color, dash in [
            (cum_s.dropna(),  'rgba(120,126,231,0.65)', 'dash'),
            (diff_cum,        'rgba(255,165,0,0.65)',   'dot'),
        ]:
            nv = _norm(vals)
            fig.add_trace(go.Scatter(
                x=nv.index, y=nv,
                line=dict(color=color, width=1.0, dash=dash),
                showlegend=False, hoverinfo='skip',
            ), row=row, col=col)

        def _r(a, b):
            al = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna()
            if len(al) < 10:
                return float('nan')
            return al['a'].corr(al['b'])

        r1, r2, r3 = _r(s, idx_s), _r(cum_s, idx_s), _r(diff_cum, idx_s)

        def _rfmt(r):
            return f'{r:+.2f}' if not pd.isna(r) else '─'

        ann = f"지표 {_rfmt(r1)}  누적 {_rfmt(r2)}  기울기↑누적 {_rfmt(r3)}"
        # row_heights=[0.22,0.22,0.28,0.28], v_spacing=0.09, h_spacing=0.08
        # paper 좌표: 각 서브플롯 좌상단 근처
        _ytop  = {1: 0.99, 2: 0.74, 3: 0.49, 4: 0.20}
        _xleft = {1: 0.02, 2: 0.54}
        fig.add_annotation(
            x=_xleft[col], y=_ytop[row],
            xref='paper', yref='paper',
            xanchor='left', yanchor='top',
            text=ann, showarrow=False,
            font=dict(size=7.5, color='#666'),
            bgcolor='rgba(14,14,17,0.75)', borderpad=2,
        )

    _specs = [[{"secondary_y": True}, {"secondary_y": True}]] * 4
    fig = make_subplots(
        rows=4, cols=2,
        specs=_specs,
        row_heights=[0.22, 0.22, 0.28, 0.28],
        subplot_titles=[
            "시총가중 vs 균일가중 (기준=100)",
            "확산비율 (균일가중 ÷ 시총가중)  ↑확산 ↓쏠림",
            "ADL — 등락 누적선",
            "52주 신고가 비율 (% of 전체 유효 종목)",
            "맥클렐란 서머레이션 인덱스",
            f"{vix_label}  (↑높을수록 공포)",
            "상승비율 & MA20  (50 중심 루트 스트레치)",
            "이동평균선 상위 종목 비율 (20일 / 100일)",
        ],
        vertical_spacing=0.09,
        horizontal_spacing=0.08,
    )

    # ── Row 1 left: 시총가중 vs 균일가중
    fig.add_trace(go.Scatter(x=df.index, y=df['시총가중'],
        name="시총가중", line=dict(color="#00FF7F", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['균일가중'],
        name="균일가중", line=dict(color="#FFD700", width=1.5)), row=1, col=1)
    _cum_overlays(fig, 1, 1, df['균일가중'])

    # ── Row 1 right: 확산비율 (균일가중 ÷ 시총가중) + 지수 배경
    # 비율 상승 = 균일가중 우세 = 장세 확산, 하락 = 시총가중 우세 = 대형주 쏠림
    ratio = (df['균일가중'] / df['시총가중'].replace(0, float('nan'))).round(4)
    _idx_overlay(fig, 1, 2)
    fig.add_trace(go.Scatter(x=df.index, y=ratio,
        line=dict(color="#FFD700", width=1.5), showlegend=False), row=1, col=2)
    fig.add_trace(_hl(float(ratio.mean()), "rgba(255,255,255,0.12)", 'dot'), row=1, col=2)
    _cum_overlays(fig, 1, 2, ratio.dropna())

    # ── Row 2 left: ADL + MA20 + 지수 배경
    _idx_overlay(fig, 2, 1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ADL'],
        name="ADL", line=dict(color="rgba(120,126,231,0.35)", width=1.2),
        fill='tozeroy', fillcolor="rgba(120,126,231,0.06)",
        showlegend=False,
    ), row=2, col=1)
    if 'ADL_MA10' in df.columns and df['ADL_MA10'].notna().any():
        fig.add_trace(go.Scatter(
            x=df.index, y=df['ADL_MA10'],
            name="ADL MA10", line=dict(color="#787EE7", width=1.8, dash='dot'),
            showlegend=False,
        ), row=2, col=1)
    fig.add_trace(_hl(0, "rgba(255,255,255,0.15)", 'dot'), row=2, col=1)
    _cum_overlays(fig, 2, 1, df['ADL'].dropna())

    # ── Row 2 right: 52주 신고가 비율 + 지수 배경
    if has_nh:
        nh = df['NH비율'].dropna()
        _idx_overlay(fig, 2, 2)
        fig.add_trace(go.Scatter(
            x=nh.index, y=nh,
            line=dict(color="#DDA0DD", width=1.8),
            showlegend=False,
        ), row=2, col=2)
        # NH/total 기준: 30%=강세, 15%=중립, 5%=약세
        for lvl, c in [(30, "rgba(75,255,179,0.45)"),
                       (15, "rgba(255,255,255,0.12)"),
                       (5,  "rgba(255,75,110,0.45)")]:
            fig.add_trace(_hl(lvl, c), row=2, col=2)
        if has_nh_ma:
            nh_ma = df['NH비율MA10'].dropna()
            fig.add_trace(go.Scatter(
                x=nh_ma.index, y=nh_ma,
                name="NH MA10", line=dict(color="#E8B8FF", width=1.8, dash='dot'),
                showlegend=False,
            ), row=2, col=2)
        # Y 범위: MA20도 포함해서 최댓값 결정
        _nh_all = pd.concat([nh, df['NH비율MA10'].dropna()]) if has_nh_ma else nh
        nh_max = max(float(_nh_all.max()), 30) * 1.2 if not _nh_all.empty else 40
        fig.update_yaxes(range=[0, nh_max], row=2, col=2)
        _cum_overlays(fig, 2, 2, df['NH비율'].dropna())
    else:
        fig.add_annotation(
            text="52주 데이터 부족 (기간 늘리기)", x=0.5, y=0.5,
            xref="x4 domain", yref="y4 domain",
            showarrow=False, font=dict(color="#555", size=11),
        )

    # ── Row 3 left: 서머레이션 + 지수 배경
    # Bar 대신 Scatter fill 사용 → 한국 공휴일 gap 없이 깔끔하게 렌더링
    # 양수(강세 기간)=초록 영역, 음수(약세 기간)=빨간 영역
    if has_summ:
        summ = df['서머레이션']  # NaN 포함 (connectgaps=False로 gap 처리)
        _idx_overlay(fig, 3, 1)
        summ_pos = summ.where(summ >= 0, 0)
        summ_neg = summ.where(summ <= 0, 0)
        fig.add_trace(go.Scatter(
            x=summ.index, y=summ_pos,
            fill='tozeroy', fillcolor="rgba(75,255,179,0.20)",
            line=dict(color="rgba(75,255,179,0.55)", width=0.8),
            showlegend=False, connectgaps=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=summ.index, y=summ_neg,
            fill='tozeroy', fillcolor="rgba(255,75,110,0.20)",
            line=dict(color="rgba(255,75,110,0.55)", width=0.8),
            showlegend=False, connectgaps=False,
        ), row=3, col=1)
        fig.add_trace(_hl(0, "rgba(255,255,255,0.20)", 'solid', 1.0), row=3, col=1)
        _summ_valid = summ.dropna()
        summ_ref = max(abs(float(_summ_valid.max())), abs(float(_summ_valid.min())), 50) * 0.70
        for lvl, c in [(summ_ref, "rgba(255,75,110,0.40)"),
                       (-summ_ref, "rgba(75,255,179,0.40)")]:
            fig.add_trace(_hl(lvl, c, 'dot'), row=3, col=1)
        summ_bound = max(abs(float(_summ_valid.max())), abs(float(_summ_valid.min())), 50) * 1.25
        fig.update_yaxes(range=[-summ_bound, summ_bound], row=3, col=1)
        _cum_overlays(fig, 3, 1, df['서머레이션'].dropna())

    # ── Row 3 right: VIX / HV20 + 지수 배경
    if has_vix:
        vix = df['VIX'].dropna()
        _idx_overlay(fig, 3, 2)
        fig.add_trace(go.Scatter(
            x=vix.index, y=vix,
            line=dict(color="#FFB347", width=1.8),
            showlegend=False,
        ), row=3, col=2)
        # 동적 중심: 데이터 중앙값 기준, 고정 참조선 유지
        vix_med  = float(vix.median())
        vix_ref  = [15, 20, 25] if is_korean else [20, 25, 30]
        vix_clrs = ["rgba(75,255,179,0.45)", "rgba(255,255,255,0.10)", "rgba(255,75,110,0.45)"]
        half = max(abs(float(vix.max()) - vix_med),
                   abs(vix_med - float(vix.min())), 5) * 1.4
        fig.update_yaxes(range=[vix_med - half, vix_med + half], row=3, col=2)
        for lvl, c in zip(vix_ref, vix_clrs):
            fig.add_trace(_hl(lvl, c), row=3, col=2)
        _cum_overlays(fig, 3, 2, df['VIX'].dropna())
    else:
        fig.add_annotation(
            text=f"{vix_label} 데이터 없음", x=0.5, y=0.5,
            xref="x6 domain", yref="y6 domain",
            showarrow=False, font=dict(color="#555", size=11),
        )

    # ── Row 4 left: 상승비율 & MA20 — 50 중심 루트 스트레치
    # 공식: 50 + sign(x-50) × √|x-50| × 10  →  40→18, 50→50, 60→82 등
    def _stretch50(s):
        dev = s - 50
        _sign = dev.map(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
        return (50 + _sign * (dev.abs() ** 0.5) * 10).clip(0, 100)

    # 참조값(원본): 40, 50, 60 → 변환 후 위치 계산
    _ref_raw = [40, 50, 60]
    _ref_trn = [float(50 + (1 if r > 50 else -1 if r < 50 else 0) * ((abs(r - 50)) ** 0.5) * 10)
                for r in _ref_raw]  # ≈ [18.4, 50, 81.6]

    adv_s = _stretch50(df['상승비율'])
    _idx_overlay(fig, 4, 1)
    fig.add_trace(go.Scatter(
        x=df.index, y=adv_s,
        name="상승비율", line=dict(color="rgba(120,126,231,0.18)", width=1),
        customdata=df['상승비율'],
        hovertemplate="%{customdata:.1f}%<extra>상승비율</extra>",
    ), row=4, col=1)
    if df['상승비율MA20'].notna().any():
        ma20_s = _stretch50(df['상승비율MA20'])
        fig.add_trace(go.Scatter(
            x=df.index, y=ma20_s,
            name="MA20", line=dict(color="#787EE7", width=2),
            customdata=df['상승비율MA20'],
            hovertemplate="%{customdata:.1f}%<extra>MA20</extra>",
        ), row=4, col=1)
    for lvl_t, c in zip(_ref_trn,
                        ["rgba(255,75,110,0.45)",
                         "rgba(255,255,255,0.12)",
                         "rgba(75,255,179,0.45)"]):
        fig.add_trace(_hl(lvl_t, c), row=4, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)
    _cum_overlays(fig, 4, 1, df['상승비율'].dropna())

    # ── Row 4 right: 100MA 상위 + 20MA 상위 오버레이 + 편차 + 지수 배경
    if has_200:
        p100 = df['100MA상위'].dropna()
        _idx_overlay(fig, 4, 2)
        fig.add_trace(go.Scatter(
            x=p100.index, y=p100,
            name="100MA 상위", line=dict(color="#C8C850", width=1.8),
        ), row=4, col=2)
        if has_50:
            p20 = df['20MA상위'].dropna()
            fig.add_trace(go.Scatter(
                x=p20.index, y=p20,
                name="20MA 상위", line=dict(color="#87CEEB", width=1.5, dash='dot'),
            ), row=4, col=2)
        spread_20_100 = pd.Series(dtype=float)
        if has_50:
            spread_20_100 = (df['20MA상위'] - df['100MA상위']).dropna()
        _ma_all_vals = pd.concat(
            [p100] + ([p20] if has_50 else []) + ([spread_20_100] if not spread_20_100.empty else [])
        )
        center = 50.0
        half = max(abs(float(_ma_all_vals.max()) - center),
                   abs(center - float(_ma_all_vals.min())), 10) * 1.3
        fig.update_yaxes(range=[center - half, center + half], row=4, col=2)
        if not spread_20_100.empty:
            fig.add_trace(go.Scatter(
                x=spread_20_100.index, y=spread_20_100,
                name="20-100 편차", line=dict(color="rgba(255,165,0,0.7)", width=1.0),
                fill='tozeroy', fillcolor="rgba(255,165,0,0.07)",
            ), row=4, col=2)
            fig.add_trace(_hl(0, "rgba(255,165,0,0.25)", 'dot'), row=4, col=2)
        for lvl, c in [(70, "rgba(75,255,179,0.45)"),
                       (50, "rgba(255,255,255,0.12)"),
                       (30, "rgba(255,75,110,0.45)")]:
            fig.add_trace(_hl(lvl, c), row=4, col=2)
        _cum_overlays(fig, 4, 2, df['100MA상위'].dropna())

    fig.update_layout(
        height=1100,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        **_base_layout(),
    )
    fig.update_xaxes(**_axis_kw())
    fig.update_yaxes(**_axis_kw())
    # 보조 Y축: global update_yaxes 이후에 range를 덮어써야 초기화 방지
    # range를 여기서 마지막으로 설정해야 Plotly가 덮어쓰지 않음
    for _r in range(1, 5):
        for _c in range(1, 3):
            fig.update_yaxes(
                range=_idx_yr,
                showticklabels=False, showgrid=False,
                zeroline=False, showline=False,
                row=_r, col=_c, secondary_y=True,
            )
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
# 매크로 탭 — 데이터 패처 + 차트 빌더
# ============================================================

@st.cache_data(ttl=86400)
def _fred(series_id: str, years: int = 5) -> pd.Series:
    """FRED 공개 CSV (API 키 불필요). SSL 자체 서명 대응 + 타임아웃 처리."""
    import urllib.request, ssl, io as _io
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for verify in (True, False):
        try:
            ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
                content = resp.read().decode('utf-8')
            s = pd.read_csv(_io.StringIO(content), index_col=0, parse_dates=True, na_values='.')
            s = s.iloc[:, 0].astype(float).dropna()
            cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
            return s[s.index >= cutoff]
        except Exception:
            if verify:
                continue  # retry without SSL verify
            return pd.Series(dtype=float, name=series_id)
    return pd.Series(dtype=float, name=series_id)


@st.cache_data(ttl=86400)
def _yf_close(ticker: str, years: int = 5) -> pd.Series:
    try:
        start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime('%Y-%m-%d')
        raw = yf.download(ticker, start=start, progress=False)
        df = _normalize_yf_ohlcv(raw)
        return df['Close'].dropna() if 'Close' in df.columns else pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=3600)
def _foreign_cumnet(market_code: str, years: int = 5):
    """외국인 주식 누적 순매수 (pykrx, 억원). Returns (series, error_str)."""
    try:
        from pykrx import stock as _pk
        end_d   = pd.Timestamp.now().strftime('%Y%m%d')
        start_d = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime('%Y%m%d')
        df = _pk.get_market_trading_value_by_date(start_d, end_d, market_code)
        if df is None or df.empty:
            return pd.Series(dtype=float), '빈 데이터 반환 (KRX API 일시 불가)'
        # pykrx 버전에 따라 컬럼명이 다를 수 있음
        candidates = ['외국인합계', '외국인', 'FOREIGNER', 'Foreign']
        col = next((c for c in candidates if c in df.columns), None)
        if col is None:
            # 마지막 수치형 컬럼이 대체로 '외국인합계'
            num_cols = df.select_dtypes(include='number').columns.tolist()
            col = num_cols[-1] if num_cols else None
        if col is None:
            return pd.Series(dtype=float), f'외국인 컬럼 없음 (컬럼: {list(df.columns)})'
        s = df[col].astype(float)
        s.index = pd.to_datetime(s.index)
        return s.cumsum() / 1e8, None
    except Exception as e:
        return pd.Series(dtype=float), str(e)


def _zscore(s: pd.Series, window: int = 252) -> pd.Series:
    mu    = s.rolling(window, min_periods=max(30, window // 4)).mean()
    sigma = s.rolling(window, min_periods=max(30, window // 4)).std()
    return ((s - mu) / sigma.replace(0, float('nan'))).clip(-3, 3)


def _ml(title: str, height: int = 300, **kw) -> dict:
    """매크로 차트 공통 layout."""
    base = dict(
        title=dict(text=title, font=dict(size=12, color='#9B9B9B'), x=0, y=0.97),
        height=height,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#9B9B9B', size=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1,
                    font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=50, r=20, t=38, b=30),
        hovermode='x unified',
        xaxis=dict(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9)),
        yaxis=dict(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False),
    )
    base.update(kw)
    return base


def _hidden_yaxis(overlaying='y', side='right') -> dict:
    """숨겨진 오버레이 y축 (눈금 없음)."""
    return dict(overlaying=overlaying, side=side, showgrid=False,
                showticklabels=False, showline=False, zeroline=False)


def _add_spx_cum_overlays(fig, main_s: pd.Series, spx_s,
                           cum_yaxis='y2', spx_yaxis='y3',
                           cum_label='누적변화', row=None, col=None):
    """누적변화(주황 점선) + 지수%(노란 파선) 오버레이를 fig에 추가."""
    kw = {}  # subplot row/col 은 yaxis 명시 트레이스에선 무시됨 — layout으로 처리

    # ① 주요 지표 누적 변화 (시작일 대비)
    if main_s is not None and not main_s.empty and len(main_s) > 2:
        cum = (main_s - main_s.iloc[0]).dropna()
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum, name=cum_label,
            line=dict(color='rgba(255,140,100,0.65)', width=1.1, dash='dot'),
            showlegend=True, hoverinfo='skip', yaxis=cum_yaxis,
        ))

    # ② S&P 500 % 변화 (시작일 기준 정규화)
    if spx_s is not None and not spx_s.empty:
        t0 = main_s.index[0] if (main_s is not None and not main_s.empty) else spx_s.index[0]
        spx_t = spx_s[spx_s.index >= t0]
        if len(spx_t) > 2:
            spx_pct = ((spx_t / spx_t.iloc[0]) - 1) * 100
            fig.add_trace(go.Scatter(
                x=spx_pct.index, y=spx_pct, name='S&P500(%)',
                line=dict(color='rgba(200,200,80,0.45)', width=1.0, dash='dash'),
                showlegend=True, hoverinfo='skip', yaxis=spx_yaxis,
            ))


def _add_corr_annotation(fig, main_s: pd.Series, spx_s, label='vs S&P500'):
    """상관계수 어노테이션을 그래프 우상단에 추가."""
    if spx_s is None or spx_s.empty or main_s is None or main_s.empty:
        return
    try:
        aligned = pd.concat([main_s.rename('ind'), spx_s.rename('spx')], axis=1).dropna()
        if len(aligned) < 20:
            return
        r = aligned['ind'].corr(aligned['spx'])
        if pd.isna(r):
            return
        color = '#4BFFB3' if r > 0.3 else '#FF4B6E' if r < -0.3 else '#AAAAAA'
        fig.add_annotation(
            x=1, y=1, xref='paper', yref='paper',
            xanchor='right', yanchor='top',
            text=f'r = {r:+.2f} ({label})',
            showarrow=False,
            font=dict(size=9, color=color),
            bgcolor='rgba(14,14,17,0.80)',
            bordercolor=color, borderwidth=1, borderpad=3,
        )
    except Exception:
        pass


def make_macro_credit_spread_chart(years: int = 5, spx_s=None):
    """① 크레딧 스프레드: HY OAS + IG OAS + 누적 + 지수"""
    hy = _fred('BAMLH0A0HYM2', years)
    ig = _fred('BAMLC0A0CM',   years)
    if hy.empty:
        return None
    fig = go.Figure()
    fig.add_hline(y=5, line=dict(color='rgba(255,75,110,0.3)', dash='dot', width=1))
    fig.add_trace(go.Scatter(x=hy.index, y=hy, name='HY 스프레드',
                             line=dict(color='#FF4B6E', width=1.5)))
    if not ig.empty:
        fig.add_trace(go.Scatter(x=ig.index, y=ig, name='IG 스프레드',
                                 line=dict(color='#4BFFB3', width=1.3), yaxis='y2'))
    _add_spx_cum_overlays(fig, hy, spx_s, cum_yaxis='y3', spx_yaxis='y4', cum_label='HY 누적변화')
    fig.update_layout(
        **_ml('① 크레딧 스프레드 (HY · IG OAS, %)'),
        yaxis2=dict(overlaying='y', side='right', showgrid=False, tickfont=dict(size=9), zeroline=False),
        yaxis3=_hidden_yaxis('y', 'right'),
        yaxis4=_hidden_yaxis('y', 'right'),
    )
    _add_corr_annotation(fig, hy, spx_s)
    return fig


def make_macro_credit_stress_chart(years: int = 5, spx_s=None):
    """② 신용 스트레스 지수: HY + NFCI + VIX z-score 합성"""
    hy   = _fred('BAMLH0A0HYM2', years + 1)
    nfci = _fred('NFCI',         years + 1)
    vix  = _yf_close('^VIX',     years + 1)
    parts = []
    if not hy.empty:   parts.append(_zscore(hy).rename('HY'))
    if not nfci.empty: parts.append(_zscore(nfci).rename('NFCI'))
    if not vix.empty:  parts.append(_zscore(vix).rename('VIX'))
    if not parts:
        return None
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    stress = pd.concat(parts, axis=1).mean(axis=1).dropna()
    stress = stress[stress.index >= cutoff]
    if stress.empty:
        return None
    # ADL식 누적 스트레스
    cum_stress = stress.cumsum()
    fig = go.Figure()
    fig.add_hline(y=0,  line=dict(color='rgba(255,255,255,0.2)', width=1))
    fig.add_hline(y=1,  line=dict(color='rgba(255,75,110,0.25)',  dash='dot', width=1))
    fig.add_hline(y=-1, line=dict(color='rgba(75,255,179,0.25)',  dash='dot', width=1))
    fig.add_trace(go.Scatter(x=stress.index, y=stress.clip(lower=0),
                             fill='tozeroy', fillcolor='rgba(255,75,110,0.10)',
                             line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=stress.index, y=stress.clip(upper=0),
                             fill='tozeroy', fillcolor='rgba(75,255,179,0.10)',
                             line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=stress.index, y=stress, name='신용 스트레스',
                             line=dict(color='#787EE7', width=1.5),
                             hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:.2f}<extra></extra>'))
    # 누적 스트레스
    fig.add_trace(go.Scatter(x=cum_stress.index, y=cum_stress, name='누적 스트레스(ADL식)',
                             line=dict(color='rgba(255,140,100,0.65)', width=1.1, dash='dot'),
                             showlegend=True, hoverinfo='skip', yaxis='y2'))
    # SPX 오버레이
    if spx_s is not None and not spx_s.empty:
        t0 = stress.index[0]
        spx_t = spx_s[spx_s.index >= t0]
        if len(spx_t) > 2:
            spx_pct = ((spx_t / spx_t.iloc[0]) - 1) * 100
            fig.add_trace(go.Scatter(x=spx_pct.index, y=spx_pct, name='S&P500(%)',
                                     line=dict(color='rgba(200,200,80,0.45)', width=1.0, dash='dash'),
                                     showlegend=True, hoverinfo='skip', yaxis='y3'))
    fig.update_layout(
        **_ml('② 신용 스트레스 지수 (HY + NFCI + VIX z-score 합성)'),
        yaxis2=_hidden_yaxis('y', 'right'),
        yaxis3=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(tickformat='+.1f')
    _add_corr_annotation(fig, stress, spx_s)
    return fig


def make_macro_options_chart(years: int = 5, spx_s=None):
    """③ VIX 텀스트럭처: VIX 레벨 + VIX-VIX3M 스프레드(역전=공포 극대) + SKEW"""
    vix   = _yf_close('^VIX',   years)
    vix3m = _yf_close('^VIX3M', years)
    skew  = _yf_close('^SKEW',  years)
    if vix.empty:
        return None

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.60, 0.40],
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=['VIX 레벨  /  VIX-VIX3M 스프레드 (우, 역전=붉은 영역)', 'SKEW 지수'],
    )

    # ── Row 1: VIX 레벨
    fig.add_hline(y=20, line=dict(color='rgba(255,255,255,0.12)', dash='dot', width=1), row=1, col=1)
    fig.add_hline(y=30, line=dict(color='rgba(255,75,110,0.30)', dash='dot', width=1), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=vix.index, y=vix, name='VIX 레벨',
        line=dict(color='#FF4B6E', width=1.7),
        hovertemplate='<b>%{x|%Y-%m-%d}</b>  VIX %{y:.1f}<extra></extra>',
    ), row=1, col=1)

    # ── Row 1 우축: VIX - VIX3M 스프레드 (핵심 시그널)
    #   양수(VIX > VIX3M) = 단기 공포 > 장기 → 역전 = 공포 극대 (빨간 영역)
    #   역전 해소(0 하향 돌파) = 매수 타이밍
    if not vix3m.empty:
        spread = (vix - vix3m.reindex(vix.index)).dropna()
        if len(spread) > 2:
            # 역전 구간 (양수, 빨간)
            fig.add_trace(go.Scatter(
                x=spread.index, y=spread.clip(lower=0),
                fill='tozeroy', fillcolor='rgba(255,75,110,0.18)',
                line=dict(width=0), showlegend=False, hoverinfo='skip',
                yaxis='y3',
            ))
            # 정상 컨탱고 구간 (음수, 초록)
            fig.add_trace(go.Scatter(
                x=spread.index, y=spread.clip(upper=0),
                fill='tozeroy', fillcolor='rgba(75,255,179,0.08)',
                line=dict(width=0), showlegend=False, hoverinfo='skip',
                yaxis='y3',
            ))
            fig.add_trace(go.Scatter(
                x=spread.index, y=spread,
                name='VIX-VIX3M 스프레드 (우)',
                line=dict(color='#FF8C69', width=1.4),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  스프레드 %{y:.2f}<extra></extra>',
                yaxis='y3',
            ))

    # ── Row 2: SKEW
    if not skew.empty:
        fig.add_hline(y=130, line=dict(color='rgba(120,126,231,0.30)', dash='dot', width=1), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=skew.index, y=skew, name='SKEW',
            line=dict(color='#787EE7', width=1.3),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  SKEW %{y:.1f}<extra></extra>',
        ), row=2, col=1)

    # ── SPX 오버레이 (row1 숨김 우축)
    if spx_s is not None and not spx_s.empty and len(vix) > 2:
        t0 = vix.index[0]
        spx_t = spx_s[spx_s.index >= t0]
        if len(spx_t) > 2:
            spx_pct = ((spx_t / spx_t.iloc[0]) - 1) * 100
            fig.add_trace(go.Scatter(
                x=spx_pct.index, y=spx_pct, name='S&P500(%)',
                line=dict(color='rgba(200,200,80,0.40)', width=1.0, dash='dash'),
                showlegend=True, hoverinfo='skip', yaxis='y4',
            ))

    fig.update_layout(
        height=400,
        title=dict(
            text='③ VIX 텀스트럭처 · SKEW  (VIX>VIX3M 역전=공포 극대, 해소=매수 시점)',
            font=dict(size=12, color='#9B9B9B'), x=0, y=0.98,
        ),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#9B9B9B', size=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1,
                    font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=50, r=55, t=45, b=30),
        hovermode='x unified',
        # y3: 스프레드 우측 축 (눈금 표시)
        yaxis3=dict(
            overlaying='y', anchor='x', side='right',
            showgrid=False, showticklabels=True, showline=True,
            linecolor='rgba(255,140,100,0.3)', tickfont=dict(size=8, color='#FF8C69'),
            zeroline=True, zerolinecolor='rgba(255,75,110,0.6)', zerolinewidth=1.5,
        ),
        # y4: SPX 숨김
        yaxis4=dict(overlaying='y', anchor='x', side='right',
                    showgrid=False, showticklabels=False, showline=False, zeroline=False),
    )
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9))
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False)
    # subplot_titles 색상
    for ann in fig.layout.annotations:
        ann.font.size  = 9
        ann.font.color = '#666'
    _add_corr_annotation(fig, vix, spx_s, label='VIX vs S&P500')
    return fig


def make_macro_pmi_chart(years: int = 5, spx_s=None):
    """④ ISM 신규주문-재고 스프레드 (대리지표: 제조업 신규주문 vs 재고-판매비율)
    ISM 원데이터는 FRED에 없으므로:
      - 신규주문 proxy: AMTMNO (전체 제조업 신규주문, SA) → NEWORDER → DGORDER 순 fallback
      - 재고 proxy: ISRATIO (재고/판매비율) 역방향 — 재고 증가=악화
    스프레드 = 신규주문 YoY% - 재고비율 YoY%
    양→음 전환 시 경기 둔화 확정적 (ISM 스프레드 개념 동일)
    """
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)

    # 신규주문 proxy (3단계 fallback)
    ord_s = pd.Series(dtype=float)
    ord_label = ''
    for sid, lbl in [('AMTMNO', '全제조 신규주문'), ('NEWORDER', '자본재 신규주문'), ('DGORDER', '내구재 주문')]:
        ord_s = _fred(sid, years + 2)
        if not ord_s.empty:
            ord_label = lbl
            break

    # 재고 proxy
    inv_s    = _fred('ISRATIO', years + 2)  # 재고/판매비율: 높을수록 재고 과잉 = 악화
    inv_label = '재고/판매비율'

    if ord_s.empty:
        return None

    # YoY% 변환
    ord_yoy = (ord_s.pct_change(12) * 100).dropna()
    ord_yoy = ord_yoy[ord_yoy.index >= cutoff]

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))

    fig.add_trace(go.Scatter(
        x=ord_yoy.index, y=ord_yoy,
        name=f'{ord_label} YoY%',
        line=dict(color='#4BFFB3', width=1.6),
        hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:.1f}%<extra></extra>',
    ))

    main_s = ord_yoy
    spread_s = pd.Series(dtype=float)

    if not inv_s.empty:
        inv_yoy = (inv_s.pct_change(12) * 100).dropna()
        inv_yoy = inv_yoy[inv_yoy.index >= cutoff]
        # 재고 악화(+) → 시그널 반전해서 표시 (재고 줄면 좋음 → 양의 기여)
        fig.add_trace(go.Scatter(
            x=inv_yoy.index, y=-inv_yoy,
            name=f'{inv_label} YoY% (부호반전, 우)',
            line=dict(color='#FF8C69', width=1.2, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:.1f}%<extra></extra>',
            yaxis='y2',
        ))
        # 스프레드 = 신규주문 YoY% + 재고비율 YoY% 반전 (클수록 수요>공급)
        aligned = ord_yoy.reindex(inv_yoy.index).dropna()
        inv_aligned = inv_yoy.reindex(aligned.index).dropna()
        aligned = aligned.reindex(inv_aligned.index)
        spread_s = (aligned - inv_aligned).dropna()

    if not spread_s.empty:
        fig.add_trace(go.Scatter(
            x=spread_s.index, y=spread_s.clip(lower=0),
            fill='tozeroy', fillcolor='rgba(75,255,179,0.10)',
            line=dict(width=0), showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=spread_s.index, y=spread_s.clip(upper=0),
            fill='tozeroy', fillcolor='rgba(255,75,110,0.10)',
            line=dict(width=0), showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=spread_s.index, y=spread_s,
            name='신규주문-재고 스프레드 ★',
            line=dict(color='#C8C850', width=1.8),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  스프레드 %{y:.1f}<extra></extra>',
        ))
        main_s = spread_s

    _add_spx_cum_overlays(fig, main_s, spx_s, cum_yaxis='y3', spx_yaxis='y4',
                          cum_label='스프레드 누적')
    fig.update_layout(
        **_ml('④ ISM 신규주문-재고 스프레드 (대리: 제조업 신규주문 vs 재고비율)'),
        yaxis2=dict(overlaying='y', side='right', showgrid=False,
                    tickfont=dict(size=9), zeroline=False, ticksuffix='%'),
        yaxis3=_hidden_yaxis('y', 'right'),
        yaxis4=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(ticksuffix='%')
    _add_corr_annotation(fig, main_s, spx_s)
    return fig


def make_macro_liquidity_chart(years: int = 5, spx_s=None):
    """⑤ 유동성: M2 YoY% + Fed 자산 YoY%"""
    m2  = _fred('M2SL',  years + 2)
    fed = _fred('WALCL', years + 2)
    if m2.empty and fed.empty:
        return None
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.2)', width=1))
    main_s = None
    if not m2.empty:
        m2_yoy = (m2.pct_change(12) * 100).dropna()
        m2_yoy = m2_yoy[m2_yoy.index >= cutoff]
        fig.add_trace(go.Scatter(x=m2_yoy.index, y=m2_yoy, name='M2 YoY%',
                                 line=dict(color='#4BFFB3', width=1.5)))
        main_s = m2_yoy
    if not fed.empty:
        fed_yoy = (fed.pct_change(52) * 100).dropna()
        fed_yoy = fed_yoy[fed_yoy.index >= cutoff]
        fig.add_trace(go.Scatter(x=fed_yoy.index, y=fed_yoy, name='Fed 자산 YoY% (우)',
                                 line=dict(color='#787EE7', width=1.3, dash='dot'), yaxis='y2'))
        if main_s is None:
            main_s = fed_yoy
    _add_spx_cum_overlays(fig, main_s, spx_s, cum_yaxis='y3', spx_yaxis='y4',
                          cum_label='M2 누적변화')
    fig.update_layout(
        **_ml('⑤ 유동성 지표 (M2 · Fed 자산 YoY%)'),
        yaxis2=dict(overlaying='y', side='right', showgrid=False, tickfont=dict(size=9),
                    zeroline=False, ticksuffix='%'),
        yaxis3=_hidden_yaxis('y', 'right'),
        yaxis4=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(ticksuffix='%')
    _add_corr_annotation(fig, main_s, spx_s)
    return fig


def make_macro_yield_curve_chart(years: int = 5, spx_s=None):
    """⑥ 장단기 금리차: T10Y3M(10Y-3M) + T10Y2Y(10Y-2Y)
    1순위: FRED 사전계산 시리즈 (T10Y3M, T10Y2Y) — 더 안정적
    2순위: 구성 금리 직접 차감 (DGS10 - DTB3 / DGS2) — fallback
    """
    # 1순위: FRED 사전계산
    t3m = _fred('T10Y3M', years)
    t2y = _fred('T10Y2Y', years)
    # 2순위: 직접 계산 (어느 한 쪽이라도 비었으면 시도)
    if t3m.empty or t2y.empty:
        dgs10 = _fred('DGS10', years)
        dtb3  = _fred('DTB3',  years)
        dgs2  = _fred('DGS2',  years)
        if not dgs10.empty:
            idx = dgs10.index
            if t3m.empty and not dtb3.empty:
                t3m = (dgs10 - dtb3.reindex(idx).interpolate()).dropna()
            if t2y.empty and not dgs2.empty:
                t2y = (dgs10 - dgs2.reindex(idx).interpolate()).dropna()
    if t3m.empty and t2y.empty:
        return None
    main_s = t3m if not t3m.empty else t2y
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,75,110,0.5)', width=1.2))
    if not t3m.empty:
        fig.add_trace(go.Scatter(x=t3m.index, y=t3m.clip(lower=0),
                                 fill='tozeroy', fillcolor='rgba(75,255,179,0.08)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=t3m.index, y=t3m.clip(upper=0),
                                 fill='tozeroy', fillcolor='rgba(255,75,110,0.12)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=t3m.index, y=t3m, name='10Y-3M',
                                 line=dict(color='#4BFFB3', width=1.5)))
    if not t2y.empty:
        fig.add_trace(go.Scatter(x=t2y.index, y=t2y, name='10Y-2Y',
                                 line=dict(color='#C8C850', width=1.2, dash='dot')))
    _add_spx_cum_overlays(fig, main_s, spx_s, cum_yaxis='y2', spx_yaxis='y3',
                          cum_label='10Y-3M 누적변화')
    fig.update_layout(
        **_ml('⑥ 장단기 금리차 (0 이하 = 역전 = 경기침체 선행 신호)'),
        yaxis2=_hidden_yaxis('y', 'right'),
        yaxis3=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(ticksuffix='%')
    _add_corr_annotation(fig, main_s, spx_s)
    return fig


def make_macro_foreign_flow_chart(market_code: str, years: int = 5, spx_s=None):
    """⑦ 외국인 누적 순매수 (주식시장 proxy, 억원) + KOSPI/KOSDAQ 지수 오버레이"""
    s, _err = _foreign_cumnet(market_code, years)
    if s.empty:
        return None, _err
    idx_code = '^KS11' if market_code == 'KOSPI' else '^KQ11'
    mkt_s    = _yf_close(idx_code, years)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s, name=f'{market_code} 외국인 누적',
        line=dict(color='#787EE7', width=1.5),
        fill='tozeroy', fillcolor='rgba(120,126,231,0.07)',
        hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:,.0f}억원<extra></extra>',
    ))
    # 지수 오버레이 (KOSPI or KOSDAQ)
    if not mkt_s.empty and len(mkt_s) > 2:
        t0 = s.index[0]
        mkt_t = mkt_s[mkt_s.index >= t0]
        if len(mkt_t) > 2:
            mkt_pct = ((mkt_t / mkt_t.iloc[0]) - 1) * 100
            fig.add_trace(go.Scatter(
                x=mkt_pct.index, y=mkt_pct, name=f'{market_code} 지수(%)',
                line=dict(color='rgba(200,200,80,0.55)', width=1.2, dash='dash'),
                showlegend=True, hoverinfo='skip', yaxis='y2',
            ))
    fig.update_layout(
        **_ml(f'⑦ 외국인 누적 순매수 — {market_code} (억원)', height=280),
        yaxis2=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(tickformat=',.0f')
    _add_corr_annotation(fig, s, mkt_s, label=f'vs {market_code}')
    return fig, None


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

        # ── 차트 모드 (사이드바 최상단 — period 기본값에 영향)
        _intra_interval_map = {"5분": "5m", "15분": "15m", "30분": "30m", "60분": "60m"}
        _intra_bars_per_day = {"5m": 78, "15m": 26, "30m": 13, "60m": 7}
        st.markdown("**🕯 차트 모드**")
        chart_mode = st.radio(
            "차트모드", ["일봉", "분봉"], horizontal=True,
            label_visibility="collapsed", key="chart_mode",
        )
        if chart_mode == "분봉":
            intra_interval_label = st.radio(
                "분봉", list(_intra_interval_map.keys()), horizontal=True,
                label_visibility="collapsed", key="intra_interval",
            )
            yf_interval = _intra_interval_map[intra_interval_label]

            st.divider()
            st.markdown("**🔄 자동 새로고침**")
            auto_refresh = st.toggle("분봉 자동 갱신", value=False, key="auto_refresh_toggle")
            if auto_refresh:
                refresh_interval_label = st.radio(
                    "갱신 주기", ["1분", "3분", "5분"], index=2,
                    horizontal=True, label_visibility="collapsed", key="refresh_interval",
                )
                _refresh_ms = {"1분": 60_000, "3분": 180_000, "5분": 300_000}
                refresh_ms = _refresh_ms[refresh_interval_label]
            else:
                auto_refresh = False
                refresh_ms = 300_000
        else:
            intra_interval_label = None
            yf_interval = None
            auto_refresh = False
            refresh_ms = 300_000

        st.divider()

        # ── 차트 기간 (모드 전환 시 기본값 자동 변경)
        _period_keys = list(PERIOD_OPTIONS.keys())
        _default_period = "3일" if chart_mode == "분봉" else "3개월"
        if st.session_state.get('_prev_chart_mode_period') != chart_mode:
            st.session_state['sidebar_period'] = _default_period
            st.session_state['_prev_chart_mode_period'] = chart_mode
        st.markdown("**📅 차트 기간**")
        period_name = st.radio(
            "기간", _period_keys,
            key='sidebar_period',
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
            value=1,
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

    tab1, tab2, tab3 = st.tabs(["📊 신호 스캐너", "🌐 시장 내부지표", "🌍 매크로 지표"])

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — 신호 스캐너
    # ═══════════════════════════════════════════════════════════
    with tab1:
        # ── DEBUG (KIS 동작 확인 후 삭제) ────────────────────────────
        with st.expander("🔍 KIS 디버그 (확인 후 삭제)", expanded=True):
            import requests as _req
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _kst = _tz(_td(hours=9))
            _now_kst = _dt.now(_kst)
            st.write(f"현재 KST: {_now_kst.strftime('%H:%M:%S')}  (장중: 09:00~15:30)")
            try:
                _tok = _kis_token()
                st.write(f"KIS 토큰: {'✅ 발급됨' if _tok else '❌ None'}")
            except Exception as _e:
                st.write(f"KIS 토큰 오류: {_e}")
                _tok = None
            if _tok:
                try:
                    _cfg = dict(st.secrets.get("kis", {}))
                    _base = ("https://openapivts.koreainvestment.com:9443"
                             if _cfg.get("is_mock", True)
                             else "https://openapi.koreainvestment.com:9443")
                    st.write(f"API 서버: {'🟡 모의(VTS)' if _cfg.get('is_mock', True) else '🟢 실서버'} — {_base}")
                    _qtime = _now_kst.strftime("%H%M%S")
                    _r = _req.get(
                        f"{_base}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                        headers={"authorization": f"Bearer {_tok}",
                                 "appkey": _cfg["app_key"], "appsecret": _cfg["app_secret"],
                                 "tr_id": "FHKST03010200", "custtype": "P"},
                        params={"FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J",
                                "FID_INPUT_ISCD": "005930", "FID_INPUT_HOUR_1": _qtime,
                                "FID_PW_DATA_INCU_YN": "Y"},
                        timeout=10)
                    _rj = _r.json()
                    st.write(f"HTTP {_r.status_code}  |  rt_cd={_rj.get('rt_cd')}  msg={_rj.get('msg1','')}")
                    st.write(f"output2 행수: {len(_rj.get('output2') or [])}")
                except Exception as _e:
                    import traceback; st.write(f"API 직접 호출 오류:\n{traceback.format_exc()}")
            if chart_mode == "분봉":
                try:
                    _idf, _ierr = fetch_intraday("005930.KS", yf_interval)
                    st.write(f"fetch_intraday {yf_interval}: {len(_idf)}행  |  최신봉={_idf.index[-1] if not _idf.empty else 'empty'}")
                    if _ierr: st.write(f"  에러: {_ierr}")
                except Exception as _e:
                    st.write(f"fetch_intraday 오류: {_e}")
        # ── END DEBUG ────────────────────────────────────────────────

        # 자동 새로고침 (분봉 모드 + 토글 ON 일 때만)
        if auto_refresh and AUTOREFRESH_AVAILABLE:
            _count = st_autorefresh(interval=refresh_ms, key="intra_autorefresh")
        elif auto_refresh and not AUTOREFRESH_AVAILABLE:
            st.warning("⚠️ 자동 새로고침을 사용하려면 `streamlit-autorefresh` 패키지가 필요합니다.")

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

        # US 워치리스트 (신호 계산에 필요해 tickers_tuple보다 먼저 정의)
        _US_WATCHLIST = [
            # ── 지수 (이름 오름차순: ASCII → 가나다)
            {"code": "^GSPC",  "name": "S&P 500 (^GSPC)"},
            {"code": "^IXIC",  "name": "나스닥 (^IXIC)"},
            {"code": "^DJI",   "name": "다우존스 (^DJI)"},
            # ── 단일종목 (이름 오름차순: ASCII → 가나다)
            {"code": "QBTS",   "name": "D-Wave 퀀텀 (QBTS)"},
            {"code": "GOOGL",  "name": "구글 알파벳 (GOOGL)"},
            {"code": "HG=F",   "name": "구리 현물 (Copper Futures)"},
            {"code": "GC=F",   "name": "금 현물 (Gold Futures)"},
            {"code": "RGTI",   "name": "리게티컴퓨팅 (RGTI)"},
            {"code": "MSFT",   "name": "마이크로소프트 (MSFT)"},
            {"code": "BTC-USD", "name": "비트코인 (BTC-USD)"},
            {"code": "AMZN",   "name": "아마존 (AMZN)"},
            {"code": "IONQ",   "name": "아이온큐 (IONQ)"},
            {"code": "NVDA",   "name": "엔비디아 (NVDA)"},
            {"code": "SI=F",   "name": "은 현물 (Silver Futures)"},
            {"code": "ETH-USD", "name": "이더리움 (ETH-USD)"},
            {"code": "TSLA",   "name": "테슬라 (TSLA)"},
            {"code": "PLTR",   "name": "팔란티어 (PLTR)"},
            # ── ETF 1배 (코드 오름차순)
            {"code": "AIPO",   "name": "AIPO AI·IPO ETF"},
            {"code": "ARKQ",   "name": "ARKQ ARK 자율주행/로봇 ETF"},
            {"code": "BLOK",   "name": "BLOK 블록체인 ETF"},
            {"code": "GRID",   "name": "GRID 스마트그리드 ETF"},
            {"code": "NLR",    "name": "NLR 원자력 ETF"},
            {"code": "PTIR",   "name": "PTIR 테크인프라 ETF"},
            {"code": "QTUM",   "name": "QTUM 퀀텀컴퓨팅/AI ETF"},
            {"code": "SHLD",   "name": "SHLD 방산테크 ETF"},
            {"code": "SOXX",   "name": "SOXX 반도체 ETF"},
            {"code": "TAN",    "name": "TAN 태양광 ETF"},
            {"code": "UFO",    "name": "UFO 우주항공 ETF"},
            {"code": "XLU",    "name": "XLU 유틸리티 ETF"},
            # ── ETF 2배 (코드 오름차순)
            {"code": "AMZU",   "name": "AMZU 아마존 2X"},
            {"code": "GGLL",   "name": "GGLL 구글 2X"},
            {"code": "MSFU",   "name": "MSFU 마이크로소프트 2X"},
            {"code": "NVDL",   "name": "NVDL 엔비디아 2X"},
            {"code": "TSLL",   "name": "TSLL 테슬라 2X"},
            {"code": "UGL",    "name": "UGL 금 2X"},
            {"code": "USD",    "name": "USD 반도체 2X (ProShares)"},
            # ── ETF 3배 (코드 오름차순)
            {"code": "SOXL",   "name": "SOXL 반도체 3X"},
            {"code": "TECL",   "name": "TECL 테크 3X"},
            {"code": "TQQQ",   "name": "TQQQ 나스닥 3X"},
        ]

        tickers_tuple    = tuple(f['code'] for f in favorites)
        us_tickers_tuple = tuple(t['code'] for t in _US_WATCHLIST)

        with st.spinner("📡 데이터 로딩..."):
            if chart_mode == "분봉":
                closes = fetch_intraday_batch(tickers_tuple, yf_interval)
            else:
                closes = fetch_close_batch(tickers_tuple, data_start, data_end)
            us_closes = fetch_close_batch(us_tickers_tuple, data_start, data_end)

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
            # 화면 badge와 동일한 기준 (dyn만) — band_* 는 display에 없으므로 정렬에서도 제외
            # 매수신호 > 매수플래그 > 보유중 > 매도신호 > 매도플래그 > 없음
            buy_sig   = r.get('dyn_buy_signal')
            buy_flag  = r.get('dyn_buy_flag') and not r.get('dyn_buy_signal')
            holding   = r.get('dyn_holding')
            sell_sig  = r.get('dyn_sell_signal')
            sell_flag = r.get('dyn_sell_flag') and not r.get('dyn_sell_signal')
            if buy_sig:   return 0
            if buy_flag:  return 1
            if holding:   return 2
            if sell_sig:  return 3
            if sell_flag: return 4
            return 5

        signal_rows.sort(key=sort_key)

        # US 신호 계산
        us_signal_rows = []
        for _item in _US_WATCHLIST:
            _code = _item['code']
            _row = {
                'code': _code, 'name': _item['name'],
                'close': None, 'pct_change': None, 'rsi': None,
                'bb_upper_touch': False, 'bb_lower_touch': False,
                'dyn_buy_signal': False, 'dyn_sell_signal': False,
                'band_buy_signal': False, 'band_sell_signal': False,
                'dyn_buy_flag': False, 'dyn_sell_flag': False,
                'band_buy_flag': False, 'band_sell_flag': False,
                'dyn_holding': False, 'band_holding': False,
            }
            if _code in us_closes.columns:
                _series = us_closes[_code].dropna()
                _sig = get_current_signals(
                    _series,
                    bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
                    rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
                    rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
                    phase2_rsi=phase2_rsi,
                )
                if _sig:
                    _row.update(_sig)
                elif len(_series) >= 2:
                    _last = float(_series.iloc[-1])
                    _prev = float(_series.iloc[-2])
                    _row['close'] = _last
                    _row['pct_change'] = (_last / _prev - 1) * 100 if _prev else 0.0
            us_signal_rows.append(_row)
        us_signal_rows.sort(key=sort_key)

        # 신호 요약 카운트 — 한국
        n_dyn_buy_flag  = sum(1 for r in signal_rows if r.get('dyn_buy_flag')  and not r.get('dyn_buy_signal'))
        n_dyn_buy       = sum(1 for r in signal_rows if r.get('dyn_buy_signal'))
        n_dyn_hold      = sum(1 for r in signal_rows if r.get('dyn_holding'))
        n_dyn_sell_flag = sum(1 for r in signal_rows if r.get('dyn_sell_flag') and not r.get('dyn_sell_signal'))
        n_dyn_sell      = sum(1 for r in signal_rows if r.get('dyn_sell_signal'))

        # 신호 요약 카운트 — 미국
        n_us_buy_flag   = sum(1 for r in us_signal_rows if r.get('dyn_buy_flag')  and not r.get('dyn_buy_signal'))
        n_us_buy        = sum(1 for r in us_signal_rows if r.get('dyn_buy_signal'))
        n_us_hold       = sum(1 for r in us_signal_rows if r.get('dyn_holding'))
        n_us_sell_flag  = sum(1 for r in us_signal_rows if r.get('dyn_sell_flag') and not r.get('dyn_sell_signal'))
        n_us_sell       = sum(1 for r in us_signal_rows if r.get('dyn_sell_signal'))

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

        def _mini_label(flag):
            return (f'<div style="display:flex;align-items:center;justify-content:center;'
                    f'min-width:32px;background:#141416;'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:6px;'
                    f'font-size:13px;flex-shrink:0;">{flag}</div>')

        def _mini_row(prefix, items, flag=''):
            label = _mini_label(flag) if flag else ''
            cards = "".join(_mini_card(f"{prefix} {lbl}", val, acc) for lbl, val, acc in items)
            return (f'<div style="display:flex;gap:5px;margin-bottom:5px;align-items:stretch;">'
                    f'{label}{cards}</div>')

        st.markdown(
            '<div style="margin-bottom:20px">' +
            _mini_row("★", [
                ("매수 플래그", f"{n_dyn_buy_flag}",  "#7AAFD4"),
                ("매수 신호",   f"{n_dyn_buy}",        "#4BFFB3"),
                ("보유 중",     f"{n_dyn_hold}",       "#C8C850"),
                ("매도 플래그", f"{n_dyn_sell_flag}",  "#D47A9F"),
                ("매도 신호",   f"{n_dyn_sell}",       "#FF4B6E"),
            ], flag='🇰🇷') +
            _mini_row("★", [
                ("매수 플래그", f"{n_us_buy_flag}",   "#7AAFD4"),
                ("매수 신호",   f"{n_us_buy}",         "#4BFFB3"),
                ("보유 중",     f"{n_us_hold}",        "#C8C850"),
                ("매도 플래그", f"{n_us_sell_flag}",   "#D47A9F"),
                ("매도 신호",   f"{n_us_sell}",        "#FF4B6E"),
            ], flag='🇺🇸') +
            '</div>',
            unsafe_allow_html=True,
        )

        # ── 활성 시장 추적 (session_state)
        if 'scan_active' not in st.session_state:
            st.session_state.scan_active = 'kr'

        def _set_kr(): st.session_state.scan_active = 'kr'
        def _set_us(): st.session_state.scan_active = 'us'

        # ① 전체 종목 현황 — 한국 / 미국 분리 (접힘)
        with st.expander(f"📋 🇰🇷 한국 즐겨찾기 현황 ({len(signal_rows)}개)", expanded=False):
            st.markdown(render_signal_table(signal_rows), unsafe_allow_html=True)

        with st.expander(f"📋 🇺🇸 미국 지수/ETF 현황 ({len(us_signal_rows)}개)", expanded=False):
            st.markdown(render_signal_table(us_signal_rows), unsafe_allow_html=True)

        # ② 종목 선택 — 한국 / 미국 좌우 분리
        col_kr, col_us = st.columns(2)

        kr_names = [f['name'] for f in favorites]
        us_names = [t['name'] for t in _US_WATCHLIST]

        with col_kr:
            with st.expander("🇰🇷 한국 즐겨찾기", expanded=True):
                if 'scan_kr_name' not in st.session_state or \
                        st.session_state.scan_kr_name not in kr_names:
                    st.session_state.scan_kr_name = kr_names[0]
                st.selectbox("한국종목선택", kr_names,
                             key='scan_kr_name', on_change=_set_kr,
                             label_visibility='collapsed')

        with col_us:
            with st.expander("🇺🇸 미국 지수/ETF", expanded=True):
                if 'scan_us_name' not in st.session_state or \
                        st.session_state.scan_us_name not in us_names:
                    st.session_state.scan_us_name = us_names[0]
                st.selectbox("미국종목선택", us_names,
                             key='scan_us_name', on_change=_set_us,
                             label_visibility='collapsed')

        # 활성 티커 결정
        if st.session_state.scan_active == 'kr':
            _kr_name = st.session_state.get('scan_kr_name', kr_names[0])
            _sel_item = next((f for f in favorites if f['name'] == _kr_name), favorites[0])
            selected_name = _sel_item['name']
            selected_code = _sel_item['code']
        else:
            _us_name = st.session_state.get('scan_us_name', us_names[0])
            _sel_item = next((t for t in _US_WATCHLIST if t['name'] == _us_name), _US_WATCHLIST[0])
            selected_name = _sel_item['name']
            selected_code = _sel_item['code']

        # 한국 시간대 판별 (지수 코드 포함)
        _is_korean = selected_code.endswith(('.KS', '.KQ')) or \
                     selected_code in ('^KS11', '^KQ11')

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── 일봉 차트 ──────────────────────────────────────
        if chart_mode == "일봉":
            with st.spinner("차트 로딩..."):
                ohlcv = fetch_ohlcv(selected_code, data_start, data_end)

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
            _ticker = selected_code
            with st.spinner(f"분봉 로딩... ({intra_interval_label}, {period_name} 기준)"):
                ohlcv_intra, intra_err = fetch_intraday(_ticker, yf_interval)

            if ohlcv_intra.empty:
                st.warning(f"⚠️ {selected_name} 분봉 데이터를 가져올 수 없습니다.")
                if intra_err:
                    st.code(intra_err, language=None)
            else:
                if intra_err:
                    st.caption(f"⚠️ 데이터 로딩 경고: {intra_err}")
                _disp_bars = _intra_bars_per_day[yf_interval] * period_days
                _session   = (15.5, 9.0) if _is_korean else None
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

        # ③ 신호 해석 가이드 — 접힘
        with st.expander("📖 신호 해석 가이드", expanded=False):
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
                "시장", ["코스피", "코스닥", "S&P 500", "나스닥 200"],
                horizontal=True,
                label_visibility="collapsed",
            )
        with col_period:
            _mkt_labels = {
                20: "20일", 42: "2개월", 63: "3개월",
                126: "6개월", 189: "9개월",
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

            # ── 종합판단 시계열 차트 (전폭)
            _score_ts_fig = make_score_timeseries_chart(market_df, market_choice)
            if _score_ts_fig is not None:
                st.plotly_chart(_score_ts_fig, use_container_width=True,
                                config={"displayModeBar": False})

            # ── 시장 강도 점수 (기존 감성 요약 대체)
            render_market_score_ui(market_df, market_choice)

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

            summ_val = float(latest['서머레이션'])
            vix_val  = latest['VIX']
            ma20_val = latest['상승비율MA20']
            p200_val = latest['100MA상위']
            p50_val  = latest.get('20MA상위')
            adl_chg  = float(latest['ADL'] - prev['ADL'])
            vix_lbl  = "변동성(HV20)" if market_choice in ("코스피", "코스닥") else "VIX"

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
                _mkt_card("20MA 상위",
                    f"{p50_val:.1f}%" if pd.notna(p50_val) else "—",
                    "강세" if (pd.notna(p50_val) and float(p50_val) > 50)
                    else "약세",
                    "#87CEEB" if (pd.notna(p50_val) and float(p50_val) > 50) else "#FF4B6E"),
                _mkt_card("100MA 상위",
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

            with st.expander("📖 지표 쉽게 이해하기", expanded=False):
                st.markdown("""
<style>
.guide-table { width:100%; border-collapse:collapse; font-size:12px; }
.guide-table th { background:#1a1a2e; color:#787EE7; padding:7px 10px; text-align:left; border-bottom:1px solid #2a2a3e; }
.guide-table td { padding:6px 10px; border-bottom:1px solid #1e1e2e; vertical-align:top; line-height:1.6; }
.guide-table tr:hover td { background:rgba(120,126,231,0.04); }
.bull { color:#4BFFB3; font-weight:600; }
.bear { color:#FF4B6E; font-weight:600; }
.neut { color:#C8C850; font-weight:600; }
</style>

<table class="guide-table">
<tr>
  <th>지표 이름</th>
  <th>한 줄 설명 (쉽게)</th>
  <th>🟢 좋은 신호</th>
  <th>🔴 나쁜 신호</th>
  <th>결론 내리는 법</th>
</tr>
<tr>
  <td><b>시총가중 지수</b></td>
  <td>삼성·애플 같은 큰 회사 위주로 시장이 얼마나 올랐나</td>
  <td class="bull">꾸준히 우상향</td>
  <td class="bear">꺾이며 하락</td>
  <td>우리가 흔히 보는 코스피·S&P500 과 같은 개념. 가장 기본 지표</td>
</tr>
<tr>
  <td><b>균일가중 지수</b></td>
  <td>큰 회사·작은 회사 모두 똑같이 1표씩 줬을 때의 시장. "골고루 오르나?" 확인용</td>
  <td class="bull">시총가중과 함께 오름</td>
  <td class="bear">시총가중만 오르고 이건 제자리</td>
  <td>둘이 같이 오르면 건강한 장. 시총가중만 오르면 일부 대형주만 끌어올리는 불안한 장</td>
</tr>
<tr>
  <td><b>ADL (등락누적선)</b></td>
  <td>매일 오른 종목 수 − 내린 종목 수를 계속 더한 값. 시장이 진짜 건강한지 보여줌</td>
  <td class="bull">계속 우상향</td>
  <td class="bear">지수는 오르는데 ADL은 내려감 (위험 신호!)</td>
  <td><b>가장 중요한 선행지표.</b> 지수보다 ADL이 먼저 꺾이면 조정이 곧 온다는 경고. ADL이 먼저 올라오면 반등 시작 신호</td>
</tr>
<tr>
  <td><b>52주 신고가 비율</b></td>
  <td>오늘 1년(52주) 내 최고가를 찍은 종목 수 ÷ 전체 유효 종목 수 × 100. 진짜 상승 모멘텀이 있는지 확인</td>
  <td class="bull">30% 이상 = 강한 상승 모멘텀</td>
  <td class="bear">5% 이하 = 신고가 거의 없음 (약세 신호)</td>
  <td>지수가 오르는데 신고가 비율이 낮으면 소수 대형주만 끌어올리는 불안한 장. 역대 최고가 갱신 구간에서 30%+ 유지되면 진짜 상승장</td>
</tr>
<tr>
  <td><b>20일선 상위 비율</b></td>
  <td>20일(약 1달) 평균 가격보다 지금 비싼 종목이 몇 %인지. 단기 추세의 건강도를 빠르게 파악</td>
  <td class="bull">50% 이상 = 단기 강세 흐름</td>
  <td class="bear">50% 이하 = 단기 약세 흐름</td>
  <td>100일선 상위 비율보다 민감하게 반응해서 추세 전환을 더 빨리 알려줌. 50%선을 뚫고 올라오면 단기 반등 확인 신호</td>
</tr>
<tr>
  <td><b>맥클렐란 서머레이션</b></td>
  <td>단기·장기 평균 등락 차이를 계속 누적한 값. "지금 강세장인지 약세장인지" 큰 그림</td>
  <td class="bull">0 이상 (강세장 영역)</td>
  <td class="bear">0 이하 (약세장 영역)</td>
  <td>0선 위면 강세장, 아래면 약세장. 0선을 뚫고 올라오면 장세 전환 신호. 0선 위에서 하락 전환하면 조정 경고</td>
</tr>
<tr>
  <td><b>VIX / 역사적변동성(HV20)</b></td>
  <td>투자자들이 얼마나 겁먹고 있나. 미국=VIX(옵션 내재변동성), 한국=HV20(지수 20일 실현변동성). 숫자 클수록 불안</td>
  <td class="bull">급등 후 빠르게 내려올 때 → 공포 해소 = 반등 신호</td>
  <td class="bear">낮은 수준에서 갑자기 급등 → 조정 시작 신호</td>
  <td>미국 VIX: 20 이하=안심, 20~30=주의, 30 이상=공포. 한국 HV20: 15 이하=안심, 20 이상=주의, 25 이상=경계. <b>공포 극대일 때가 역발상 매수 타이밍</b>인 경우 많음</td>
</tr>
<tr>
  <td><b>상승비율 MA20</b></td>
  <td>오늘 전체 종목 중 오른 종목이 몇 %인지를 20일 평균낸 것</td>
  <td class="bull">60% 이상 유지</td>
  <td class="bear">40% 이하로 내려감</td>
  <td>50% 위면 "대부분 오르는 중", 아래면 "대부분 내리는 중". 하루치 수치는 변동 크니 20일 평균선만 봐도 충분</td>
</tr>
<tr>
  <td><b>100일선 상위 비율</b></td>
  <td>100일(약 5개월) 평균 가격보다 지금 비싼 종목이 몇 %인지</td>
  <td class="bull">70% 이상 = 강세장</td>
  <td class="bear">30% 이하 = 약세장 / 20% 이하 = 침체 바닥권</td>
  <td>중장기 건강도 지표. 30% 이하까지 내려간 뒤 반등하면 강력한 바닥 신호로 자주 활용됨</td>
</tr>
</table>

<br>

**🗺️ 지표 조합으로 지금 어느 상황인지 판단하기**

| 시장 상황 | ADL | 서머레이션 | 52주신고가 비율 | 100일선 상위 | 공포지수 | 내가 할 행동 |
|---------|-----|----------|------------|------------|---------|------------|
| 🟢 **상승 시작** | 바닥 찍고 올라오는 중 | 0선 위로 뚫음 | 30%→50% 회복 | 30%→50% 회복 중 | 30 이상에서 내려오는 중 | 적극적으로 매수할 타이밍 |
| 🟢 **상승 중반** | 계속 우상향 | +500 이상 | 70% 이상 유지 | 60~80% | 20 이하 (안심 구간) | 보유 유지. 추격 매수는 자제 |
| 🟡 **상승 막바지** | 지수는 오르는데 ADL은 정체 | +1000 이상이지만 더 안 오름 | 지수 오르는데 70% 이하 | 70% 이상 | 15 이하 (과도한 안심) | 비중 줄이고 차익실현 준비 |
| 🔴 **하락장** | 계속 우하향 | 0선 아래 | 30% 이하 | 30% 이하 | 30 이상 (공포) | 현금 비중 늘리기. 반등해도 매도 기회 |

> 균일가중 지수는 공식 지수가 아니라 직접 계산한 참고용 지표입니다.
> 첫 로딩 시 전체 종목 다운로드로 1~2분 소요됩니다.
                """, unsafe_allow_html=True)


            # ── 지표 선행성 분석
            with st.expander("🔬 지표 선행성 분석 (지수 예측력)", expanded=False):
                st.caption(
                    "corr(지표[오늘], 지수[오늘+N일]) — 값이 높을수록 해당 지표가 N일 후 지수를 예측하는 경향이 있음. "
                    "4년치 데이터를 별도 로딩합니다."
                )
                with st.spinner("4년 데이터 로딩 중..."):
                    _ll_df, _ = get_market_internals(market_choice, lookback_days=1008)

                if _ll_df is not None and not _ll_df.empty:
                    _ll_tbl = compute_lead_lag_table(_ll_df)
                    if not _ll_tbl.empty:
                        # 색상 함수
                        def _style_corr(v):
                            if pd.isna(v):
                                return 'color:#444'
                            ab = abs(v)
                            if ab >= 0.8:
                                c = '#00FF7F' if v > 0 else '#FF4B6E'
                            elif ab >= 0.6:
                                c = '#4BFFB3' if v > 0 else '#FF6B6B'
                            elif ab >= 0.4:
                                c = '#88D0B3' if v > 0 else '#FF9A6C'
                            else:
                                c = '#555'
                            return f'color:{c};font-weight:{"700" if ab>=0.7 else "400"}'

                        _styled = _ll_tbl.style.map(_style_corr).format(
                            lambda v: f"{v:+.2f}" if not pd.isna(v) else "—"
                        )
                        st.dataframe(_styled, use_container_width=True)
                        st.download_button(
                            "⬇ CSV 다운로드",
                            data=_ll_tbl.to_csv(float_format="%.2f"),
                            file_name=f"lead_lag_{market_choice}.csv",
                            mime="text/csv",
                        )
                    else:
                        st.info("데이터 부족으로 선행성 분석을 계산할 수 없습니다.")

    # ═══════════════════════════════════════════════════════════
    # TAB 3 — 매크로 지표
    # ═══════════════════════════════════════════════════════════
    with tab3:
        st.caption("FRED + yfinance 기반 매크로 지표 (일 1회 캐시). 미국 데이터 위주이며 참고용. 주황 점선=누적변화, 노란 파선=S&P500%.")

        _c1, _c2 = st.columns([3, 1])
        with _c1:
            _yr_opts = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년'}
            _macro_years = st.select_slider(
                "기간",
                options=list(_yr_opts.keys()),
                value=5,
                format_func=lambda x: _yr_opts[x],
                label_visibility='collapsed',
            )
        with _c2:
            _show_spx = st.checkbox("S&P500 오버레이", value=True)

        with st.spinner("📡 S&P500 데이터 로딩 중..."):
            _spx_s = _yf_close('^GSPC', _macro_years) if _show_spx else None

        with st.spinner("📡 매크로 데이터 로딩 중..."):
            _macro_charts = [
                make_macro_credit_spread_chart(_macro_years, _spx_s),   # ① 크레딧 스프레드
                make_macro_credit_stress_chart(_macro_years, _spx_s),   # ② 크레딧 스트레스 복합
                make_macro_options_chart(_macro_years,       _spx_s),   # ③ 옵션 심리 (VIX/SKEW)
                make_macro_pmi_chart(_macro_years,           _spx_s),   # ④ 경기 모멘텀
                make_macro_liquidity_chart(_macro_years,     _spx_s),   # ⑤ 유동성 (M2/Fed)
                make_macro_yield_curve_chart(_macro_years,   _spx_s),   # ⑥ 장단기 금리차
            ]

        _mc = st.columns(2)
        for i, ch in enumerate(_macro_charts):
            if ch is not None:
                with _mc[i % 2]:
                    st.plotly_chart(ch, use_container_width=True, config={"displayModeBar": False})
            else:
                with _mc[i % 2]:
                    _labels = ['① 크레딧 스프레드', '② 크레딧 스트레스', '③ VIX/SKEW',
                               '④ 경기 모멘텀', '⑤ 유동성', '⑥ 금리차']
                    st.warning(f"{_labels[i]} 데이터 로딩 실패 — FRED 일시 불가. 잠시 후 재시도해 주세요.")

        # ⑦ 외국인 순매수 누적 — KOSPI / KOSDAQ 선택
        st.divider()
        _ff_code = st.radio("외국인 순매수 시장", ['KOSPI', 'KOSDAQ'], horizontal=True,
                            label_visibility='visible')
        with st.spinner("📡 외국인 순매수 데이터 로딩 중..."):
            _ff, _ff_err = make_macro_foreign_flow_chart(_ff_code, _macro_years, _spx_s)
        if _ff is not None:
            st.plotly_chart(_ff, use_container_width=True, config={"displayModeBar": False})
        else:
            _err_detail = f" — {_ff_err}" if _ff_err else ""
            st.warning(f"⑦ 외국인 순매수 데이터 로딩 실패{_err_detail}")

        # ── 매크로 지표 상관계수 테이블 ───────────────────────────────────
        st.divider()
        st.markdown("##### 📊 매크로 지표 × S&P500 상관계수")
        st.caption("r > +0.3 🟢 양의 상관  /  r < -0.3 🔴 음의 상관  /  선행(1M·3M): 지표가 시장을 N개월 앞설 때")

        with st.spinner("상관계수 계산 중..."):
            # 각 지표 주요 시리즈 수집 (FRED 캐시 재사용)
            _cy = _macro_years
            _hy_s   = _fred('BAMLH0A0HYM2', _cy)
            _nfci_s = _fred('NFCI', _cy)
            _vix_s  = _yf_close('^VIX', _cy)
            _m2_s_raw = _fred('M2SL', _cy + 2)
            _m2_yoy = (_m2_s_raw.pct_change(12) * 100).dropna() if not _m2_s_raw.empty else pd.Series(dtype=float)
            _t3m_s  = _fred('T10Y3M', _cy)
            if _t3m_s.empty:
                _dgs10 = _fred('DGS10', _cy); _dtb3 = _fred('DTB3', _cy)
                if not _dgs10.empty and not _dtb3.empty:
                    _t3m_s = (_dgs10 - _dtb3.reindex(_dgs10.index).interpolate()).dropna()
            # ISM proxy
            _ord_s = pd.Series(dtype=float)
            for _sid in ('AMTMNO', 'NEWORDER', 'DGORDER'):
                _ord_s = _fred(_sid, _cy + 2)
                if not _ord_s.empty: break
            _ord_yoy = (_ord_s.pct_change(12) * 100).dropna() if not _ord_s.empty else pd.Series(dtype=float)

            _macro_named = {
                '① HY 스프레드':     _hy_s,
                '② NFCI':            _nfci_s,
                '③ VIX':             _vix_s,
                '④ 신규주문 YoY%':   _ord_yoy,
                '⑤ M2 YoY%':         _m2_yoy,
                '⑥ 10Y-3M 스프레드': _t3m_s,
            }

            if _spx_s is not None and not _spx_s.empty:
                _spx_ret = _spx_s.pct_change().dropna()
                _corr_rows = []
                for _nm, _s in _macro_named.items():
                    if _s.empty:
                        _corr_rows.append({'지표': _nm, '동기(r)': '—', '1M 선행(r)': '—', '3M 선행(r)': '—'})
                        continue
                    def _calc_r(series, shift_days=0):
                        try:
                            _spx_shifted = _spx_ret.shift(-shift_days) if shift_days else _spx_ret
                            _al = pd.concat([series.rename('x'), _spx_shifted.rename('y')], axis=1).dropna()
                            if len(_al) < 20: return float('nan')
                            return round(float(_al['x'].corr(_al['y'])), 2)
                        except Exception:
                            return float('nan')
                    _corr_rows.append({
                        '지표': _nm,
                        '동기(r)':     _calc_r(_s),
                        '1M 선행(r)': _calc_r(_s, 21),
                        '3M 선행(r)': _calc_r(_s, 63),
                    })

                _corr_df = pd.DataFrame(_corr_rows).set_index('지표')

                def _style_r(v):
                    if not isinstance(v, (int, float)) or pd.isna(v): return 'color:#666'
                    if v >= 0.5:  return 'color:#4BFFB3;font-weight:600'
                    if v >= 0.3:  return 'color:#4BFFB3'
                    if v <= -0.5: return 'color:#FF4B6E;font-weight:600'
                    if v <= -0.3: return 'color:#FF4B6E'
                    return 'color:#AAAAAA'

                _styled_corr = (
                    _corr_df.style
                    .map(_style_r)
                    .format(lambda v: f'{v:+.2f}' if isinstance(v, float) and not pd.isna(v) else '—')
                )
                st.dataframe(_styled_corr, use_container_width=True)
            else:
                st.info("S&P500 오버레이를 체크해야 상관계수를 계산할 수 있습니다.")


if __name__ == "__main__":
    main()
