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
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf
import json
import os
import re
import sys
import time
import warnings
import traceback
warnings.filterwarnings('ignore')

try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
    _PYKRX_IMPORT_ERR = None
except Exception as _e:
    PYKRX_AVAILABLE = False
    pass

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False


# ============================================================
# 페이지 설정
# ============================================================
_IS_MARKET_MACRO_APP = any(
    os.path.basename(str(arg)) in ("market_macro_dashboard.py", "market_macro_dashboard2.py")
    for arg in sys.argv
)

st.set_page_config(
    page_title="시장/매크로 지표" if _IS_MARKET_MACRO_APP else "기술적 신호 스캐너",
    page_icon="🏔️" if _IS_MARKET_MACRO_APP else "🎯",
    layout="wide",
    initial_sidebar_state="collapsed" if _IS_MARKET_MACRO_APP else "expanded"
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
    [data-testid="stSidebarCollapseButton"]   { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
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
MACRO_DATA_DIR = os.path.join(_DIR, "macro_data")
CAPEX_FALLBACK_CSV = os.path.join(MACRO_DATA_DIR, "hyperscaler_capex_quarterly.csv")
MEMORY_PRICE_CSV = os.path.join(MACRO_DATA_DIR, "memory_price_qoq.csv")
MEMORY_PROFIT_CSV = os.path.join(MACRO_DATA_DIR, "memory_profit_quarterly.csv")
MACRO_BENCHMARKS = {
    "S&P500": {"code": "^GSPC", "label": "S&P500", "kind": "us"},
    "Nasdaq": {"code": "^IXIC", "label": "Nasdaq", "kind": "us"},
    "KOSPI": {"code": "^KS11", "label": "KOSPI", "kind": "kr"},
}

DEFAULT_FAVORITES = [
    {"code": "^KQ11",      "name": "코스닥 지수 (^KQ11)"},
    {"code": "^KS11",      "name": "코스피 지수 (^KS11)"},
    {"code": "373220.KS",  "name": "LG에너지솔루션 (373220)"},
    {"code": "000660.KS",  "name": "SK하이닉스 (000660)"},
    {"code": "005930.KS",  "name": "삼성전자 (005930)"},
    {"code": "442570.KS",  "name": "RISE TDF2050액티브 적격 (442570)"},
    {"code": "284430.KS",  "name": "KODEX 200미국채혼합 (284430)"},
    {"code": "0162Z0.KS",  "name": "RISE 삼성전자SK하이닉스채권혼합50 (0162Z0)"},
    {"code": "0025N0.KS",  "name": "TIGER TDF2045 적격 (0025N0)"},
    {"code": "0019K0.KS",  "name": "TIME 미국나스닥100채권혼합50액티브 (0019K0)"},
    {"code": "491010.KS",  "name": "TIGER 글로벌AI전력인프라액티브 (491010)"},
    {"code": "487240.KS",  "name": "KODEX AI전력핵심설비 (487240)"},
    {"code": "456600.KS",  "name": "TIME 글로벌AI인공지능액티브 (456600)"},
    {"code": "446770.KS",  "name": "ACE 글로벌반도체TOP4 Plus (446770)"},
    {"code": "441800.KS",  "name": "TIME Korea플러스배당액티브 (441800)"},
    {"code": "396500.KS",  "name": "TIGER Fn반도체TOP10 (396500)"},
    {"code": "091160.KS",  "name": "KODEX 반도체 (091160)"},
    {"code": "0173Y0.KS",  "name": "KODEX 미국AI광통신네트워크 (0173Y0)"},
    {"code": "0164G0.KS",  "name": "RISE 차이나AI반도체TOP4Plus (0164G0)"},
    {"code": "0041D0.KS",  "name": "KODEX 미국AI소프트웨어TOP10 (0041D0)"},
    {"code": "0195S0.KS",  "name": "TIGER SK하이닉스단일종목레버리지 (0195S0)"},
    {"code": "0195R0.KS",  "name": "TIGER 삼성전자단일종목레버리지 (0195R0)"},
]

STOCK_SEARCH_LIST = [
    # 주요 국내 ETF
    {"code": "069500.KS", "name": "KODEX 200"},
    {"code": "091160.KS", "name": "KODEX 반도체"},
    {"code": "396500.KS", "name": "TIGER Fn반도체TOP10"},
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
    {"code": "284430.KS", "name": "KODEX 200미국채혼합"},
    {"code": "0019K0.KS", "name": "TIME 미국나스닥100채권혼합50액티브"},
    {"code": "0025N0.KS", "name": "TIGER TDF2045 적격"},
    {"code": "0162Z0.KS", "name": "RISE 삼성전자SK하이닉스채권혼합50"},
    {"code": "442570.KS", "name": "RISE TDF2050액티브 적격"},
    {"code": "491010.KS", "name": "TIGER 글로벌AI전력인프라액티브"},
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
    "COIN","ZM","DOCU","OKTA","SOFI","AFRM","RIVN","LCID","HOOD",
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
    "4년":     1008,
    "6년":     1512,
    "8년":     2016,
    "10년":    2520,
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
        width: 260px !important; min-width: 260px !important;
        transform: translateX(0) !important;
        background: #111113 !important;
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


def _is_rate_limit_error(e):
    """yfinance Rate limit(429 Too Many Requests) 에러 여부 판별.
    감지되면 같은 루프에서 더 이상 개별 요청을 보내지 않아 429를 추가로
    유발하지 않도록 한다. 상장폐지 등 일반 오류는 False를 반환해
    해당 티커만 skip하고 나머지는 계속 진행한다.
    """
    return type(e).__name__ == 'YFRateLimitError' or 'Too Many Requests' in str(e) or 'Rate limit' in str(e)


@st.cache_data(ttl=180)
def fetch_ohlcv(ticker, start_str, end_str, interval="1d"):
    """단일 종목 OHLCV (BB·RSI 차트용)"""
    try:
        raw = yf.download(ticker, start=start_str, end=end_str, interval=interval, progress=False)
        df = _normalize_yf_ohlcv(raw)
        if df.empty:
            return pd.DataFrame()
        cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        return df[cols].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=180)
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
            except Exception as e:
                # rate limit이면 나머지 티커 개별 요청을 멈춤 (429 추가 유발 방지)
                if _is_rate_limit_error(e):
                    break
                # 그 외(상장폐지 등 단일 티커 오류)는 이 티커만 skip하고 계속

    if not result.empty:
        result.index = _strip_tz(result.index)
    return result


@st.cache_data(ttl=180, max_entries=10)
def fetch_ohlcv_batch(tickers_tuple, start_str, end_str, interval="1d"):
    """다중 종목 OHLCV 일괄 다운로드 → (closes, highs, lows) 반환. fetch_close_batch와 동일한 단일 요청."""
    tickers = list(tickers_tuple)
    if not tickers:
        empty = pd.DataFrame()
        return empty, empty, empty

    closes = highs = lows = pd.DataFrame()

    def _pick(raw, field):
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                l0 = set(raw.columns.get_level_values(0))
                if l0 & _OHLCV_FIELDS:
                    block = raw.get(field, pd.DataFrame())
                    if isinstance(block, pd.Series):
                        return pd.DataFrame({tickers[0]: block}) if len(tickers) == 1 else pd.DataFrame()
                    return block[[t for t in tickers if t in block.columns]]
                else:
                    res = {}
                    for t in tickers:
                        try:
                            b = raw[t]
                            res[t] = b[field] if isinstance(b, pd.DataFrame) and field in b.columns else pd.Series(dtype=float)
                        except Exception:
                            pass
                    return pd.DataFrame(res)
            elif field in raw.columns and len(tickers) == 1:
                s = raw[field]
                return pd.DataFrame({tickers[0]: s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s})
        except Exception:
            pass
        return pd.DataFrame()

    try:
        raw = yf.download(tickers, start=start_str, end=end_str,
                          interval=interval, progress=False, group_by='ticker', threads=False)
        closes = _pick(raw, 'Close')
        highs  = _pick(raw, 'High')
        lows   = _pick(raw, 'Low')
    except Exception:
        pass

    # 배치 누락 개별 보완
    for t in tickers:
        if t not in closes.columns or closes[t].isna().all():
            try:
                raw = yf.download(t, start=start_str, end=end_str, interval=interval, progress=False)
                df = _normalize_yf_ohlcv(raw)
                if not df.empty:
                    if 'Close' in df.columns: closes[t] = df['Close']
                    if 'High'  in df.columns: highs[t]  = df['High']
                    if 'Low'   in df.columns: lows[t]   = df['Low']
            except Exception as e:
                # rate limit이면 나머지 티커 개별 요청을 멈춤 (429 추가 유발 방지)
                if _is_rate_limit_error(e):
                    break
                # 그 외(상장폐지 등 단일 티커 오류)는 이 티커만 skip하고 계속

    for df in [closes, highs, lows]:
        if not df.empty:
            df.index = _strip_tz(df.index)

    return closes, highs, lows


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

@st.cache_data(ttl=82800)
def _kis_token():
    """KIS OAuth 토큰 발급 (23시간 캐시). 실패/미설정 시 None 반환."""
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
        if rows:
            all_bars.extend(rows)
        if not all_bars:
            return pd.DataFrame()
        today = _now_kst.strftime("%Y%m%d")
        df = pd.DataFrame(all_bars)
        date_col = "stck_bsop_date" if "stck_bsop_date" in df.columns else None
        df["_dt"] = pd.to_datetime(
            (df[date_col] if date_col else today) + df["stck_cntg_hour"],
            format="%Y%m%d%H%M%S")
        df = (df.set_index("_dt")
                .rename(columns={"stck_oprc": "Open", "stck_hgpr": "High",
                                 "stck_lwpr": "Low",  "stck_prpr": "Close",
                                 "cntg_vol":  "Volume"})
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
            # 거래시간(09:00~15:30) 외 봉 제거
            if not _kis_1m.empty:
                _h = _kis_1m.index.hour
                _m = _kis_1m.index.minute
                _kis_1m = _kis_1m[(_h > 8) & ((_h < 15) | ((_h == 15) & (_m <= 30)))]
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
        # yfinance 아티팩트(자정 봉 등) + 장외 봉 최종 제거
        _h2 = df_hist.index.hour
        _m2 = df_hist.index.minute
        df_hist = df_hist[(_h2 > 8) & ((_h2 < 15) | ((_h2 == 15) & (_m2 <= 30)))]

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


def get_current_signals(close, high=None, low=None, bb_window=20, bb_std=2.0, rsi_period=14,
                        rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                        rsi_lookback=60, persist=2, phase2_rsi=False):
    """
    현재(오늘) 신호 계산 (스캔 테이블용).
    high/low 미전달 시 close 대용 (분봉 배치 스캔).

    반환:
      dyn_buy/sell  : 동적 RSI(±0) + BB 파쿠르 확정 신호
      band_buy/sell : 고정 RSI 밴드(±5) + BB 파쿠르 확정 신호
    """
    close = close.dropna()
    if len(close) < bb_window + rsi_period + rsi_lookback // 2:
        return None

    _high = high.reindex(close.index).fillna(close) if high is not None else close
    _low  = low.reindex(close.index).fillna(close)  if low  is not None else close

    sma, upper, lower = calculate_bb(close, bb_window, bb_std)
    rsi = calculate_rsi(close, rsi_period)
    dyn_lower, dyn_upper = calculate_dynamic_rsi_thresholds(rsi, rsi_lookback)

    # 동적 파쿠르: rsi_band=0 (동적 퍼센타일 자체가 임계값)
    dyn_of, dyn_buy, dyn_oh, dyn_sell = calculate_parkour_signals(
        close, _high, _low, upper, lower, rsi,
        dyn_lower, dyn_upper, rsi_band=0, persist=persist, phase2_rsi=phase2_rsi,
    )
    # 밴드+BB (B안): Phase1=BB터치+RSI극단, Phase2=RSI회복 (persist 없음)
    band_of, band_buy, band_oh, band_sell = calculate_band_signals(
        close, _high, _low, upper, lower, rsi,
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

    # 동적 RSI 파쿠르 확정
    dyn_buy_idx  = disp[dyn_buy[disp].values]
    dyn_sell_idx = disp[dyn_sell[disp].values]

    # 고정 밴드 RSI 파쿠르 확정
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
    # BB 밴드 채움용 (hover 없음 - 순서 유지 필요)
    fig.add_trace(go.Scatter(x=disp, y=upper[disp],
        line=dict(color="rgba(120,126,231,0.2)", width=1),
        showlegend=False, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=lower[disp],
        line=dict(color="rgba(120,126,231,0.2)", width=1),
        fill='tonexty', fillcolor="rgba(120,126,231,0.04)",
        showlegend=False, hoverinfo='skip'), row=1, col=1)
    # hover 트레이스: 추가 순서 = 툴팁 표시 순서 (종가 → SMA20 → BB상단 → BB하단)
    fig.add_trace(go.Scatter(x=disp, y=close[disp],
        name=name, line=dict(color="#EDEDED", width=1.5),
        hovertemplate="종가: %{y:,.0f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=sma[disp],
        line=dict(color="rgba(120,126,231,0.4)", width=1, dash='dot'),
        showlegend=False, name="SMA20",
        hovertemplate="SMA20: %{y:,.0f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=upper[disp],
        line=dict(color="rgba(120,126,231,0.3)", width=0),
        showlegend=False, name="BB상단",
        hovertemplate="BB상단: %{y:,.0f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=disp, y=lower[disp],
        line=dict(color="rgba(120,126,231,0.3)", width=0),
        showlegend=False, name="BB하단",
        hovertemplate="BB하단: %{y:,.0f}<extra></extra>"), row=1, col=1)

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
            name=_label, hoverinfo='skip'), row=1, col=1)

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


@st.cache_data(ttl=3600, max_entries=4)
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


_CREDIT_SPREAD_PROXY_MAP = {
    'BAMLH0A0HYM2': ('DBAA', 'DGS10', 'HY'),
    'BAMLC0A0CM': ('DAAA', 'DGS10', 'IG'),
}


@st.cache_data(ttl=86400)
def _credit_spread_series(series_id: str, years: int = 5) -> pd.Series:
    """HY/IG OAS는 최근 3년 원본 + 이전 구간은 장기 프록시로 이어 붙여 반환."""
    exact = _fred(series_id, years)
    proxy_meta = _CREDIT_SPREAD_PROXY_MAP.get(series_id)
    if proxy_meta is None:
        return exact

    corp_id, treasury_id, label = proxy_meta
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    fetch_years = max(years + 2, 6)
    corp_yield = _fred(corp_id, fetch_years)
    treasury_yield = _fred(treasury_id, fetch_years)
    if corp_yield.empty or treasury_yield.empty:
        return exact

    treasury_aligned = treasury_yield.reindex(corp_yield.index).interpolate(method='time').ffill().bfill()
    proxy = (corp_yield - treasury_aligned).dropna()
    proxy.name = f'{label}_proxy_spread'
    if proxy.empty:
        return exact

    if exact.empty:
        return proxy[proxy.index >= cutoff]

    overlap = pd.concat(
        [exact.rename('exact'), proxy.rename('proxy')],
        axis=1,
        join='inner',
    ).dropna()
    shift = (overlap['exact'] - overlap['proxy']).median() if len(overlap) >= 20 else 0.0
    proxy_adjusted = proxy + shift
    older_proxy = proxy_adjusted[proxy_adjusted.index < exact.index.min()]
    stitched = pd.concat([older_proxy, exact]).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep='last')]
    stitched.name = series_id
    return stitched[stitched.index >= cutoff]


@st.cache_data(ttl=86400)
def _yf_close(ticker: str, years: int = 5) -> pd.Series:
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime('%Y-%m-%d')

    def _extract_close(raw_obj):
        df = _normalize_yf_ohlcv(raw_obj)
        if df is None or df.empty or 'Close' not in df.columns:
            return pd.Series(dtype=float)
        return df['Close'].dropna()

    fetchers = [
        lambda: yf.download(ticker, start=start, progress=False, threads=False, auto_adjust=False),
        lambda: yf.Ticker(ticker).history(start=start, auto_adjust=False),
    ]

    for fetcher in fetchers:
        for _ in range(2):
            try:
                series = _extract_close(fetcher())
                if not series.empty:
                    return series
            except Exception:
                pass
            time.sleep(0.6)
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


def _ensure_macro_data_templates():
    """자동 수집이 어려운 매크로 보조 데이터용 CSV 템플릿을 만든다."""
    os.makedirs(MACRO_DATA_DIR, exist_ok=True)
    templates = {
        CAPEX_FALLBACK_CSV: "quarter,company,capex_bil_usd,source\n",
        MEMORY_PRICE_CSV: "quarter,dram_contract_qoq,nand_contract_qoq,dram_spot_qoq,nand_spot_qoq,source\n",
        MEMORY_PROFIT_CSV: "quarter,samsung_ds_op,sk_hynix_op,source\n",
    }
    for path, header in templates.items():
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(header)


def _quarter_to_timestamp(value):
    try:
        txt = str(value).strip().upper().replace(" ", "").replace("/", "")
        txt = txt.replace("-Q", "Q").replace("_Q", "Q")
        return pd.Period(txt, freq="Q").to_timestamp(how="end").normalize()
    except Exception:
        return pd.NaT


def _quarter_timestamp_to_label(idx) -> str:
    try:
        p = pd.Timestamp(idx).to_period("Q")
        return f"{p.year}Q{p.quarter}"
    except Exception:
        return str(idx)


def _load_quarterly_csv(path: str, required_cols: list[str]) -> pd.DataFrame:
    _ensure_macro_data_templates()
    if not os.path.exists(path):
        return pd.DataFrame(columns=required_cols)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=required_cols)
    if df.empty or any(col not in df.columns for col in required_cols):
        return pd.DataFrame(columns=required_cols)
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame(columns=required_cols)
    df["quarter_ts"] = df["quarter"].map(_quarter_to_timestamp)
    df = df.dropna(subset=["quarter_ts"]).sort_values("quarter_ts")
    return df


@st.cache_data(ttl=86400)
def _fetch_quarterly_capex_yf(ticker: str) -> pd.Series:
    """yfinance quarterly cashflow에서 CAPEX 계열 항목을 찾아 billion USD로 반환."""
    try:
        tk = yf.Ticker(ticker)
        raw = getattr(tk, "quarterly_cashflow", pd.DataFrame())
        if raw is None or raw.empty:
            raw = getattr(tk, "quarterly_cash_flow", pd.DataFrame())
        if raw is None or raw.empty:
            return pd.Series(dtype=float)

        idx_map = {str(idx).strip().lower(): idx for idx in raw.index}
        candidates = [
            "capital expenditure",
            "capital expenditures",
            "purchase of ppe",
            "property plant equipment",
            "payments to acquire property plant and equipment",
            "payments to acquire productive assets",
            "property plant and equipment additions",
        ]
        row_key = None
        for cand in candidates:
            for idx_lower, original_idx in idx_map.items():
                if cand in idx_lower:
                    row_key = original_idx
                    break
            if row_key is not None:
                break
        if row_key is None:
            return pd.Series(dtype=float)

        s = raw.loc[row_key].astype(float).dropna()
        if s.empty:
            return pd.Series(dtype=float)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        s = s.abs() / 1e9
        s.name = ticker
        return s
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=86400)
def _get_hyperscaler_capex_frame() -> pd.DataFrame:
    """Google/Microsoft/Meta/Amazon 분기 CAPEX를 wide frame으로 반환."""
    _ensure_macro_data_templates()
    companies = {
        "GOOGL": "Google / Alphabet",
        "MSFT": "Microsoft",
        "META": "Meta",
        "AMZN": "Amazon",
    }
    auto = {}
    for ticker, label in companies.items():
        s = _fetch_quarterly_capex_yf(ticker)
        if not s.empty:
            s.index = pd.to_datetime(s.index)
            s.name = label
            auto[label] = s
    auto_df = pd.DataFrame(auto).sort_index() if auto else pd.DataFrame()

    fallback = _load_quarterly_csv(CAPEX_FALLBACK_CSV, ["quarter", "company", "capex_bil_usd", "source"])
    if not fallback.empty:
        fallback["capex_bil_usd"] = pd.to_numeric(fallback["capex_bil_usd"], errors="coerce")
        pivot = (
            fallback.dropna(subset=["capex_bil_usd"])
            .pivot_table(index="quarter_ts", columns="company", values="capex_bil_usd", aggfunc="last")
            .sort_index()
        )
        if auto_df.empty:
            auto_df = pivot
        else:
            auto_df = auto_df.combine_first(pivot)
            auto_df.update(pivot)

    if auto_df.empty:
        return pd.DataFrame()

    auto_df.index.name = "quarter_ts"
    auto_df["Total CAPEX"] = auto_df.sum(axis=1, min_count=1)
    return auto_df.sort_index()


def _macro_placeholder_chart(title: str, message: str, height: int = 300):
    fig = go.Figure()
    fig.update_layout(**_ml(title, height=height))
    fig.add_annotation(
        text=message,
        x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=12, color="#666"),
    )
    return fig


def _load_memory_price_frame() -> pd.DataFrame:
    df = _load_quarterly_csv(
        MEMORY_PRICE_CSV,
        ["quarter", "dram_contract_qoq", "nand_contract_qoq", "dram_spot_qoq", "nand_spot_qoq", "source"],
    )
    if df.empty:
        return df
    numeric_cols = ["dram_contract_qoq", "nand_contract_qoq", "dram_spot_qoq", "nand_spot_qoq"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("quarter_ts")


def _load_memory_profit_frame() -> pd.DataFrame:
    df = _load_quarterly_csv(
        MEMORY_PROFIT_CSV,
        ["quarter", "samsung_ds_op", "sk_hynix_op", "source"],
    )
    if df.empty:
        return df
    for col in ["samsung_ds_op", "sk_hynix_op"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("quarter_ts")


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
                line=dict(color='rgba(200,200,80,0.45)', width=1.0),
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
            x=0, y=1, xref='paper', yref='paper',
            xanchor='left', yanchor='top',
            text=f'r = {r:+.2f} ({label})',
            showarrow=False,
            font=dict(size=9, color=color),
            bgcolor='rgba(14,14,17,0.80)',
            bordercolor=color, borderwidth=1, borderpad=3,
        )
    except Exception:
        pass


def _visible_price_yaxis(overlaying='y', side='right') -> dict:
    """가격 오버레이용 우측 y축."""
    return dict(
        overlaying=overlaying,
        side=side,
        showgrid=False,
        showticklabels=True,
        showline=True,
        linecolor='rgba(180, 180, 180, 0.35)',
        tickfont=dict(size=9, color='rgba(200, 200, 200, 0.82)'),
        zeroline=False,
        tickformat=',.0f',
    )


def _get_macro_benchmark(benchmark_name: str | None):
    return MACRO_BENCHMARKS.get(benchmark_name or "S&P500", MACRO_BENCHMARKS["S&P500"])


def _realized_volatility(price_s: pd.Series, window: int = 20) -> pd.Series:
    if price_s is None or price_s.empty:
        return pd.Series(dtype=float)
    ret = price_s.pct_change()
    return (ret.rolling(window, min_periods=max(5, window // 2)).std() * (252 ** 0.5) * 100).dropna()


def _relative_strength_spread(leader_s: pd.Series, lagger_s: pd.Series) -> pd.Series:
    if leader_s is None or leader_s.empty or lagger_s is None or lagger_s.empty:
        return pd.Series(dtype=float)
    aligned = pd.concat([leader_s.rename('leader'), lagger_s.rename('lagger')], axis=1).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)
    leader_norm = aligned['leader'] / aligned['leader'].iloc[0] * 100
    lagger_norm = aligned['lagger'] / aligned['lagger'].iloc[0] * 100
    return (leader_norm - lagger_norm).dropna()


def _korean_credit_proxy_series(years: int, quality: str = 'AA') -> pd.Series:
    treasury_3y = _yf_close('114260.KS', years + 1)   # KODEX 국고채3년
    corp_map = {
        'AA': ('273130.KS', '종합채권(AA-이상)'),
        'A': ('385540.KS', '종합채권(A-이상)'),
    }
    corp_ticker, _ = corp_map.get(quality, corp_map['AA'])
    corp = _yf_close(corp_ticker, years + 1)
    return _relative_strength_spread(treasury_3y, corp)


def _korean_fx_stress_series(years: int) -> pd.Series:
    return _yf_close('KRW=X', years + 1)


def _korean_volatility_series(years: int, benchmark_s: pd.Series | None = None, window: int = 20) -> pd.Series:
    if benchmark_s is None or benchmark_s.empty:
        benchmark_s = _yf_close('^KS11', years + 1)
    return _realized_volatility(benchmark_s, window=window)


def _korean_vol_term_spread_series(years: int, benchmark_s: pd.Series | None = None) -> pd.Series:
    if benchmark_s is None or benchmark_s.empty:
        benchmark_s = _yf_close('^KS11', years + 1)
    hv20 = _realized_volatility(benchmark_s, window=20)
    hv60 = _realized_volatility(benchmark_s, window=60)
    return (hv20 - hv60.reindex(hv20.index)).dropna()


def _korean_yield_curve_proxy_bundle(years: int):
    bond_3y = _yf_close('114260.KS', years + 1)   # KODEX 국고채3년
    bond_10y = _yf_close('148070.KS', years + 1)  # KIWOOM 국고채10년
    spread = _relative_strength_spread(bond_3y, bond_10y)
    return spread, bond_3y, bond_10y


def _add_spx_overlay(fig, main_s: pd.Series, spx_s, yaxis='y2', label='S&P500'):
    """기준 지수 실제 값 우측 축 오버레이."""
    if spx_s is None or spx_s.empty or main_s is None or main_s.empty:
        return
    t0 = main_s.index[0]
    spx_t = spx_s[spx_s.index >= t0]
    if len(spx_t) <= 2:
        return
    fig.add_trace(go.Scatter(
        x=spx_t.index, y=spx_t, name=label,
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        showlegend=True, hoverinfo='skip', yaxis=yaxis,
    ))


def _add_price_signal_markers(fig, signal_df: pd.DataFrame, price_s: pd.Series, yaxis='y2', prefix='Risk-off'):
    """신호 마커를 가격 오버레이 축 위에 표시한다."""
    if signal_df is None or signal_df.empty or price_s is None or price_s.empty:
        return

    def _signal_price_points(mask_col: str) -> pd.Series:
        sig_idx = signal_df.index[signal_df[mask_col].fillna(False)]
        if len(sig_idx) == 0:
            return pd.Series(dtype=float)
        exact = price_s.reindex(sig_idx)
        if exact.notna().any():
            return exact.dropna()
        try:
            nearest = price_s.reindex(sig_idx, method='nearest', tolerance=pd.Timedelta('7D'))
            return nearest.dropna()
        except Exception:
            return pd.Series(dtype=float)

    start_y = _signal_price_points('down_start_signal')
    end_y = _signal_price_points('down_end_signal')
    if not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name=f'{prefix} 시작',
            mode='markers', yaxis=yaxis,
            marker=dict(symbol='triangle-down', size=9, color='rgba(255,140,105,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Risk-off 시작<extra></extra>',
        ))
    if not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name=f'{prefix} 종료',
            mode='markers', yaxis=yaxis,
            marker=dict(symbol='triangle-up', size=9, color='rgba(75,255,179,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Risk-off 종료<extra></extra>',
        ))


_DEFAULT_DOWNTURN_PARAMS = {
    'ema_span': 20,
    'std_window': 40,
    'ema_compare_days': 10,
    'start_count': 4,
    'end_count': 3,
}


def _resolve_downturn_params(params=None) -> dict:
    merged = _DEFAULT_DOWNTURN_PARAMS.copy()
    if params:
        merged.update(params)
    return merged


def _compute_downturn_signal_frame(s: pd.Series, params=None) -> pd.DataFrame:
    """단일 지표의 Risk-off 사이클 상태를 계산한다."""
    if s is None or s.empty:
        return pd.DataFrame()
    params = _resolve_downturn_params(params)
    ema_span = int(params['ema_span'])
    std_window = int(params['std_window'])
    ema_compare_days = int(params['ema_compare_days'])
    start_count = int(params['start_count'])
    end_count = int(params['end_count'])

    ema_col = f'ema{ema_span}'
    slope_col = f'{ema_col}_slope'

    ema_s = s.ewm(span=ema_span, adjust=False, min_periods=5).mean().dropna()
    aligned = pd.concat([s.rename('value'), ema_s.rename(ema_col)], axis=1).dropna()
    if len(aligned) < 50:
        return pd.DataFrame()

    slope = aligned[ema_col].diff()
    threshold = 0.5 * slope.rolling(std_window, min_periods=max(5, std_window // 2)).std()
    down_count = slope.lt(-threshold).rolling(5, min_periods=5).sum()
    up_count = slope.gt(threshold).rolling(5, min_periods=5).sum()
    ema_vs_prev = aligned[ema_col] - aligned[ema_col].shift(ema_compare_days)

    out = aligned.copy()
    out[slope_col] = slope
    out['threshold'] = threshold
    out['down_count'] = down_count
    out['up_count'] = up_count
    out['start_ready'] = down_count.ge(start_count) & ema_vs_prev.lt(0)
    out['end_ready'] = up_count.ge(end_count) & ema_vs_prev.gt(0)
    out['down_flag'] = False
    out['down_start_signal'] = False
    out['down_end_signal'] = False

    risk_off = False
    for idx in out.index:
        if not risk_off and bool(out.at[idx, 'start_ready']):
            risk_off = True
            out.at[idx, 'down_start_signal'] = True
        elif risk_off and bool(out.at[idx, 'end_ready']):
            risk_off = False
            out.at[idx, 'down_end_signal'] = True
        out.at[idx, 'down_flag'] = risk_off
    return out


def _compute_threshold_ema_signal_frame(s: pd.Series, ema_span: int = 20, threshold: float = 0.0) -> pd.DataFrame:
    """EMA가 지정 threshold 아래로 내려가면 시작, 위로 올라오면 종료."""
    if s is None or s.empty:
        return pd.DataFrame()

    ema_col = f'ema{int(ema_span)}'
    ema_s = s.ewm(span=int(ema_span), adjust=False, min_periods=max(3, int(ema_span) // 2)).mean().dropna()
    out = pd.concat([s.rename('value'), ema_s.rename(ema_col)], axis=1).dropna()
    if len(out) < max(10, ema_span):
        return pd.DataFrame()

    below = out[ema_col] < threshold
    above = out[ema_col] > threshold
    start_signal = below & ~below.shift(1).fillna(False)
    end_signal = above & ~above.shift(1).fillna(False)

    out['down_flag'] = False
    out['down_start_signal'] = False
    out['down_end_signal'] = False

    in_cycle = False
    for idx in out.index:
        if not in_cycle and bool(start_signal.loc[idx]):
            in_cycle = True
            out.at[idx, 'down_start_signal'] = True
        elif in_cycle and bool(end_signal.loc[idx]):
            in_cycle = False
            out.at[idx, 'down_end_signal'] = True
        out.at[idx, 'down_flag'] = in_cycle
    return out


def _add_ema20_downturn_signals(fig, s: pd.Series, show_downturn=True, overlay_price=None, overlay_yaxis='y2', params=None):
    """EMA 기반 Risk-off 시작/종료 이벤트를 추가."""
    params = _resolve_downturn_params(params)
    ema_span = int(params['ema_span'])
    std_window = int(params['std_window'])
    ema_compare_days = int(params['ema_compare_days'])
    start_count = int(params['start_count'])
    end_count = int(params['end_count'])
    ema_col = f'ema{ema_span}'

    signal_df = _compute_downturn_signal_frame(s, params=params)
    if signal_df.empty:
        return

    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df[ema_col], name=f'EMA{ema_span}',
        line=dict(color='rgba(255,255,255,0.28)', width=1.0, dash='dot'),
        hoverinfo='skip',
    ))
    if not show_downturn:
        return

    if overlay_price is not None and not overlay_price.empty:
        _add_price_signal_markers(fig, signal_df, overlay_price, yaxis=overlay_yaxis)
        return

    sig1_start = signal_df.loc[signal_df['down_start_signal'], ema_col]
    sig1_end = signal_df.loc[signal_df['down_end_signal'], ema_col]

    if not sig1_start.empty:
        fig.add_trace(go.Scatter(
            x=sig1_start.index, y=sig1_start, name=f'1: Risk-off 시작 ({start_count}/5 하락 + EMA{ema_span}<{ema_compare_days}D전)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=8, color='rgba(255,140,105,0.80)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>최근 5일 중 slope < -0.5*{std_window}일 std 가 {start_count}일 이상<br>현재 EMA{ema_span} < {ema_compare_days}일 전 EMA{ema_span}<extra></extra>',
        ))
    if not sig1_end.empty:
        fig.add_trace(go.Scatter(
            x=sig1_end.index, y=sig1_end, name=f'1: Risk-off 종료 ({end_count}/5 상승 + EMA{ema_span}>{ema_compare_days}D전)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=8, color='rgba(75,255,179,0.80)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>최근 5일 중 slope > +0.5*{std_window}일 std 가 {end_count}일 이상<br>현재 EMA{ema_span} > {ema_compare_days}일 전 EMA{ema_span}<extra></extra>',
        ))


def _add_threshold_ema_signals(fig, s: pd.Series, threshold: float, ema_span: int = 20,
                               overlay_price=None, overlay_yaxis='y2', prefix='Risk-off'):
    signal_df = _compute_threshold_ema_signal_frame(s, ema_span=ema_span, threshold=threshold)
    if signal_df.empty:
        return

    ema_col = f'ema{int(ema_span)}'
    fig.add_hline(y=threshold, line=dict(color='rgba(255,255,255,0.16)', width=1, dash='dot'))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df[ema_col], name=f'EMA{ema_span}',
        line=dict(color='rgba(255,255,255,0.28)', width=1.0, dash='dot'),
        hoverinfo='skip',
    ))
    if overlay_price is not None and not overlay_price.empty:
        _add_price_signal_markers(fig, signal_df, overlay_price, yaxis=overlay_yaxis, prefix=prefix)
    else:
        sig_start = signal_df.loc[signal_df['down_start_signal'], ema_col]
        sig_end = signal_df.loc[signal_df['down_end_signal'], ema_col]
        if not sig_start.empty:
            fig.add_trace(go.Scatter(
                x=sig_start.index, y=sig_start, name=f'{prefix} 시작',
                mode='markers',
                marker=dict(symbol='triangle-down', size=8, color='rgba(255,140,105,0.85)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(75,255,179,0.85)'),
            ))


def _compute_dual_threshold_ema_signal_frame(
    s: pd.Series,
    ema_span: int = 20,
    start_threshold: float = 0.5,
    end_threshold: float = -0.5,
) -> pd.DataFrame:
    """EMA가 시작 threshold 아래로 하향 돌파하면 시작, 종료 threshold 위로 상향 돌파하면 종료."""
    if s is None or s.empty:
        return pd.DataFrame()

    ema_col = f'ema{int(ema_span)}'
    ema_s = s.ewm(span=int(ema_span), adjust=False, min_periods=max(3, int(ema_span) // 2)).mean().dropna()
    out = pd.concat([s.rename('value'), ema_s.rename(ema_col)], axis=1).dropna()
    if len(out) < max(10, ema_span):
        return pd.DataFrame()

    out['down_flag'] = False
    out['down_start_signal'] = False
    out['down_end_signal'] = False

    in_cycle = False
    for idx in out.index:
        loc = out.index.get_loc(idx)
        ema_value = float(out.at[idx, ema_col])
        prev_ema = float(out.iloc[loc - 1][ema_col]) if loc > 0 else np.nan
        start_cross = loc > 0 and prev_ema >= float(start_threshold) and ema_value <= float(start_threshold)
        end_cross = loc > 0 and prev_ema <= float(end_threshold) and ema_value >= float(end_threshold)

        if not in_cycle and start_cross:
            in_cycle = True
            out.at[idx, 'down_start_signal'] = True
        elif in_cycle and end_cross:
            in_cycle = False
            out.at[idx, 'down_end_signal'] = True
        out.at[idx, 'down_flag'] = in_cycle
    return out


def _add_dual_threshold_ema_signals(
    fig,
    s: pd.Series,
    start_threshold: float,
    end_threshold: float,
    ema_span: int = 20,
    overlay_price=None,
    overlay_yaxis='y2',
    prefix='Risk-off',
):
    signal_df = _compute_dual_threshold_ema_signal_frame(
        s,
        ema_span=ema_span,
        start_threshold=start_threshold,
        end_threshold=end_threshold,
    )
    if signal_df.empty:
        return

    ema_col = f'ema{int(ema_span)}'
    fig.add_hline(y=float(start_threshold), line=dict(color='rgba(255,140,105,0.30)', width=1, dash='dot'))
    fig.add_hline(y=float(end_threshold), line=dict(color='rgba(75,255,179,0.30)', width=1, dash='dot'))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df[ema_col], name=f'EMA{ema_span}',
        line=dict(color='rgba(255,255,255,0.28)', width=1.0, dash='dot'),
        hoverinfo='skip',
    ))
    if overlay_price is not None and not overlay_price.empty:
        _add_price_signal_markers(fig, signal_df, overlay_price, yaxis=overlay_yaxis, prefix=prefix)
    else:
        sig_start = signal_df.loc[signal_df['down_start_signal'], ema_col]
        sig_end = signal_df.loc[signal_df['down_end_signal'], ema_col]
        if not sig_start.empty:
            fig.add_trace(go.Scatter(
                x=sig_start.index, y=sig_start, name=f'{prefix} 시작',
                mode='markers',
                marker=dict(symbol='triangle-down', size=8, color='rgba(255,140,105,0.85)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(75,255,179,0.85)'),
            ))


def _compute_dynamic_quantile_signal_frame(
    s: pd.Series,
    window: int = 126,
    start_quantile: float = 0.4,
    end_quantile: float = 0.2,
    ema_span: int = 20,
) -> pd.DataFrame:
    """동적 분위수 라인 기반 Risk-off 사이클 상태를 계산한다."""
    if s is None or s.empty:
        return pd.DataFrame()

    ema_col = f'ema{int(ema_span)}'
    out = pd.DataFrame({'value': s}).dropna()
    out[ema_col] = out['value'].ewm(
        span=int(ema_span),
        adjust=False,
        min_periods=max(3, int(ema_span) // 2),
    ).mean()
    out = out.dropna().copy()
    if len(out) < max(30, int(window) // 2):
        return pd.DataFrame()

    out['risk_start_line'] = (
        out[ema_col]
        .rolling(int(window), min_periods=max(20, int(window) // 2))
        .quantile(float(start_quantile))
        .shift(1)
    )
    out['risk_end_line'] = (
        out[ema_col]
        .rolling(int(window), min_periods=max(20, int(window) // 2))
        .quantile(float(end_quantile))
        .shift(1)
    )
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()

    out['down_flag'] = False
    out['down_start_signal'] = False
    out['down_end_signal'] = False

    in_cycle = False
    for idx in out.index:
        loc = out.index.get_loc(idx)
        ema_value = float(out.at[idx, ema_col])
        start_line = float(out.at[idx, 'risk_start_line'])
        end_line = float(out.at[idx, 'risk_end_line'])
        prev_ema = float(out.iloc[loc - 1][ema_col]) if loc > 0 else np.nan
        prev_start_line = float(out.iloc[loc - 1]['risk_start_line']) if loc > 0 else np.nan
        prev_end_line = float(out.iloc[loc - 1]['risk_end_line']) if loc > 0 else np.nan

        start_cross = (
            loc > 0
            and pd.notna(prev_ema)
            and pd.notna(prev_start_line)
            and prev_ema >= prev_start_line
            and ema_value < start_line
        )
        end_cross = (
            loc > 0
            and pd.notna(prev_ema)
            and pd.notna(prev_end_line)
            and prev_ema <= prev_end_line
            and ema_value > end_line
        )

        if not in_cycle and start_cross:
            in_cycle = True
            out.at[idx, 'down_start_signal'] = True
        elif in_cycle and end_cross:
            in_cycle = False
            out.at[idx, 'down_end_signal'] = True
        out.at[idx, 'down_flag'] = in_cycle
    return out


def _add_dynamic_quantile_signals(
    fig,
    s: pd.Series,
    window: int = 126,
    start_quantile: float = 0.4,
    end_quantile: float = 0.2,
    ema_span: int = 20,
    overlay_price=None,
    overlay_yaxis='y2',
    prefix='Risk-off',
):
    signal_df = _compute_dynamic_quantile_signal_frame(
        s,
        window=window,
        start_quantile=start_quantile,
        end_quantile=end_quantile,
        ema_span=ema_span,
    )
    if signal_df.empty:
        return

    ema_col = f'ema{int(ema_span)}'
    start_pct = int(round(float(start_quantile) * 100))
    end_pct = int(round(float(end_quantile) * 100))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df[ema_col],
        name=f'EMA{int(ema_span)}',
        line=dict(color='rgba(255,255,255,0.32)', width=1.1, dash='dot'),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>EMA{int(ema_span)}  %{{y:.2f}}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df['risk_start_line'],
        name=f'시작선 Q{start_pct}',
        line=dict(color='rgba(255,140,105,0.55)', width=1.2, dash='dot'),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>Risk 시작선 (Q{start_pct})  %{{y:.2f}}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df['risk_end_line'],
        name=f'종료선 Q{end_pct}',
        line=dict(color='rgba(75,255,179,0.55)', width=1.2, dash='dot'),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>Risk 종료선 (Q{end_pct})  %{{y:.2f}}<extra></extra>',
    ))
    if overlay_price is not None and not overlay_price.empty:
        _add_price_signal_markers(fig, signal_df, overlay_price, yaxis=overlay_yaxis, prefix=prefix)
    else:
        sig_start = signal_df.loc[signal_df['down_start_signal'], 'value']
        sig_end = signal_df.loc[signal_df['down_end_signal'], 'value']
        if not sig_start.empty:
            fig.add_trace(go.Scatter(
                x=sig_start.index, y=sig_start, name=f'{prefix} 시작',
                mode='markers',
                marker=dict(symbol='triangle-down', size=8, color='rgba(255,140,105,0.85)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(75,255,179,0.85)'),
            ))


def _compute_combo_downturn_frame(parts: dict[str, pd.Series], params=None) -> pd.DataFrame:
    """0~4 개별 Risk-off 상태를 합성한 종합 하락 사이클 상태를 계산한다."""
    frames = {}
    for name, series in parts.items():
        sig = _compute_downturn_signal_frame(series, params=params)
        if sig.empty:
            continue
        frames[name] = sig[['down_flag', 'down_start_signal', 'down_end_signal']].rename(columns={
            'down_flag': f'{name}_down_flag',
            'down_start_signal': f'{name}_down_start_signal',
            'down_end_signal': f'{name}_down_end_signal',
        })
    if len(frames) < 4:
        return pd.DataFrame()

    combo = pd.concat(frames.values(), axis=1).sort_index().fillna(False)
    flag_cols = [f'{name}_down_flag' for name in frames]
    combo['active_down_count'] = combo[flag_cols].sum(axis=1).astype(int)
    combo['combo_watch_state'] = False
    combo['combo_watch_start_signal'] = False
    combo['combo_watch_end_signal'] = False
    combo['combo_risk_state'] = False
    combo['combo_risk_start_signal'] = False
    combo['combo_risk_end_signal'] = False

    watch_state = False
    risk_state = False
    for idx in combo.index:
        active_count = int(combo.at[idx, 'active_down_count'])
        if not watch_state and active_count >= 3:
            watch_state = True
            combo.at[idx, 'combo_watch_start_signal'] = True
        elif watch_state and active_count <= 2:
            watch_state = False
            combo.at[idx, 'combo_watch_end_signal'] = True
        if not risk_state and active_count >= 4:
            risk_state = True
            combo.at[idx, 'combo_risk_start_signal'] = True
        elif risk_state and active_count <= 3:
            risk_state = False
            combo.at[idx, 'combo_risk_end_signal'] = True
        combo.at[idx, 'combo_watch_state'] = watch_state
        combo.at[idx, 'combo_risk_state'] = risk_state
    return combo


def make_macro_index_cycle_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                                 dynamic_mode: bool = False, dynamic_window: int = 126,
                                 dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                                 ema_span: int | None = None):
    """⓪ 선택 지수 자체의 EMA 기반 Risk-off 사이클."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if spx_s is None or spx_s.empty:
        spx_s = _yf_close(benchmark['code'], years)
    if spx_s is None or spx_s.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_s.index, y=spx_s, name=benchmark['label'],
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{benchmark["label"]} %{{y:,.1f}}<extra></extra>',
    ))
    if dynamic_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        _add_dynamic_quantile_signals(
            fig, spx_s,
            window=int(dynamic_window),
            start_quantile=float(dynamic_start_quantile),
            end_quantile=float(dynamic_end_quantile),
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y',
        )
    else:
        _add_ema20_downturn_signals(fig, spx_s, show_downturn=True, overlay_price=spx_s, overlay_yaxis='y', params=downturn_params)
    fig.update_layout(
        **_ml(f'⓪ {benchmark["label"]} 지수 Risk-off 사이클', height=300),
    )
    return fig


def make_macro_combo_downturn_chart(years: int = 5, spx_s=None, signal_modes=None, downturn_params=None, benchmark_name='S&P500'):
    """⑤ 0~4 종합 Risk-off 사이클."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if spx_s is None or spx_s.empty:
        spx_s = _yf_close(benchmark['code'], years)
    if spx_s is None or spx_s.empty:
        return None

    if benchmark['kind'] == 'kr':
        hy = _korean_credit_proxy_series(years, 'A')
        ig = _korean_credit_proxy_series(years, 'AA')
        fx = _korean_fx_stress_series(years + 1)
        hv20 = _korean_volatility_series(years + 1, benchmark_s=spx_s, window=20)
        stress_parts = []
        if not hy.empty:
            stress_parts.append(_zscore(hy).rename('CorpA'))
        if not ig.empty:
            stress_parts.append(_zscore(ig).rename('CorpAA'))
        if not fx.empty:
            stress_parts.append(_zscore(fx).rename('USDKRW'))
        if not hv20.empty:
            stress_parts.append(_zscore(hv20).rename('HV20'))
        stress = pd.concat(stress_parts, axis=1).mean(axis=1).dropna() if stress_parts else pd.Series(dtype=float)
        vix = hv20
        parts = {
            'spx': spx_s.dropna(),
            'hy': hy.dropna(),
            'ig': ig.dropna(),
            'stress': stress.dropna(),
            'vix': vix.dropna(),
        }
        title = f'⑤ 종합 하락 사이클 (KOSPI 한국형 5지표 조합, {benchmark["label"]} 위 표시)'
    else:
        hy = _credit_spread_series('BAMLH0A0HYM2', years)
        ig = _credit_spread_series('BAMLC0A0CM', years)
        nfci = _fred('NFCI', years + 1)
        vix = _yf_close('^VIX', years + 1)
        stress_parts = []
        if not hy.empty:
            stress_parts.append(_zscore(hy).rename('HY'))
        if not nfci.empty:
            stress_parts.append(_zscore(nfci).rename('NFCI'))
        if not vix.empty:
            stress_parts.append(_zscore(vix).rename('VIX'))
        stress = pd.concat(stress_parts, axis=1).mean(axis=1).dropna() if stress_parts else pd.Series(dtype=float)
        parts = {
            'spx': spx_s.dropna(),
            'hy': (-hy).dropna(),
            'ig': (-ig).dropna(),
            'stress': (-stress).dropna(),
            'vix': (-vix).dropna(),
        }
        title = f'⑤ 종합 하락 사이클 (0~4 조합, {benchmark["label"]} 위 시작/종료 표시)'

    combo = _compute_combo_downturn_frame(parts, params=downturn_params)
    if combo.empty:
        return None
    spx_aligned = spx_s.reindex(combo.index).dropna()
    if spx_aligned.empty:
        return None
    combo = combo.reindex(spx_aligned.index)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark['label'],
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{benchmark["label"]} %{{y:,.1f}}<extra></extra>',
    ))
    watch_start_y = spx_aligned.loc[combo['combo_watch_start_signal']]
    watch_end_y = spx_aligned.loc[combo['combo_watch_end_signal']]
    risk_start_y = spx_aligned.loc[combo['combo_risk_start_signal']]
    risk_end_y = spx_aligned.loc[combo['combo_risk_end_signal']]
    show_watch = signal_modes is None or 'Watch' in signal_modes
    show_risk = signal_modes is not None and 'Risk' in signal_modes
    if show_watch and not watch_start_y.empty:
        fig.add_trace(go.Scatter(
            x=watch_start_y.index, y=watch_start_y, name='⑤ Watch 시작 (3/5)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=9, color='rgba(255,210,80,0.90)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Watch 시작: active_down_count >= 3<extra></extra>',
        ))
    if show_watch and not watch_end_y.empty:
        fig.add_trace(go.Scatter(
            x=watch_end_y.index, y=watch_end_y, name='⑤ Watch 종료 (2/5)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=9, color='rgba(75,255,179,0.90)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Watch 종료: active_down_count <= 2<extra></extra>',
        ))
    if show_risk and not risk_start_y.empty:
        fig.add_trace(go.Scatter(
            x=risk_start_y.index, y=risk_start_y, name='⑤ Risk 시작 (4/5)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(255,75,110,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Risk 시작: active_down_count >= 4<extra></extra>',
        ))
    if show_risk and not risk_end_y.empty:
        fig.add_trace(go.Scatter(
            x=risk_end_y.index, y=risk_end_y, name='⑤ Risk 종료 (3/5)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Risk 종료: active_down_count <= 3<extra></extra>',
        ))
    fig.update_layout(
        **_ml(title, height=300),
    )
    return fig


_MACRO2_SIGNAL_LABELS = {
    "0": "⓪ 지수",
    "1": "① HY",
    "2": "② IG",
    "3": "③ 신용스트레스",
    "4": "④ 옵션/변동성",
    "6": "⑥ 변동성 스프레드",
}


def _get_macro2_dynamic_defaults():
    return {
        "0": {"label": "⓪ 지수", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "1": {"label": "① HY", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "2": {"label": "② IG", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "3": {"label": "③ 신용스트레스", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "4": {"label": "④ 옵션/변동성", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "6": {"label": "⑥ 변동성 스프레드", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
    }


def _build_macro2_dynamic_charts(years: int, spx_s, show_raw: bool, benchmark_name: str, cfgs: dict):
    return [
        make_macro_index_cycle_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["0"]["ema"],
            dynamic_window=cfgs["0"]["window"],
            dynamic_start_quantile=cfgs["0"]["start"],
            dynamic_end_quantile=cfgs["0"]["end"],
        ),
        make_macro_hy_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["1"]["ema"],
            dynamic_window=cfgs["1"]["window"],
            dynamic_start_quantile=cfgs["1"]["start"],
            dynamic_end_quantile=cfgs["1"]["end"],
        ),
        make_macro_ig_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["2"]["ema"],
            dynamic_window=cfgs["2"]["window"],
            dynamic_start_quantile=cfgs["2"]["start"],
            dynamic_end_quantile=cfgs["2"]["end"],
        ),
        make_macro_credit_stress_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["3"]["ema"],
            dynamic_window=cfgs["3"]["window"],
            dynamic_start_quantile=cfgs["3"]["start"],
            dynamic_end_quantile=cfgs["3"]["end"],
        ),
        make_macro_options_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["4"]["ema"],
            dynamic_window=cfgs["4"]["window"],
            dynamic_start_quantile=cfgs["4"]["start"],
            dynamic_end_quantile=cfgs["4"]["end"],
        ),
        make_macro_vix_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["6"]["ema"],
            dynamic_window=cfgs["6"]["window"],
            dynamic_start_quantile=cfgs["6"]["start"],
            dynamic_end_quantile=cfgs["6"]["end"],
        ),
    ]


def _get_macro2_signal_series(signal_code: str, years: int, benchmark_name: str = 'S&P500', spx_s=None) -> pd.Series:
    benchmark = _get_macro_benchmark(benchmark_name)
    if signal_code == "0":
        if spx_s is None or spx_s.empty:
            spx_s = _yf_close(benchmark['code'], years)
        return spx_s.dropna() if spx_s is not None else pd.Series(dtype=float)

    if signal_code == "1":
        if benchmark['kind'] == 'kr':
            hy = _korean_credit_proxy_series(years, 'A')
        else:
            hy = _credit_spread_series('BAMLH0A0HYM2', years)
        return (-hy).dropna() if hy is not None else pd.Series(dtype=float)

    if signal_code == "2":
        if benchmark['kind'] == 'kr':
            ig = _korean_credit_proxy_series(years, 'AA')
        else:
            ig = _credit_spread_series('BAMLC0A0CM', years)
        return (-ig).dropna() if ig is not None else pd.Series(dtype=float)

    if signal_code == "3":
        parts = []
        if benchmark['kind'] == 'kr':
            hy = _korean_credit_proxy_series(years + 1, 'A')
            ig = _korean_credit_proxy_series(years + 1, 'AA')
            fx = _korean_fx_stress_series(years + 1)
            hv20 = _korean_volatility_series(years + 1, benchmark_s=spx_s, window=20)
            if not hy.empty:
                parts.append(_zscore(hy).rename('CorpA'))
            if not ig.empty:
                parts.append(_zscore(ig).rename('CorpAA'))
            if not fx.empty:
                parts.append(_zscore(fx).rename('USDKRW'))
            if not hv20.empty:
                parts.append(_zscore(hv20).rename('HV20'))
        else:
            hy = _credit_spread_series('BAMLH0A0HYM2', years + 1)
            nfci = _fred('NFCI', years + 1)
            vix = _yf_close('^VIX', years + 1)
            if not hy.empty:
                parts.append(_zscore(hy).rename('HY'))
            if not nfci.empty:
                parts.append(_zscore(nfci).rename('NFCI'))
            if not vix.empty:
                parts.append(_zscore(vix).rename('VIX'))
        if not parts:
            return pd.Series(dtype=float)
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
        stress = pd.concat(parts, axis=1).mean(axis=1).dropna()
        stress = stress[stress.index >= cutoff]
        return (-stress).dropna()

    if signal_code == "4":
        if benchmark['kind'] == 'kr':
            vol = _korean_volatility_series(years, benchmark_s=spx_s, window=20)
        else:
            vol = _yf_close('^VIX', years)
        return (-vol).dropna() if vol is not None else pd.Series(dtype=float)

    if signal_code == "6":
        if benchmark['kind'] == 'kr':
            spread = _korean_vol_term_spread_series(years, benchmark_s=spx_s)
        else:
            vix = _yf_close('^VIX', years)
            vix3m = _yf_close('^VIX3M', years)
            if vix.empty or vix3m.empty:
                return pd.Series(dtype=float)
            spread = (vix - vix3m.reindex(vix.index)).dropna()
        return (-spread).dropna() if spread is not None else pd.Series(dtype=float)

    return pd.Series(dtype=float)


def make_macro_combo_dynamic_chart(
    years: int = 5,
    spx_s=None,
    benchmark_name: str = 'S&P500',
    selected_codes=None,
    cfgs=None,
    combo_k: int = 3,
):
    benchmark = _get_macro_benchmark(benchmark_name)
    if spx_s is None or spx_s.empty:
        spx_s = _yf_close(benchmark['code'], years)
    if spx_s is None or spx_s.empty:
        return None

    selected_codes = list(selected_codes or ["0", "1", "3", "6"])
    cfgs = cfgs or _get_macro2_dynamic_defaults()
    if not selected_codes:
        return None

    frames = {}
    for code in selected_codes:
        series = _get_macro2_signal_series(code, years, benchmark_name=benchmark_name, spx_s=spx_s)
        if series is None or series.empty or code not in cfgs:
            continue
        signal_df = _compute_dynamic_quantile_signal_frame(
            series,
            window=int(cfgs[code]["window"]),
            start_quantile=float(cfgs[code]["start"]),
            end_quantile=float(cfgs[code]["end"]),
            ema_span=int(cfgs[code]["ema"]),
        )
        if signal_df.empty:
            continue
        frames[code] = signal_df[["down_flag"]].rename(columns={"down_flag": f"{code}_down_flag"})

    if not frames:
        return None

    combo = pd.concat(frames.values(), axis=1).sort_index().fillna(False)
    flag_cols = [f"{code}_down_flag" for code in frames]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    combo["combo_risk_state"] = False
    combo["combo_start_signal"] = False
    combo["combo_end_signal"] = False

    combo_k = max(1, min(int(combo_k), len(flag_cols)))
    in_cycle = False
    for idx in combo.index:
        active_count = int(combo.at[idx, "active_count"])
        if not in_cycle and active_count >= combo_k:
            in_cycle = True
            combo.at[idx, "combo_start_signal"] = True
        elif in_cycle and active_count < combo_k:
            in_cycle = False
            combo.at[idx, "combo_end_signal"] = True
        combo.at[idx, "combo_risk_state"] = in_cycle

    spx_aligned = spx_s.reindex(combo.index).dropna()
    if spx_aligned.empty:
        return None
    combo = combo.reindex(spx_aligned.index).fillna(False)
    combo["active_count"] = combo["active_count"].astype(int)

    selected_labels = ", ".join(_MACRO2_SIGNAL_LABELS.get(code, code) for code in selected_codes if code in frames)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark['label'],
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{benchmark['label']} %{{y:,.1f}}<extra></extra>',
    ))

    start_y = spx_aligned.loc[combo["combo_start_signal"]]
    end_y = spx_aligned.loc[combo["combo_end_signal"]]
    if not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name=f'Risk-off 시작 ({combo_k}/{len(flag_cols)})',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(255,75,110,0.92)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>Risk-off 시작: active_count >= {combo_k}<extra></extra>',
        ))
    if not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name=f'Risk-off 종료 (<{combo_k}/{len(flag_cols)})',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(75,255,179,0.92)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>Risk-off 종료: active_count < {combo_k}<extra></extra>',
        ))
    fig.update_layout(
        **_ml(f'⓪ 조합 Risk-off 사이클 ({benchmark["label"]}, {combo_k}/{len(flag_cols)})', height=300),
    )
    fig.add_annotation(
        xref='paper', yref='paper', x=0.01, y=0.98, showarrow=False,
        text=f'<b>조합</b>: {selected_labels}',
        font=dict(size=11, color='#C8C8C8'),
        align='left',
        bgcolor='rgba(0,0,0,0.18)',
        bordercolor='rgba(255,255,255,0.08)',
        borderwidth=1,
        borderpad=4,
    )
    return fig


def _make_inverted_spread_chart(
    s: pd.Series,
    title: str,
    trace_name: str,
    spx_s=None,
    benchmark_label='S&P500',
    color='#FF8C69',
    height=300,
    suffix='%',
    show_raw=True,
    show_downturn=True,
    downturn_params=None,
    dynamic_mode: bool = False,
    dynamic_window: int = 126,
    dynamic_start_quantile: float = 0.4,
    dynamic_end_quantile: float = 0.2,
    ema_span: int | None = None,
):
    """스프레드는 -1배로 표시해 위험 확대가 아래쪽으로 보이게 한다."""
    if s is None or s.empty:
        return None
    plot_s = (-s).dropna()
    if plot_s.empty:
        return None
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
    if show_raw:
        fig.add_trace(go.Scatter(
            x=plot_s.index, y=plot_s,
            name=f'{trace_name} (반전)',
            line=dict(color=color, width=1.2),
            opacity=0.28,
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  반전값 %{y:.2f}<extra></extra>',
        ))
    _add_spx_overlay(fig, plot_s, spx_s, yaxis='y2', label=benchmark_label)
    if dynamic_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        _add_dynamic_quantile_signals(
            fig, plot_s,
            window=int(dynamic_window),
            start_quantile=float(dynamic_start_quantile),
            end_quantile=float(dynamic_end_quantile),
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y2',
        )
    else:
        _add_ema20_downturn_signals(fig, plot_s, show_downturn=show_downturn, overlay_price=spx_s, overlay_yaxis='y2', params=downturn_params)
    fig.update_layout(
        **_ml(title, height=height),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.layout.yaxis.ticksuffix = suffix
    _add_corr_annotation(fig, plot_s, spx_s, label=f'vs {benchmark_label}')
    return fig


def make_macro_hy_spread_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                               dynamic_mode: bool = False, dynamic_window: int = 126,
                               dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                               ema_span: int | None = None):
    """① HY 크레딧 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        hy = _korean_credit_proxy_series(years, 'A')
        title = '① 회사채(A-이상)-국고채 상대강도 (반전, 한국 proxy)'
        trace_name = 'A-이상 회사채 프록시'
        suffix = ''
    else:
        hy = _credit_spread_series('BAMLH0A0HYM2', years)
        title = '① HY 크레딧 스프레드 (반전, OAS %)'
        trace_name = 'HY 스프레드'
        suffix = '%'
    return _make_inverted_spread_chart(
        hy, title, trace_name,
        spx_s=spx_s, benchmark_label=benchmark['label'], color='#FF4B6E', suffix=suffix, show_raw=show_raw,
        downturn_params=downturn_params, dynamic_mode=dynamic_mode, dynamic_window=dynamic_window,
        dynamic_start_quantile=dynamic_start_quantile, dynamic_end_quantile=dynamic_end_quantile, ema_span=ema_span,
    )


def make_macro_ig_spread_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                               dynamic_mode: bool = False, dynamic_window: int = 126,
                               dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                               ema_span: int | None = None):
    """② IG 크레딧 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        ig = _korean_credit_proxy_series(years, 'AA')
        title = '② 회사채(AA-이상)-국고채 상대강도 (반전, 한국 proxy)'
        trace_name = 'AA-이상 회사채 프록시'
        suffix = ''
    else:
        ig = _credit_spread_series('BAMLC0A0CM', years)
        title = '② IG 크레딧 스프레드 (반전, OAS %)'
        trace_name = 'IG 스프레드'
        suffix = '%'
    return _make_inverted_spread_chart(
        ig, title, trace_name,
        spx_s=spx_s, benchmark_label=benchmark['label'], color='#4BFFB3', suffix=suffix, show_raw=show_raw,
        downturn_params=downturn_params, dynamic_mode=dynamic_mode, dynamic_window=dynamic_window,
        dynamic_start_quantile=dynamic_start_quantile, dynamic_end_quantile=dynamic_end_quantile, ema_span=ema_span,
    )


def make_macro_credit_stress_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                                   threshold_mode=False, threshold_value: float = 0.0, ema_span: int | None = None,
                                   dynamic_mode: bool = False, dynamic_window: int = 126,
                                   dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                                   threshold_end_value: float | None = None):
    """③ 신용 스트레스 지수: HY + NFCI + VIX z-score 합성, 반전 표시."""
    benchmark = _get_macro_benchmark(benchmark_name)
    parts = []
    if benchmark['kind'] == 'kr':
        hy = _korean_credit_proxy_series(years + 1, 'A')
        ig = _korean_credit_proxy_series(years + 1, 'AA')
        fx = _korean_fx_stress_series(years + 1)
        hv20 = _korean_volatility_series(years + 1, benchmark_s=spx_s, window=20)
        if not hy.empty: parts.append(_zscore(hy).rename('CorpA'))
        if not ig.empty: parts.append(_zscore(ig).rename('CorpAA'))
        if not fx.empty: parts.append(_zscore(fx).rename('USDKRW'))
        if not hv20.empty: parts.append(_zscore(hv20).rename('HV20'))
        title = '③ 한국 스트레스 지수 (반전, 회사채·환율·변동성)'
    else:
        hy   = _credit_spread_series('BAMLH0A0HYM2', years + 1)
        nfci = _fred('NFCI',         years + 1)
        vix  = _yf_close('^VIX',     years + 1)
        if not hy.empty:   parts.append(_zscore(hy).rename('HY'))
        if not nfci.empty: parts.append(_zscore(nfci).rename('NFCI'))
        if not vix.empty:  parts.append(_zscore(vix).rename('VIX'))
        title = '③ 신용 스트레스 지수 (반전, HY + NFCI + VIX z-score)'
    if not parts:
        return None
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    stress = pd.concat(parts, axis=1).mean(axis=1).dropna()
    stress = stress[stress.index >= cutoff]
    if stress.empty:
        return None
    plot_s = (-stress).dropna()
    fig = go.Figure()
    fig.add_hline(y=0,  line=dict(color='rgba(255,255,255,0.2)', width=1))
    if threshold_end_value is None:
        fig.add_hline(y=1,  line=dict(color='rgba(75,255,179,0.25)',  dash='dot', width=1))
        fig.add_hline(y=-1, line=dict(color='rgba(255,75,110,0.25)',  dash='dot', width=1))
    if show_raw:
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s.clip(lower=0),
                                 fill='tozeroy', fillcolor='rgba(75,255,179,0.10)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s.clip(upper=0),
                                 fill='tozeroy', fillcolor='rgba(255,75,110,0.10)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s, name='신용 스트레스 (반전)',
                                 line=dict(color='#787EE7', width=1.2),
                                 opacity=0.28,
                                 hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:.2f}<extra></extra>'))
    _add_spx_overlay(fig, plot_s, spx_s, yaxis='y2', label=benchmark['label'])
    if dynamic_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        _add_dynamic_quantile_signals(
            fig,
            plot_s,
            window=int(dynamic_window),
            start_quantile=float(dynamic_start_quantile),
            end_quantile=float(dynamic_end_quantile),
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y2',
        )
    elif threshold_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        if threshold_end_value is not None:
            _add_dual_threshold_ema_signals(
                fig,
                plot_s,
                start_threshold=float(threshold_value),
                end_threshold=float(threshold_end_value),
                ema_span=_ema_span,
                overlay_price=spx_s,
                overlay_yaxis='y2',
            )
        else:
            _add_threshold_ema_signals(fig, plot_s, threshold=threshold_value, ema_span=_ema_span,
                                       overlay_price=spx_s, overlay_yaxis='y2')
    else:
        _add_ema20_downturn_signals(fig, plot_s, overlay_price=spx_s, overlay_yaxis='y2', params=downturn_params)
    fig.update_layout(
        **_ml(title),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.update_yaxes(tickformat='+.1f')
    _add_corr_annotation(fig, plot_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_options_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                             threshold_mode=False, threshold_value: float = -20.0, ema_span: int | None = None,
                             dynamic_mode: bool = False, dynamic_window: int = 126,
                             dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2):
    """④ VIX 레벨: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        vix = _korean_volatility_series(years, benchmark_s=spx_s, window=20)
        title = '④ 역사적 변동성 HV20 (반전, KOSPI)'
        trace_name = 'HV20 (반전)'
        line_label = '반전 HV20'
        threshold_1 = -20
        threshold_2 = -30
        corr_label = f'반전 HV20 vs {benchmark["label"]}'
    else:
        vix = _yf_close('^VIX', years)
        title = '④ VIX 레벨 (반전)'
        trace_name = 'VIX 레벨 (반전)'
        line_label = '반전 VIX'
        threshold_1 = -20
        threshold_2 = -30
        corr_label = f'반전 VIX vs {benchmark["label"]}'
    if vix.empty:
        return None
    plot_s = (-vix).dropna()
    fig = go.Figure()
    fig.add_hline(y=threshold_1, line=dict(color='rgba(255,255,255,0.12)', dash='dot', width=1))
    fig.add_hline(y=threshold_2, line=dict(color='rgba(255,75,110,0.30)', dash='dot', width=1))
    if show_raw:
        fig.add_trace(go.Scatter(
            x=plot_s.index, y=plot_s, name=trace_name,
            line=dict(color='#FF4B6E', width=1.2),
            opacity=0.28,
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b>  {line_label} %{{y:.1f}}<extra></extra>',
        ))
    _add_spx_overlay(fig, plot_s, spx_s, yaxis='y2', label=benchmark['label'])
    if dynamic_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        _add_dynamic_quantile_signals(
            fig, plot_s,
            window=int(dynamic_window),
            start_quantile=float(dynamic_start_quantile),
            end_quantile=float(dynamic_end_quantile),
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y2',
        )
    elif threshold_mode:
        _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
        _add_threshold_ema_signals(fig, plot_s, threshold=threshold_value, ema_span=_ema_span,
                                   overlay_price=spx_s, overlay_yaxis='y2')
    else:
        _add_ema20_downturn_signals(fig, plot_s, overlay_price=spx_s, overlay_yaxis='y2', params=downturn_params)
    fig.update_layout(
        **_ml(title, height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    _add_corr_annotation(fig, plot_s, spx_s, label=corr_label)
    return fig


def make_macro_vix_spread_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                                threshold_mode=False, threshold_value: float = 2.0, ema_span: int | None = None,
                                dynamic_mode: bool = False, dynamic_window: int = 126,
                                dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2):
    """⑥ VIX-VIX3M 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        spread = _korean_vol_term_spread_series(years, benchmark_s=spx_s)
        title = '⑥ HV20-HV60 스프레드 (반전, KOSPI)'
        trace_name = 'HV20-HV60 스프레드'
    else:
        vix   = _yf_close('^VIX',   years)
        vix3m = _yf_close('^VIX3M', years)
        if vix.empty or vix3m.empty:
            return None
        spread = (vix - vix3m.reindex(vix.index)).dropna()
        title = '⑥ VIX-VIX3M 스프레드 (반전)'
        trace_name = 'VIX-VIX3M 스프레드'
    if not threshold_mode and not dynamic_mode:
        return _make_inverted_spread_chart(
            spread, title, trace_name,
            spx_s=spx_s, benchmark_label=benchmark['label'], color='#FF8C69', suffix='', show_raw=show_raw, downturn_params=downturn_params,
        )

    if spread is None or spread.empty:
        return None
    plot_s = (-spread).dropna()
    if plot_s.empty:
        return None
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
    if show_raw:
        fig.add_trace(go.Scatter(
            x=plot_s.index, y=plot_s, name=f'{trace_name} (반전)',
            line=dict(color='#FF8C69', width=1.2),
            opacity=0.28,
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  반전값 %{y:.2f}<extra></extra>',
        ))
    _add_spx_overlay(fig, plot_s, spx_s, yaxis='y2', label=benchmark['label'])
    _ema_span = int(ema_span or _resolve_downturn_params(downturn_params)['ema_span'])
    if dynamic_mode:
        _add_dynamic_quantile_signals(
            fig, plot_s,
            window=int(dynamic_window),
            start_quantile=float(dynamic_start_quantile),
            end_quantile=float(dynamic_end_quantile),
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y2',
        )
    else:
        _add_threshold_ema_signals(
            fig, plot_s,
            threshold=threshold_value,
            ema_span=_ema_span,
            overlay_price=spx_s,
            overlay_yaxis='y2',
        )
    fig.update_layout(
        **_ml(title, height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    _add_corr_annotation(fig, plot_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_pmi_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """⑦ ISM 신규주문-재고 스프레드 (대리지표: 제조업 신규주문 vs 재고-판매비율)
    ISM 원데이터는 FRED에 없으므로:
      - 신규주문 proxy: AMTMNO (전체 제조업 신규주문, SA) → NEWORDER → DGORDER 순 fallback
      - 재고 proxy: ISRATIO (재고/판매비율) 역방향 — 재고 증가=악화
    스프레드 = 신규주문 YoY% - 재고비율 YoY%
    양→음 전환 시 경기 둔화 확정적 (ISM 스프레드 개념 동일)
    """
    benchmark = _get_macro_benchmark(benchmark_name)
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

    main_s = ord_yoy
    spread_s = pd.Series(dtype=float)

    if not inv_s.empty:
        inv_yoy = (inv_s.pct_change(12) * 100).dropna()
        inv_yoy = inv_yoy[inv_yoy.index >= cutoff]
        # 스프레드 = 신규주문 YoY% + 재고비율 YoY% 반전 (클수록 수요>공급)
        aligned = ord_yoy.reindex(inv_yoy.index).dropna()
        inv_aligned = inv_yoy.reindex(aligned.index).dropna()
        aligned = aligned.reindex(inv_aligned.index)
        spread_s = (aligned - inv_aligned).dropna()

    if not spread_s.empty:
        main_s = spread_s
    if main_s.empty:
        return None

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
    fig.add_trace(go.Scatter(
        x=main_s.index, y=main_s, name='신규주문-재고 스프레드',
        line=dict(color='#C8C850', width=1.3),
        hovertemplate='<b>%{x|%Y-%m-%d}</b>  %{y:.2f}%<extra></extra>',
    ))
    _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
    fig.update_layout(
        **_ml('⑧ 신규주문-재고 스프레드 (YoY%)' if benchmark['kind'] != 'kr' else '⑧ 글로벌 신규주문-재고 스프레드 (KOSPI 외수 proxy)', height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.layout.yaxis.ticksuffix = '%'
    _add_corr_annotation(fig, main_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_liquidity_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """⑧ 유동성: M2 YoY% + Fed 자산 YoY%"""
    benchmark = _get_macro_benchmark(benchmark_name)
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
                                 line=dict(color='rgba(75,255,179,0.38)', width=1.2)))
        main_s = m2_yoy
    if not fed.empty:
        fed_yoy = (fed.pct_change(52) * 100).dropna()
        fed_yoy = fed_yoy[fed_yoy.index >= cutoff]
        fig.add_trace(go.Scatter(x=fed_yoy.index, y=fed_yoy, name='Fed 자산 YoY%',
                                 line=dict(color='rgba(120,126,231,0.38)', width=1.1, dash='dot')))
        if main_s is None:
            main_s = fed_yoy
    _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
    fig.update_layout(
        **_ml('⑨ 유동성 지표 (M2 · Fed 자산 YoY%)' if benchmark['kind'] != 'kr' else '⑨ 글로벌 유동성 지표 (KOSPI 외국인 자금 proxy)'),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.update_yaxes(ticksuffix='%')
    _add_corr_annotation(fig, main_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_yield_curve_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """⑨ 장단기 금리차: T10Y3M(10Y-3M)
    1순위: FRED 사전계산 시리즈 (T10Y3M, T10Y2Y) — 더 안정적
    2순위: 구성 금리 직접 차감 (DGS10 - DTB3 / DGS2) — fallback
    """
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        spread, bond_3y, bond_10y = _korean_yield_curve_proxy_bundle(years)
        if spread.empty and bond_3y.empty and bond_10y.empty:
            return None
        fig = go.Figure()
        fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
        if not spread.empty:
            fig.add_trace(go.Scatter(
                x=spread.index, y=spread, name='3Y-10Y 상대강도',
                line=dict(color='#4BFFB3', width=1.5),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  상대강도 %{y:.2f}<extra></extra>',
            ))
        if not bond_10y.empty:
            fig.add_trace(go.Scatter(
                x=bond_10y.index, y=bond_10y, name='국고채10년 ETF',
                line=dict(color='rgba(200,200,200,0.55)', width=1.0, dash='dot'),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  10년 ETF %{y:.2f}<extra></extra>',
                yaxis='y3',
            ))
        if not bond_3y.empty:
            fig.add_trace(go.Scatter(
                x=bond_3y.index, y=bond_3y, name='국고채3년 ETF',
                line=dict(color='rgba(120,220,255,0.60)', width=1.0, dash='dot'),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  3년 ETF %{y:.2f}<extra></extra>',
                yaxis='y3',
            ))
        main_s = spread if not spread.empty else bond_3y if not bond_3y.empty else bond_10y
        _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
        fig.update_layout(
            **_ml('⑦ 국고채 3Y-10Y 상대강도 (ETF proxy)', height=300),
            yaxis2=_visible_price_yaxis('y', 'right'),
            yaxis3=_hidden_yaxis('y', 'left'),
        )
        if not spread.empty:
            _add_corr_annotation(fig, spread, spx_s, label=f'vs {benchmark["label"]}')
        return fig

    t3m = _fred('T10Y3M', years)
    dgs10 = _fred('DGS10', years)
    dfii10 = _fred('DFII10', years)
    dgs2 = _fred('DGS2', years)
    dtb3 = _fred('DTB3', years)

    if t3m.empty:
        if not dgs10.empty and not dtb3.empty:
            t3m = (dgs10 - dtb3.reindex(dgs10.index).interpolate()).dropna()
    if t3m.empty and dgs10.empty and dfii10.empty and dgs2.empty and dtb3.empty:
        return None

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))

    if not t3m.empty:
        fig.add_trace(go.Scatter(
            x=t3m.index, y=t3m, name='10Y-3M 스프레드',
            line=dict(color='#4BFFB3', width=1.5),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  스프레드 %{y:.2f}%<extra></extra>',
        ))
    if not dgs10.empty:
        fig.add_trace(go.Scatter(
            x=dgs10.index, y=dgs10, name='10Y 명목',
            line=dict(color='rgba(200,200,200,0.55)', width=1.0, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y 명목 %{y:.2f}%<extra></extra>',
        ))
    if not dfii10.empty:
        fig.add_trace(go.Scatter(
            x=dfii10.index, y=dfii10, name='10Y 실질',
            line=dict(color='rgba(255,180,120,0.65)', width=1.0, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y 실질 %{y:.2f}%<extra></extra>',
        ))
    if not dgs2.empty:
        fig.add_trace(go.Scatter(
            x=dgs2.index, y=dgs2, name='2Y',
            line=dict(color='rgba(120,220,255,0.60)', width=1.0, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  2Y %{y:.2f}%<extra></extra>',
        ))
    if not dtb3.empty:
        fig.add_trace(go.Scatter(
            x=dtb3.index, y=dtb3, name='3M',
            line=dict(color='rgba(120,126,231,0.55)', width=1.0, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  3M %{y:.2f}%<extra></extra>',
        ))

    main_s = t3m if not t3m.empty else dgs10 if not dgs10.empty else dfii10 if not dfii10.empty else dgs2 if not dgs2.empty else dtb3
    _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
    fig.update_layout(
        **_ml('⑦ 10Y-3M 금리차 + 10Y 명목·실질 · 2Y · 3M', height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.layout.yaxis.ticksuffix = '%'
    if not t3m.empty:
        _add_corr_annotation(fig, t3m, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_ai_capex_chart(years: int = 5, spx_s=None):
    """⑩ 하이퍼스케일러 AI CAPEX 차트."""
    capex_df = _get_hyperscaler_capex_frame()
    if capex_df.empty:
        return _macro_placeholder_chart(
            '⑩ AI CAPEX 합산 차트',
            'CAPEX 데이터를 불러오지 못했습니다. macro_data/hyperscaler_capex_quarterly.csv 로 보완할 수 있습니다.',
            height=360,
        )

    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    capex_df = capex_df[capex_df.index >= cutoff].copy()
    if capex_df.empty:
        return _macro_placeholder_chart('⑩ AI CAPEX 합산 차트', '선택 기간에 표시할 CAPEX 데이터가 없습니다.', height=360)

    total = capex_df['Total CAPEX']
    qoq = total.pct_change() * 100
    yoy = total.pct_change(4) * 100
    _quarter_labels = capex_df.index.map(_quarter_timestamp_to_label)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.06,
        subplot_titles=['회사별 / 합산 CAPEX (billion USD)', '합산 CAPEX 변화율 (QoQ / YoY, %)'],
    )

    line_map = {
        'Google / Alphabet': '#4BFFB3',
        'Microsoft': '#7AAFD4',
        'Meta': '#FF8C69',
        'Amazon': '#C8C850',
        'Total CAPEX': '#EDEDED',
    }
    for col in [c for c in capex_df.columns if c != 'Total CAPEX']:
        if capex_df[col].dropna().empty:
            continue
        fig.add_trace(go.Scatter(
            x=capex_df.index, y=capex_df[col], name=col, customdata=_quarter_labels,
            line=dict(color=line_map.get(col, '#888'), width=1.4),
            hovertemplate='<b>%{customdata}</b><br>%{y:.1f} bn USD<extra></extra>',
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=total.index, y=total, name='4개사 합산 CAPEX', customdata=_quarter_labels,
        line=dict(color=line_map['Total CAPEX'], width=2.0),
        hovertemplate='<b>%{customdata}</b><br>합산 %{y:.1f} bn USD<extra></extra>',
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=qoq.index, y=qoq, name='합산 QoQ%', customdata=_quarter_labels,
        line=dict(color='rgba(75,255,179,0.70)', width=1.4, dash='dot'),
        hovertemplate='<b>%{customdata}</b><br>QoQ %{y:.1f}%<extra></extra>',
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=yoy.index, y=yoy, name='합산 YoY%', customdata=_quarter_labels,
        line=dict(color='rgba(255,140,105,0.75)', width=1.4, dash='dash'),
        hovertemplate='<b>%{customdata}</b><br>YoY %{y:.1f}%<extra></extra>',
    ), row=2, col=1)

    fig.update_layout(
        height=430,
        title=dict(text='⑩ AI CAPEX 합산 차트 (Google · Microsoft · Meta · Amazon)', font=dict(size=12, color='#9B9B9B'), x=0),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#9B9B9B', size=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1, font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=50, r=20, t=48, b=30),
        hovermode='x unified',
    )
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9))
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False)
    for ann in fig.layout.annotations:
        ann.font.size = 9
        ann.font.color = '#666'
    return fig


def make_macro_memory_price_chart(years: int = 5, spx_s=None):
    """⑪ 메모리 가격 방향 차트 (CSV fallback 중심)."""
    df = _load_memory_price_frame()
    if df.empty:
        return _macro_placeholder_chart(
            '⑪ 메모리 가격 방향 차트',
            'macro_data/memory_price_qoq.csv 에 분기별 DRAM/NAND QoQ 데이터를 넣으면 차트가 표시됩니다.',
            height=320,
        )

    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    df = df[df['quarter_ts'] >= cutoff].copy()
    if df.empty:
        return _macro_placeholder_chart('⑪ 메모리 가격 방향 차트', '선택 기간에 표시할 메모리 가격 데이터가 없습니다.', height=320)

    fig = go.Figure()
    _quarter_labels = df['quarter_ts'].map(_quarter_timestamp_to_label)
    color_map = {
        'dram_contract_qoq': ('DRAM Contract QoQ', '#4BFFB3'),
        'nand_contract_qoq': ('NAND Contract QoQ', '#FF8C69'),
        'dram_spot_qoq': ('DRAM Spot QoQ', '#7AAFD4'),
        'nand_spot_qoq': ('NAND Spot QoQ', '#C8C850'),
    }
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
    for col, (label, color) in color_map.items():
        if col in df.columns and df[col].dropna().any():
            fig.add_trace(go.Scatter(
                x=df['quarter_ts'], y=df[col], name=label, customdata=_quarter_labels,
                line=dict(color=color, width=1.5),
                hovertemplate='<b>%{customdata}</b><br>%{y:.1f}%<extra></extra>',
            ))
    fig.update_layout(
        **_ml('⑪ 메모리 가격 방향 차트 (QoQ %)', height=320),
    )
    fig.layout.yaxis.ticksuffix = '%'
    return fig


def make_macro_ai_memory_compare_chart(years: int = 5, spx_s=None):
    """⑫ AI CAPEX vs 메모리 실적 비교 차트."""
    capex_df = _get_hyperscaler_capex_frame()
    profit_df = _load_memory_profit_frame()
    if capex_df.empty or profit_df.empty:
        return _macro_placeholder_chart(
            '⑫ AI CAPEX vs 메모리 실적 비교',
            'CAPEX 또는 macro_data/memory_profit_quarterly.csv 데이터가 부족합니다.',
            height=380,
        )

    capex = capex_df[['Total CAPEX']].rename(columns={'Total CAPEX': 'capex_total'})
    profit_df = profit_df.set_index('quarter_ts').sort_index()
    profit_df['memory_profit_total'] = profit_df[['samsung_ds_op', 'sk_hynix_op']].sum(axis=1, min_count=1)
    merged = capex.join(profit_df[['memory_profit_total']], how='inner').dropna()
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    merged = merged[merged.index >= cutoff]
    if merged.empty:
        return _macro_placeholder_chart('⑫ AI CAPEX vs 메모리 실적 비교', '선택 기간에 두 데이터를 함께 비교할 구간이 없습니다.', height=380)

    capex_norm = (merged['capex_total'] / merged['capex_total'].iloc[0]) * 100
    profit_norm = (merged['memory_profit_total'] / merged['memory_profit_total'].iloc[0]) * 100 if merged['memory_profit_total'].iloc[0] != 0 else pd.Series(dtype=float)
    _quarter_labels = merged.index.map(_quarter_timestamp_to_label)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.45],
        vertical_spacing=0.06,
        subplot_titles=['절대값 비교 (CAPEX vs Memory Profit)', '정규화 지수 비교 (첫 분기 = 100)'],
    )
    fig.add_trace(go.Scatter(
        x=merged.index, y=merged['capex_total'], name='4개사 합산 CAPEX', customdata=_quarter_labels,
        line=dict(color='#EDEDED', width=2.0),
        hovertemplate='<b>%{customdata}</b><br>CAPEX %{y:.1f} bn USD<extra></extra>',
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=merged.index, y=merged['memory_profit_total'], name='삼성전자 + SK하이닉스 영업이익', customdata=_quarter_labels,
        line=dict(color='#4BFFB3', width=1.8),
        hovertemplate='<b>%{customdata}</b><br>Memory Profit %{y:.1f}<extra></extra>',
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=capex_norm.index, y=capex_norm, name='CAPEX Index100', customdata=_quarter_labels,
        line=dict(color='rgba(237,237,237,0.90)', width=1.8),
        hovertemplate='<b>%{customdata}</b><br>CAPEX %{y:.1f}<extra></extra>',
    ), row=2, col=1)
    if not profit_norm.empty:
        fig.add_trace(go.Scatter(
            x=profit_norm.index, y=profit_norm, name='Memory Profit Index100', customdata=_quarter_labels,
            line=dict(color='rgba(75,255,179,0.85)', width=1.8),
            hovertemplate='<b>%{customdata}</b><br>Profit %{y:.1f}<extra></extra>',
        ), row=2, col=1)
    fig.update_layout(
        height=430,
        title=dict(text='⑫ AI CAPEX vs 메모리 실적 비교', font=dict(size=12, color='#9B9B9B'), x=0),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#9B9B9B', size=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1, font=dict(size=9), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=50, r=20, t=48, b=30),
        hovermode='x unified',
    )
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9))
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False)
    for ann in fig.layout.annotations:
        ann.font.size = 9
        ann.font.color = '#666'
    return fig


def make_macro_ai_memory_signal_summary():
    """CAPEX/메모리 가격/실적 기반 요약 신호."""
    capex_df = _get_hyperscaler_capex_frame()
    mem_price_df = _load_memory_price_frame()
    mem_profit_df = _load_memory_profit_frame()

    if capex_df.empty or mem_price_df.empty or mem_profit_df.empty:
        return None

    capex_total = capex_df['Total CAPEX'].dropna()
    if len(capex_total) < 2:
        return None
    latest_capex_qoq = capex_total.pct_change().dropna().iloc[-1] if len(capex_total.dropna()) >= 2 else np.nan
    prev_capex_qoq = capex_total.pct_change().dropna().iloc[-2] if len(capex_total.dropna()) >= 3 else np.nan

    latest_price = mem_price_df[['dram_contract_qoq', 'nand_contract_qoq']].dropna(how='all')
    if latest_price.empty:
        return None
    latest_price_avg = latest_price.iloc[-1].mean(skipna=True)
    prev_price_avg = latest_price.iloc[-2].mean(skipna=True) if len(latest_price) >= 2 else np.nan

    mem_profit_df = mem_profit_df.copy()
    mem_profit_df['memory_profit_total'] = mem_profit_df[['samsung_ds_op', 'sk_hynix_op']].sum(axis=1, min_count=1)
    profit_total = mem_profit_df['memory_profit_total'].dropna()
    if len(profit_total) < 2:
        return None
    latest_profit_qoq = profit_total.pct_change().dropna().iloc[-1] if len(profit_total.dropna()) >= 2 else np.nan

    def _status_capex():
        if pd.isna(latest_capex_qoq):
            return 'Neutral'
        if latest_capex_qoq < 0:
            return 'Risk'
        if not pd.isna(prev_capex_qoq) and latest_capex_qoq < prev_capex_qoq:
            return 'Warning'
        return 'Positive'

    def _status_price():
        if pd.isna(latest_price_avg):
            return 'Neutral'
        if latest_price_avg < 0:
            return 'Risk'
        if not pd.isna(prev_price_avg) and latest_price_avg < prev_price_avg:
            return 'Warning'
        return 'Positive'

    def _status_profit():
        if pd.isna(latest_profit_qoq):
            return 'Neutral'
        if profit_total.iloc[-1] < 0:
            return 'Risk'
        if latest_profit_qoq < 0:
            return 'Warning'
        return 'Positive'

    capex_status = _status_capex()
    price_status = _status_price()
    profit_status = _status_profit()

    if 'Risk' in (capex_status, price_status):
        final_signal = 'Reduce'
    elif 'Warning' in (capex_status, price_status, profit_status):
        final_signal = 'Watch'
    else:
        final_signal = 'Maintain'

    return {
        'AI CAPEX': capex_status,
        'Memory Price': price_status,
        'Memory Profit': profit_status,
        'Final Signal': final_signal,
    }


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
        **_ml(f'외국인 누적 순매수 — {market_code} (억원)', height=280),
        yaxis2=_hidden_yaxis('y', 'right'),
    )
    fig.update_yaxes(tickformat=',.0f')
    _add_corr_annotation(fig, s, mkt_s, label=f'vs {market_code}')
    return fig, None


# ============================================================
# Arrow 직렬화 안전장치
# ============================================================
def make_arrow_safe(df):
    """st.dataframe(Styler) 표시 전 호출.

    숫자 컬럼에 '—' 같은 placeholder 문자열이 섞여 있으면 pyarrow가
    double로 변환하지 못해 ArrowInvalid 오류가 난다. object 타입 컬럼 중
    숫자로 변환 가능한 값이 하나라도 있으면 해당 컬럼을 숫자형으로 바꾸고
    변환 안 되는 값(예: '—')은 NaN으로 처리한다.
    완전히 텍스트인 컬럼과 인덱스(예: 종목명/지표명)는 그대로 둔다.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors='coerce')
            if converted.notna().any():
                df[col] = converted
    return df


# ============================================================
# 메인 앱
# ============================================================
def main(page="signal"):
    global rsi_buy_lower_global, rsi_sell_lower_global

    st.markdown(DARK_CSS, unsafe_allow_html=True)

    # 항상 파일에서 읽음 → 외부 수정·추가 즉시 반영, 삭제도 정확히 유지됨
    st.session_state.favorites = load_favorites()
    favorites = st.session_state.favorites

    if page in ("market_macro", "macro2", "macro3"):
        st.markdown("""
            <style>
            [data-testid="stSidebar"] { display: none !important; }
            section[data-testid="stSidebar"] { display: none !important; }
            </style>
        """, unsafe_allow_html=True)

    # ─── 사이드바 ─────────────────────────────────────────────
    if page not in ("market_macro", "macro2", "macro3"):
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
        _higher_interval_map = {"일봉": "1d", "주봉": "1wk", "월봉": "1mo"}
        _higher_bars_divisor = {"일봉": 1, "주봉": 5, "월봉": 21}
        st.markdown("**🕯 차트 모드**")
        chart_mode = st.radio(
            "차트모드", ["일봉", "주봉", "월봉", "분봉"], horizontal=True,
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
            higher_interval = _higher_interval_map[chart_mode]
            st.divider()
            st.markdown("**🔄 자동 새로고침**")
            auto_refresh = st.toggle(f"{chart_mode} 자동 갱신", value=False, key="daily_auto_refresh_toggle")
            if auto_refresh:
                refresh_interval_label = st.radio(
                    "갱신 주기", ["1분", "3분", "5분"], index=1,
                    horizontal=True, label_visibility="collapsed", key="daily_refresh_interval",
                )
                _refresh_ms = {"1분": 60_000, "3분": 180_000, "5분": 300_000}
                refresh_ms = _refresh_ms[refresh_interval_label]
            else:
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
                if st.button("➕ 직접 추가", width="stretch", key="direct_add_btn"):
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
                    if st.button("➕ 추가", width="stretch"):
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
    _page_titles = {
        "signal": ("TECHNICAL SIGNAL SCANNER", "🎯 기술적 신호 스캐너"),
        "market": ("MARKET INTERNALS", "🌐 시장 내부지표"),
        "macro": ("MACRO INDICATORS", "🌍 매크로 지표"),
        "market_macro": ("MARKET & MACRO DASHBOARD", "🌐 시장/매크로 지표"),
        "macro2": ("MACRO INDICATORS 2", "🧪 매크로 지표 2"),
        "macro3": ("MACRO INDICATORS 3", "🧪 매크로 지표 3"),
        "macro4": ("MACRO INDICATORS 4", "🧪 매크로 지표 4"),
        "all": ("TECHNICAL SIGNAL SCANNER", "🎯 기술적 신호 스캐너"),
    }
    _eyebrow, _title = _page_titles.get(page, _page_titles["signal"])
    st.markdown(f"""
        <div style='margin-bottom:16px;'>
            <p style='color:#555;font-size:11px;text-transform:uppercase;
                      letter-spacing:2px;margin:0 0 4px;font-weight:500;'>
                {_eyebrow}
            </p>
            <h2 style='margin:0;font-size:22px;font-weight:600;color:#EDEDED;line-height:1.3;'>
                {_title}
            </h2>
        </div>
    """, unsafe_allow_html=True)

    tab4 = None
    tab5 = None
    tab6 = None
    _market_macro_section = None
    if page == "all":
        tab1, tab2, tab3 = st.tabs(["📊 신호 스캐너", "🌐 시장 내부지표", "🌍 매크로 지표"])
    elif page == "signal":
        tab1, tab2, tab3 = st.container(), None, None
    elif page == "market":
        tab1, tab2, tab3 = None, st.container(), None
    elif page == "macro":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "market_macro":
        _market_macro_sections = [
            ("macro", "🌍 매크로 지표"),
            ("macro2", "🧪 매크로 지표 2"),
            ("macro3", "🧪 매크로 지표 3"),
            ("macro4", "🧪 매크로 지표 4"),
            ("market", "🌐 시장 내부지표"),
        ]
        _market_macro_section = st.radio(
            "섹션 선택",
            options=[k for k, _ in _market_macro_sections],
            format_func=lambda k: dict(_market_macro_sections).get(k, k),
            horizontal=True,
            label_visibility='collapsed',
            key="market_macro_section",
        )
        tab2 = st.container()
        tab3 = st.container()
        tab4 = st.container()
        tab5 = st.container()
        tab6 = st.container()
        tab1 = None
    elif page == "macro2":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro3":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro4":
        tab1, tab2, tab3 = None, None, st.container()
    else:
        st.error(f"알 수 없는 페이지입니다: {page}")
        return

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — 신호 스캐너
    # ═══════════════════════════════════════════════════════════
    if page in ("all", "signal"):
        with tab1:
            # 자동 새로고침 (분봉/일봉 옵션 ON 일 때만)
            if auto_refresh and AUTOREFRESH_AVAILABLE:
                st_autorefresh(interval=refresh_ms, key=f"{chart_mode}_autorefresh")
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
                # ── 원자재
                {"code": "HG=F",   "name": "구리 현물 (Copper Futures)"},
                {"code": "GC=F",   "name": "금 현물 (Gold Futures)"},
                {"code": "SI=F",   "name": "은 현물 (Silver Futures)"},
                # ── 비트코인
                {"code": "BTC-USD", "name": "비트코인 (BTC-USD)"},
                # ── 이더리움
                {"code": "ETH-USD", "name": "이더리움 (ETH-USD)"},
                # ── 주식 본주: 개별종목 (이름 오름차순: ASCII → 가나다)
                {"code": "GOOGL",  "name": "구글 알파벳 (GOOGL)"},
                {"code": "AMZN",   "name": "아마존 (AMZN)"},
                # ── 주식 본주: ETF 1배 (코드 오름차순)
                {"code": "AIPO",   "name": "AIPO AI·IPO ETF"},
                {"code": "BLOK",   "name": "BLOK 블록체인 ETF"},
                {"code": "GRID",   "name": "GRID 스마트그리드 ETF"},
                {"code": "QTUM",   "name": "QTUM 퀀텀컴퓨팅/AI ETF"},
                {"code": "SOXX",   "name": "SOXX 반도체 ETF"},
                {"code": "TAN",    "name": "TAN 태양광 ETF"},
                {"code": "UFO",    "name": "UFO 우주항공 ETF"},
                # ── 2배 레버리지 (코드 오름차순)
                {"code": "AMZU",   "name": "AMZU 아마존 2X"},
                {"code": "GGLL",   "name": "GGLL 구글 2X"},
                {"code": "UGL",    "name": "UGL 금 2X"},
                {"code": "USD",    "name": "USD 반도체 2X (ProShares)"},
                # ── 3배 레버리지 (코드 오름차순)
                {"code": "SOXL",   "name": "SOXL 반도체 3X"},
                {"code": "TECL",   "name": "TECL 테크 3X"},
                {"code": "TQQQ",   "name": "TQQQ 나스닥 3X"},
            ]

            tickers_tuple    = tuple(f['code'] for f in favorites)
            us_tickers_tuple = tuple(t['code'] for t in _US_WATCHLIST)

            with st.spinner("📡 데이터 로딩..."):
                if chart_mode == "분봉":
                    closes = fetch_intraday_batch(tickers_tuple, yf_interval)
                    us_closes = fetch_intraday_batch(us_tickers_tuple, yf_interval)
                    highs = lows = pd.DataFrame()
                    us_highs = us_lows = pd.DataFrame()
                else:
                    closes, highs, lows = fetch_ohlcv_batch(tickers_tuple, data_start, data_end, higher_interval)
                    us_closes, us_highs, us_lows = fetch_ohlcv_batch(us_tickers_tuple, data_start, data_end, higher_interval)

            # 데이터 로딩 실패 종목 안내 (해당 종목만 빈 값으로 표시, 앱은 계속 동작)
            _missing_kr = [f['name'] for f in favorites
                           if f['code'] not in closes.columns or closes[f['code']].dropna().empty]
            _missing_us = [t['name'] for t in _US_WATCHLIST
                           if t['code'] not in us_closes.columns or us_closes[t['code']].dropna().empty]
            _missing_all = _missing_kr + _missing_us
            if _missing_all:
                st.warning(
                    "⚠️ 일부 종목 데이터를 가져오지 못했습니다 (Yahoo Finance 요청 제한/일시 오류일 수 있음): "
                    + ", ".join(_missing_all)
                    + " — 해당 종목은 빈 값으로 표시됩니다. 잠시 후 새로고침하면 자동으로 다시 시도됩니다."
                )

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
                    _h = highs[code] if not highs.empty and code in highs.columns else None
                    _l = lows[code]  if not lows.empty  and code in lows.columns  else None
                    sig = get_current_signals(
                        series, high=_h, low=_l,
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
                    _h = us_highs[_code] if not us_highs.empty and _code in us_highs.columns else None
                    _l = us_lows[_code]  if not us_lows.empty  and _code in us_lows.columns  else None
                    _sig = get_current_signals(
                        _series, high=_h, low=_l,
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

            _kr_divider_prefix = "────────"

            def _kr_divider(label):
                return f"{_kr_divider_prefix} {label} {_kr_divider_prefix}"

            _kr_front_codes = {"^KQ11", "^KS11", "000660.KS", "005930.KS", "373220.KS"}
            _kr_retirement_100_codes = {
                "442570.KS",
                "284430.KS",
                "0162Z0.KS",
                "0025N0.KS",
                "0019K0.KS",
            }
            _kr_leverage_codes = {"0195S0.KS", "0195R0.KS"}
            _kr_front_names = [f['name'] for f in favorites if f['code'] in _kr_front_codes]
            _kr_retirement_100_names = [
                f['name'] for f in favorites
                if f['code'] in _kr_retirement_100_codes
            ]
            _kr_retirement_70_names = [
                f['name'] for f in favorites
                if f['code'] not in _kr_front_codes
                and f['code'] not in _kr_retirement_100_codes
                and f['code'] not in _kr_leverage_codes
            ]
            _kr_leverage_names = [
                f['name'] for f in favorites
                if f['code'] in _kr_leverage_codes
            ]
            kr_select_names = (
                _kr_front_names
                + [_kr_divider("퇴직연금 100%")]
                + _kr_retirement_100_names
                + [_kr_divider("퇴직연금 70%")]
                + _kr_retirement_70_names
                + [_kr_divider("레버리지 ETF")]
                + _kr_leverage_names
            )

            _us_divider_prefix = "────────"

            def _us_divider(label):
                return f"{_us_divider_prefix} {label} {_us_divider_prefix}"

            us_select_names = [
                "S&P 500 (^GSPC)",
                "나스닥 (^IXIC)",
                "다우존스 (^DJI)",
                "구리 현물 (Copper Futures)",
                "금 현물 (Gold Futures)",
                "은 현물 (Silver Futures)",
                _us_divider("코인 / 단일종목"),
                "비트코인 (BTC-USD)",
                "이더리움 (ETH-USD)",
                "구글 알파벳 (GOOGL)",
                "아마존 (AMZN)",
                _us_divider("1배 ETF"),
                "AIPO AI·IPO ETF",
                "BLOK 블록체인 ETF",
                "GRID 스마트그리드 ETF",
                "QTUM 퀀텀컴퓨팅/AI ETF",
                "SOXX 반도체 ETF",
                "TAN 태양광 ETF",
                "UFO 우주항공 ETF",
                _us_divider("레버리지 ETF"),
                "AMZU 아마존 2X",
                "GGLL 구글 2X",
                "UGL 금 2X",
                "USD 반도체 2X (ProShares)",
                "SOXL 반도체 3X",
                "TECL 테크 3X",
                "TQQQ 나스닥 3X",
            ]

            with col_kr:
                with st.expander("🇰🇷 한국 즐겨찾기", expanded=True):
                    if 'scan_kr_name' not in st.session_state or \
                            st.session_state.scan_kr_name not in kr_names:
                        st.session_state.scan_kr_name = kr_names[0]
                    if 'scan_kr_prev_name' not in st.session_state or \
                            st.session_state.scan_kr_prev_name not in kr_names:
                        st.session_state.scan_kr_prev_name = st.session_state.scan_kr_name

                    def _set_kr_select():
                        if st.session_state.scan_kr_name.startswith(_kr_divider_prefix):
                            st.session_state.scan_kr_name = st.session_state.scan_kr_prev_name
                        else:
                            st.session_state.scan_kr_prev_name = st.session_state.scan_kr_name
                            _set_kr()

                    st.selectbox("한국종목선택", kr_select_names,
                                 key='scan_kr_name', on_change=_set_kr_select,
                                 label_visibility='collapsed')

            with col_us:
                with st.expander("🇺🇸 미국 지수/ETF", expanded=True):
                    if 'scan_us_name' not in st.session_state or \
                            st.session_state.scan_us_name not in us_names:
                        st.session_state.scan_us_name = us_names[0]
                    if 'scan_us_prev_name' not in st.session_state or \
                            st.session_state.scan_us_prev_name not in us_names:
                        st.session_state.scan_us_prev_name = st.session_state.scan_us_name

                    def _set_us_select():
                        if st.session_state.scan_us_name.startswith(_us_divider_prefix):
                            st.session_state.scan_us_name = st.session_state.scan_us_prev_name
                        else:
                            st.session_state.scan_us_prev_name = st.session_state.scan_us_name
                            _set_us()

                    st.selectbox("미국종목선택", us_select_names,
                                 key='scan_us_name', on_change=_set_us_select,
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

            # ── 일/주/월봉 차트 ─────────────────────────────────
            if chart_mode != "분봉":
                with st.spinner("차트 로딩..."):
                    ohlcv = fetch_ohlcv(selected_code, data_start, data_end, higher_interval)

                if ohlcv.empty:
                    st.warning(f"⚠️ {selected_name} 데이터를 가져올 수 없습니다.")
                else:
                    _display_bars = None
                    if chart_mode == "주봉":
                        _display_bars = max(1, round(period_days / _higher_bars_divisor["주봉"]))
                    elif chart_mode == "월봉":
                        _display_bars = max(1, round(period_days / _higher_bars_divisor["월봉"]))
                    fig = make_detail_chart(
                        ohlcv, selected_name, period_days,
                        bb_window=bb_window, rsi_lookback=rsi_lookback,
                        rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                        persist=persist, phase2_rsi=phase2_rsi,
                        display_bars=_display_bars,
                    )
                    if fig:
                        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
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
                            st.plotly_chart(price_fig, width="stretch", config={"displayModeBar": False})

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
                        st.plotly_chart(fig_intra, width="stretch", config={"displayModeBar": False})
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
                            st.plotly_chart(pf, width="stretch", config={"displayModeBar": False})

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
    if page in ("all", "market") or (page == "market_macro" and _market_macro_section == "market"):
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
                    st.plotly_chart(_score_ts_fig, width="stretch",
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
                    width="stretch",
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
                        _ll_tbl = make_arrow_safe(_ll_tbl)  # Arrow 직렬화 안전장치
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
                            st.dataframe(_styled, width="stretch")
                            st.download_button(
                                "⬇ CSV 다운로드",
                                data=_ll_tbl.to_csv(float_format="%.2f"),
                                file_name=f"lead_lag_{market_choice}.csv",
                                mime="text/csv",
                            )
                        else:
                            st.info("데이터 부족으로 선행성 분석을 계산할 수 없습니다.")

        # ═══════════════════════════════════════════════════════════
        # TAB 3A — 매크로 지표 2 (실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro2" or (page == "market_macro" and _market_macro_section == "macro2"):
        _macro2_container = tab4 if page == "market_macro" else tab3
        with _macro2_container:
            st.caption("실험용 확장판입니다. ⓪/①/②/③/④/⑥ 차트 각각에 대해 동적 Risk 시작선/종료선을 개별 설정할 수 있습니다.")

            _c0, _c1, _c2 = st.columns([1.2, 2.8, 1.2])
            with _c0:
                _benchmark_name = st.selectbox(
                    "기준지수",
                    options=["S&P500", "Nasdaq", "KOSPI"],
                    index=0,
                    label_visibility='collapsed',
                    key='macro2_benchmark',
                )
            with _c1:
                _yr_opts = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년'}
                _macro2_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts.keys()),
                    value=3,
                    format_func=lambda x: _yr_opts[x],
                    label_visibility='collapsed',
                    key='macro2_years',
                )
            with _c2:
                _show_raw_macro2 = st.checkbox("원본선 표시", value=False, key='macro2_show_raw')

            _macro2_cfgs = {}
            _macro2_defaults = _get_macro2_dynamic_defaults()
            with st.expander("실험 설정", expanded=True):
                for _code, _cfg in _macro2_defaults.items():
                    with st.expander(_cfg["label"], expanded=(_code == "0")):
                        _s0, _s1, _s2, _s3 = st.columns(4)
                        with _s0:
                            _ema = st.selectbox("EMA", [10, 20, 30], index=[10, 20, 30].index(_cfg["ema"]), key=f'macro2_{_code}_ema')
                        with _s1:
                            _window = st.selectbox("Rolling Window", [63, 126, 252, 504], index=[63, 126, 252, 504].index(_cfg["window"]), key=f'macro2_{_code}_window')
                        with _s2:
                            _start = st.select_slider(
                                "Risk 시작 분위수",
                                options=[x / 100 for x in range(0, 101, 5)],
                                value=_cfg["start"],
                                format_func=lambda x: f"{int(x * 100)}%",
                                key=f'macro2_{_code}_start',
                            )
                        with _s3:
                            _end = st.select_slider(
                                "Risk 종료 분위수",
                                options=[x / 100 for x in range(0, 101, 5)],
                                value=_cfg["end"],
                                format_func=lambda x: f"{int(x * 100)}%",
                                key=f'macro2_{_code}_end',
                            )
                        _macro2_cfgs[_code] = {"ema": int(_ema), "window": int(_window), "start": float(_start), "end": float(_end)}

            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg2 = _get_macro_benchmark(_benchmark_name)
                _spx_s2 = _yf_close(_benchmark_cfg2['code'], _macro2_years)

            _invalid_macro2 = [f"({_code})" for _code, _cfg in _macro2_cfgs.items() if _cfg["start"] <= _cfg["end"]]
            if _invalid_macro2:
                st.warning(f"Risk 시작 분위수는 종료 분위수보다 높아야 합니다: {' '.join(_invalid_macro2)}")
            else:
                with st.spinner("📡 실험용 매크로 데이터 로딩 중..."):
                    _macro2_charts = _build_macro2_dynamic_charts(
                        _macro2_years, _spx_s2, _show_raw_macro2, _benchmark_name, _macro2_cfgs
                    )

                for _idx, _fig in enumerate(_macro2_charts):
                    if _fig is not None:
                        st.plotly_chart(
                            _fig,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro2_chart_{_idx}_{_benchmark_name}_{_macro2_years}",
                        )
                    else:
                        st.warning("실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")

        # ═══════════════════════════════════════════════════════════
        # TAB 3B — 매크로 지표 3 (정적 threshold 실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro3" or (page == "market_macro" and _market_macro_section == "macro3"):
        _macro3_container = tab5 if page == "market_macro" else tab3
        with _macro3_container:
            st.caption("정적 threshold 실험판입니다. ③/④/⑥ 차트에서 각 지표의 EMA가 지정 임계값 아래로 내려가면 시작, 위로 올라오면 종료로 단순화했습니다.")

            _c0, _c1, _c2 = st.columns([1.2, 2.8, 1.2])
            with _c0:
                _benchmark_name3 = st.selectbox(
                    "기준지수",
                    options=["S&P500", "Nasdaq", "KOSPI"],
                    index=0,
                    label_visibility='collapsed',
                    key='macro3_benchmark',
                )
            with _c1:
                _yr_opts3 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년'}
                _macro3_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts3.keys()),
                    value=3,
                    format_func=lambda x: _yr_opts3[x],
                    label_visibility='collapsed',
                    key='macro3_years',
                )
            with _c2:
                _show_raw_macro3 = st.checkbox("원본선 표시", value=False, key='macro3_show_raw')

            with st.expander("실험 설정", expanded=True):
                _s1, _s2, _s3, _s4, _s5 = st.columns(5)
                with _s1:
                    _ema_span3 = st.selectbox("EMA", [10, 20, 30], index=1, key='macro3_ema_span')
                with _s2:
                    _thr3_3 = st.number_input("③ 시작", value=0.5, step=0.1, format="%.2f", key='macro3_thr3')
                with _s3:
                    _thr3_end_3 = st.number_input("③ 종료", value=-0.5, step=0.1, format="%.2f", key='macro3_thr3_end')
                with _s4:
                    _thr4_3 = st.number_input("④ threshold", value=-20.0, step=0.5, format="%.2f", key='macro3_thr4')
                with _s5:
                    _thr6_3 = st.number_input("⑥ threshold", value=2.0, step=0.1, format="%.2f", key='macro3_thr6')

            _downturn_params3 = _DEFAULT_DOWNTURN_PARAMS.copy()
            _downturn_params3['ema_span'] = int(_ema_span3)

            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg3 = _get_macro_benchmark(_benchmark_name3)
                _spx_s3 = _yf_close(_benchmark_cfg3['code'], _macro3_years)

            with st.spinner("📡 실험용 매크로 데이터 로딩 중..."):
                _macro3_charts = [
                    make_macro_credit_stress_chart(
                        _macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3,
                        threshold_mode=True,
                        threshold_value=float(_thr3_3),
                        threshold_end_value=float(_thr3_end_3),
                        ema_span=int(_ema_span3)
                    ),
                    make_macro_options_chart(
                        _macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3,
                        threshold_mode=True, threshold_value=float(_thr4_3), ema_span=int(_ema_span3)
                    ),
                    make_macro_vix_spread_chart(
                        _macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3,
                        threshold_mode=True, threshold_value=float(_thr6_3), ema_span=int(_ema_span3)
                    ),
                ]

            for _idx, _fig in enumerate(_macro3_charts):
                if _fig is not None:
                    st.plotly_chart(
                        _fig,
                        width="stretch",
                        config={"displayModeBar": False},
                        key=f"macro3_chart_{_idx}_{_benchmark_name3}_{_macro3_years}",
                    )
                else:
                    st.warning("실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")

        # ═══════════════════════════════════════════════════════════
        # TAB 3C — 매크로 지표 4 (조합 Risk-off 실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro4" or (page == "market_macro" and _market_macro_section == "macro4"):
        _macro4_container = tab6 if page == "market_macro" else tab3
        with _macro4_container:
            st.caption("상단 조합 차트는 선택한 지표들의 Risk-off 상태를 합성하고, 아래 6개 차트는 매크로지표2와 동일한 개별 실험 차트입니다.")

            _macro4_defaults = _get_macro2_dynamic_defaults()
            _macro4_defaults["0"].update({"ema": 20, "window": 252, "start": 0.80, "end": 0.70})
            _macro4_defaults["1"].update({"ema": 20, "window": 126, "start": 0.60, "end": 0.50})
            _macro4_defaults["3"].update({"ema": 10, "window": 126, "start": 0.20, "end": 0.10})
            _macro4_defaults["6"].update({"ema": 30, "window": 63, "start": 0.60, "end": 0.10})
            _macro4_selected_default = ["0", "1", "3", "6"]

            _m40, _m41, _m42 = st.columns([1.2, 2.8, 1.2])
            with _m40:
                _benchmark_name4 = st.selectbox(
                    "기준지수",
                    options=["S&P500", "Nasdaq"],
                    index=0,
                    label_visibility='collapsed',
                    key='macro4_benchmark',
                )
            with _m41:
                _yr_opts4 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년'}
                _macro4_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts4.keys()),
                    value=3,
                    format_func=lambda x: _yr_opts4[x],
                    label_visibility='collapsed',
                    key='macro4_years',
                )
            with _m42:
                _show_raw_macro4 = st.checkbox("원본선 표시", value=False, key='macro4_show_raw')

            _m43, _m44 = st.columns([4.4, 1.6])
            with _m43:
                _selected_codes4 = st.multiselect(
                    "조합 지표",
                    options=list(_MACRO2_SIGNAL_LABELS.keys()),
                    default=_macro4_selected_default,
                    format_func=lambda x: _MACRO2_SIGNAL_LABELS.get(x, x),
                    key='macro4_selected_codes',
                )
            with _m44:
                _default_k4 = 3 if len(_selected_codes4) >= 3 else max(1, len(_selected_codes4))
                _combo_k4 = st.slider(
                    "Risk 기준",
                    min_value=1,
                    max_value=max(1, len(_selected_codes4)),
                    value=_default_k4,
                    format="%d개 이상 ON",
                    key='macro4_combo_k',
                )

            _macro4_cfgs = {}
            with st.expander("실험 설정", expanded=True):
                for _code, _cfg in _macro4_defaults.items():
                    with st.expander(_cfg["label"], expanded=(_code in _selected_codes4)):
                        _s0, _s1, _s2, _s3 = st.columns(4)
                        with _s0:
                            _ema = st.selectbox("EMA", [10, 20, 30], index=[10, 20, 30].index(_cfg["ema"]), key=f'macro4_{_code}_ema')
                        with _s1:
                            _window = st.selectbox("Rolling Window", [63, 126, 252, 504], index=[63, 126, 252, 504].index(_cfg["window"]), key=f'macro4_{_code}_window')
                        with _s2:
                            _start = st.select_slider(
                                "Risk 시작 분위수",
                                options=[x / 100 for x in range(0, 101, 5)],
                                value=_cfg["start"],
                                format_func=lambda x: f"{int(x * 100)}%",
                                key=f'macro4_{_code}_start',
                            )
                        with _s3:
                            _end = st.select_slider(
                                "Risk 종료 분위수",
                                options=[x / 100 for x in range(0, 101, 5)],
                                value=_cfg["end"],
                                format_func=lambda x: f"{int(x * 100)}%",
                                key=f'macro4_{_code}_end',
                            )
                        _macro4_cfgs[_code] = {"ema": int(_ema), "window": int(_window), "start": float(_start), "end": float(_end)}

            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg4 = _get_macro_benchmark(_benchmark_name4)
                _spx_s4 = _yf_close(_benchmark_cfg4['code'], _macro4_years)

            _invalid_macro4 = [f"({_code})" for _code, _cfg in _macro4_cfgs.items() if _cfg["start"] <= _cfg["end"]]
            if _invalid_macro4:
                st.warning(f"Risk 시작 분위수는 종료 분위수보다 높아야 합니다: {' '.join(_invalid_macro4)}")
            elif not _selected_codes4:
                st.warning("조합에 사용할 지표를 최소 1개 이상 선택해 주세요.")
            else:
                with st.spinner("📡 조합 매크로 데이터 로딩 중..."):
                    _macro4_combo_fig = make_macro_combo_dynamic_chart(
                        years=_macro4_years,
                        spx_s=_spx_s4,
                        benchmark_name=_benchmark_name4,
                        selected_codes=_selected_codes4,
                        cfgs=_macro4_cfgs,
                        combo_k=_combo_k4,
                    )
                    _macro4_charts = _build_macro2_dynamic_charts(
                        _macro4_years, _spx_s4, _show_raw_macro4, _benchmark_name4, _macro4_cfgs
                    )

                if _macro4_combo_fig is not None:
                    st.plotly_chart(
                        _macro4_combo_fig,
                        width="stretch",
                        config={"displayModeBar": False},
                        key=f"macro4_combo_{_benchmark_name4}_{_macro4_years}_{'_'.join(_selected_codes4)}_{_combo_k4}",
                    )
                else:
                    st.warning("조합 Risk-off 차트 데이터 로딩 실패 — 조합 지표/기간을 확인해 주세요.")

                for _idx, _fig in enumerate(_macro4_charts):
                    if _fig is not None:
                        st.plotly_chart(
                            _fig,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro4_chart_{_idx}_{_benchmark_name4}_{_macro4_years}",
                        )
                    else:
                        st.warning("개별 실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")

        # ═══════════════════════════════════════════════════════════
        # TAB 3 — 매크로 지표
        # ═══════════════════════════════════════════════════════════
    if page in ("all", "macro") or (page == "market_macro" and _market_macro_section == "macro"):
        with tab3:
            st.caption("FRED + yfinance 기반 매크로 지표 (일 1회 캐시). 나스닥은 미국 매크로 세트를 그대로 쓰고, 코스피는 변동성·텀스프레드·신용계열을 한국형 프록시로 대체합니다.")

            _c0, _c1, _c2, _c3, _c4 = st.columns([1.3, 2.7, 1, 1, 1.4])
            with _c0:
                _benchmark_name = st.selectbox(
                    "기준지수",
                    options=["S&P500", "Nasdaq", "KOSPI"],
                    index=0,
                    label_visibility='collapsed',
                )
            with _c1:
                _yr_opts = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년'}
                _macro_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts.keys()),
                    value=3,
                    format_func=lambda x: _yr_opts[x],
                    label_visibility='collapsed',
                )
            with _c2:
                _show_spx = st.checkbox("S&P500 오버레이", value=True)
            with _c3:
                _show_raw_macro = st.checkbox("원본선 표시", value=False)
            with _c4:
                _combo_modes = st.multiselect(
                    "⑤ 신호",
                    options=["Watch", "Risk"],
                    default=["Watch"],
                    label_visibility='collapsed',
                )

            with st.expander("고급 설정", expanded=False):
                _gp1, _gp2, _gp3, _gp4, _gp5 = st.columns(5)
                with _gp1:
                    _ema_span = st.selectbox("EMA", [10, 20], index=1)
                with _gp2:
                    _std_window = st.selectbox("rolling std N", [10, 20, 40], index=2)
                with _gp3:
                    _ema_compare_days = st.selectbox("EMA 비교 M일", [5, 10, 20], index=1)
                with _gp4:
                    _start_count = st.selectbox("하락 시작", [3, 4], index=1, format_func=lambda x: f"{x}/5")
                with _gp5:
                    _end_count = st.selectbox("하락 종료", [3, 4], index=0, format_func=lambda x: f"{x}/5")

            _downturn_params = {
                'ema_span': _ema_span,
                'std_window': _std_window,
                'ema_compare_days': _ema_compare_days,
                'start_count': _start_count,
                'end_count': _end_count,
            }

            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg = _get_macro_benchmark(_benchmark_name)
                _spx_s = _yf_close(_benchmark_cfg['code'], _macro_years) if _show_spx else None

            with st.spinner("📡 매크로 데이터 로딩 중..."):
                _macro_charts = [
                    make_macro_index_cycle_chart(_macro_years,    _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ⓪ 지수
                    make_macro_hy_spread_chart(_macro_years,     _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ① HY/한국형 proxy
                    make_macro_ig_spread_chart(_macro_years,     _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ② IG/한국형 proxy
                    make_macro_credit_stress_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ③ 크레딧 스트레스
                    make_macro_options_chart(_macro_years,       _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ④ VIX/HV20
                    make_macro_combo_downturn_chart(_macro_years, _spx_s, _combo_modes, _downturn_params, _benchmark_name),  # ⑤ 종합 하락 사이클
                    make_macro_vix_spread_chart(_macro_years,    _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),  # ⑥ VIX/HV term
                    make_macro_yield_curve_chart(_macro_years,   _spx_s, _benchmark_name),   # ⑦ 장단기 금리차
                    make_macro_pmi_chart(_macro_years,           _spx_s, _benchmark_name),   # ⑧ 경기 모멘텀
                    make_macro_liquidity_chart(_macro_years,     _spx_s, _benchmark_name),   # ⑨ 유동성
                    make_macro_ai_capex_chart(_macro_years,      _spx_s),   # ⑩ AI CAPEX
                ]

            _mc = st.columns(2)
            for i, ch in enumerate(_macro_charts):
                if ch is not None:
                    with _mc[i % 2]:
                        st.plotly_chart(
                            ch,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro_main_chart_{i}_{_benchmark_name}_{_macro_years}_{int(_show_spx)}_{int(_show_raw_macro)}",
                        )
                else:
                    with _mc[i % 2]:
                        _labels = ['⓪ S&P500', '① HY 스프레드', '② IG 스프레드', '③ 크레딧 스트레스', '④ VIX',
                                   '⑤ 종합 하락 사이클', '⑥ VIX 스프레드', '⑦ 금리차', '⑧ 경기 모멘텀', '⑨ 유동성',
                                   '⑩ AI CAPEX']
                        st.warning(f"{_labels[i]} 데이터 로딩 실패 — FRED 일시 불가. 잠시 후 재시도해 주세요.")


if __name__ == "__main__":
    main()
    benchmark = _get_macro_benchmark(benchmark_name)
