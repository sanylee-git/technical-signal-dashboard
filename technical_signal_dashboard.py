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
import hashlib
import os
import re
import sys
import time
import copy
import warnings
import traceback
from zoneinfo import ZoneInfo
warnings.filterwarnings('ignore')

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_COMBO1_EXPANDED_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo1_expanded_v1")
if os.path.isdir(os.path.join(_COMBO1_EXPANDED_ROOT, "combo1_expanded")) and _COMBO1_EXPANDED_ROOT not in sys.path:
    sys.path.append(_COMBO1_EXPANDED_ROOT)

try:
    from combo1_expanded.signals import (
        align_signal_to_benchmark as _combo1_align_signal_to_benchmark,
        build_hysteresis_combo_state as _combo1_build_hysteresis_combo_state,
        compute_bollinger_signal_frame as _combo1_compute_bollinger_signal_frame,
        compute_dynamic_quantile_signal_frame as _combo1_compute_dynamic_quantile_signal_frame,
        compute_rsi_signal_frame as _combo1_compute_rsi_signal_frame,
        compute_yield_slope_signal_frame as _combo1_compute_yield_slope_signal_frame,
    )
    COMBO1_EXPANDED_SIGNALS_AVAILABLE = True
except Exception:
    COMBO1_EXPANDED_SIGNALS_AVAILABLE = False

try:
    from combo1_expanded.availability import (
        apply_availability_lag as _combo1_apply_availability_lag,
        build_credit_stress_safe_from_components as _combo1_build_credit_stress_safe_from_components,
    )
    from combo1_expanded.config import PipelineConfig as _Combo1PipelineConfig
    COMBO1_EXPANDED_AVAILABILITY_AVAILABLE = True
    _MACRO3_AVAILABILITY_CONFIG = _Combo1PipelineConfig()
except Exception:
    COMBO1_EXPANDED_AVAILABILITY_AVAILABLE = False
    _MACRO3_AVAILABILITY_CONFIG = None

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


# 즐겨찾기 표 기능 토글
ENABLE_SIGNAL_TABLE_TF_BADGES = True
ENABLE_SIGNAL_TABLE_ROW_LINKS = True
DEBUG_MODE = False
MACRO_DEBUG_MODE = False
INFLIGHT_GUARD_STALE_SECONDS = 12
RECENT_FETCH_FALLBACK_SECONDS = 75
RECENT_FETCH_MAX_ITEMS = 8


# ============================================================
# 페이지 설정
# ============================================================
_IS_MARKET_MACRO_APP = any(
    os.path.basename(str(arg)) in ("market_macro_dashboard.py", "market_macro_dashboard2.py")
    for arg in sys.argv
)

def _configure_streamlit_page(page="signal"):
    is_market_macro_app = page in ("market_macro", "market", "macro", "macro2", "macro3", "macro4", "macro5", "macro6", "macro5_kospi") or _IS_MARKET_MACRO_APP
    st.set_page_config(
        page_title="시장/매크로 지표" if is_market_macro_app else "기술적 신호 스캐너",
        page_icon="🏔️" if is_market_macro_app else "🎯",
        layout="wide",
        initial_sidebar_state="collapsed" if is_market_macro_app else "expanded"
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

_MACRO_META_BACKTEST_COMPARE = {
    "sp500_buyhold": {"label": "S&P500 홀드", "group": "sp500", "metrics": {"10Y 자산": "356.4", "20Y 자산": "595.5", "10Y MDD": "-33.9%", "20Y MDD": "-56.8%", "20Y Risk-off": "0.0%", "20Y Cycle": "-", "짧은 Cycle": "-"}},
    "snp": {"label": "S&P 전용 조합", "group": "sp500", "metrics": {"10Y 자산": "428.5", "20Y 자산": "645.3", "10Y MDD": "-10.2%", "20Y MDD": "-27.6%", "20Y Risk-off": "26.0%", "20Y Cycle": "45", "짧은 Cycle": "5"}},
    "common": {"label": "미국 주식 공통 조합", "group": "sp500", "metrics": {"10Y 자산": "428.5", "20Y 자산": "645.3", "10Y MDD": "-10.2%", "20Y MDD": "-27.6%", "20Y Risk-off": "26.0%", "20Y Cycle": "45", "짧은 Cycle": "5"}},
    "snp_meta_1": {"label": "S&P 전용 메타조합 1", "group": "sp500", "metrics": {"10Y 자산": "436.4", "20Y 자산": "755.6", "10Y MDD": "-11.7%", "20Y MDD": "-21.9%", "20Y Risk-off": "30.7%", "20Y Cycle": "31", "짧은 Cycle": "5"}},
    "snp_meta_2": {"label": "S&P 전용 메타조합 2", "group": "sp500", "metrics": {"10Y 자산": "461.5", "20Y 자산": "1010.7", "10Y MDD": "-13.2%", "20Y MDD": "-26.0%", "20Y Risk-off": "15.8%", "20Y Cycle": "18", "짧은 Cycle": "3"}},
    "snp_meta_stab": {"label": "S&P 전용 메타조합 1 휩쏘제거", "group": "sp500", "metrics": {"10Y 자산": "474.6", "20Y 자산": "1399.7", "10Y MDD": "-19.2%", "20Y MDD": "-24.7%", "20Y Risk-off": "11.7%", "20Y Cycle": "11", "짧은 Cycle": "0"}},
    "snp_meta_stab_2": {"label": "S&P 전용 메타조합 2 휩쏘제거", "group": "sp500", "metrics": {"10Y 자산": "459.0", "20Y 자산": "1060.4", "10Y MDD": "-9.9%", "20Y MDD": "-23.6%", "20Y Risk-off": "33.1%", "20Y Cycle": "29", "짧은 Cycle": "0"}},
    "snp_meta_stab_3": {"label": "S&P 전용 메타조합 3 휩쏘제거", "group": "sp500", "metrics": {"10Y 자산": "422.5", "20Y 자산": "1088.3", "10Y MDD": "-13.0%", "20Y MDD": "-13.7%", "20Y Risk-off": "27.2%", "20Y Cycle": "28", "짧은 Cycle": "0"}},
    "nasdaq_buyhold": {"label": "나스닥 홀드", "group": "nasdaq", "metrics": {"10Y 자산": "536.8", "20Y 자산": "1229.0", "10Y MDD": "-36.4%", "20Y MDD": "-55.6%", "20Y Risk-off": "0.0%", "20Y Cycle": "-", "짧은 Cycle": "-"}},
    "nasdaq": {"label": "나스닥 전용 조합", "group": "nasdaq", "metrics": {"10Y 자산": "619.1", "20Y 자산": "2147.7", "10Y MDD": "-22.4%", "20Y MDD": "-23.2%", "20Y Risk-off": "25.5%", "20Y Cycle": "43", "짧은 Cycle": "5"}},
    "nasdaq_common": {"label": "미국 주식 공통 조합 (나스닥 기준)", "group": "nasdaq", "metrics": {"10Y 자산": "543.0", "20Y 자산": "852.4", "10Y MDD": "-19.5%", "20Y MDD": "-29.3%", "20Y Risk-off": "26.2%", "20Y Cycle": "42", "짧은 Cycle": "-"}},
    "nasdaq_meta": {"label": "나스닥 전용 메타조합", "group": "nasdaq", "metrics": {"10Y 자산": "785.7", "20Y 자산": "2617.9", "10Y MDD": "-21.5%", "20Y MDD": "-26.5%", "20Y Risk-off": "10.8%", "20Y Cycle": "17", "짧은 Cycle": "1"}},
    "nasdaq_meta_stab_1": {"label": "나스닥 전용 메타조합 휩쏘제거 1", "group": "nasdaq", "metrics": {"10Y 자산": "776.4", "20Y 자산": "2586.9", "10Y MDD": "-21.5%", "20Y MDD": "-26.5%", "20Y Risk-off": "10.8%", "20Y Cycle": "16", "짧은 Cycle": "0"}},
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

US_WATCHLIST = [
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


def _signal_increment_counter(name: str):
    try:
        counters = st.session_state.setdefault("_signal_debug_counters", {})
        counters[name] = int(counters.get(name, 0)) + 1
        return counters[name]
    except Exception:
        return None


def _signal_debug_log(event: str, **kwargs):
    if not DEBUG_MODE:
        return
    payload = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "event": event,
    }
    for key, value in kwargs.items():
        if isinstance(value, pd.DataFrame):
            payload[key] = f"{value.shape[0]}x{value.shape[1]}"
        elif isinstance(value, (list, tuple, set)) and len(value) > 12:
            payload[key] = f"{type(value).__name__}[{len(value)}]"
        else:
            payload[key] = value
    try:
        print("[signal-debug] " + json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        print(f"[signal-debug] {event} {payload}")


def _macro_debug_log(event: str, **kwargs):
    if not MACRO_DEBUG_MODE:
        return
    payload = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "event": event,
    }
    for key, value in kwargs.items():
        if isinstance(value, pd.DataFrame):
            payload[key] = f"{value.shape[0]}x{value.shape[1]}"
        elif isinstance(value, (list, tuple, set)) and len(value) > 12:
            payload[key] = f"{type(value).__name__}[{len(value)}]"
        else:
            payload[key] = value
    try:
        print("[macro-debug] " + json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        print(f"[macro-debug] {event} {payload}")


def _signal_scope_key(chart_mode: str, purpose: str, ticker: str | None = None,
                      interval: str | None = None, tickers_tuple=None):
    tickers_hash = ""
    if tickers_tuple:
        joined = "|".join(str(x) for x in tickers_tuple)
        tickers_hash = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
    payload = {
        "chart_mode": chart_mode or "",
        "purpose": purpose or "",
        "ticker": ticker or "",
        "interval": interval or "",
        "tickers_hash": tickers_hash,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _signal_inflight_enter(scope_key: str, stale_seconds: int = INFLIGHT_GUARD_STALE_SECONDS):
    try:
        guards = st.session_state.setdefault("_signal_inflight_guards", {})
        now = time.time()
        active = guards.get(scope_key)
        if active and now - float(active.get("ts", 0.0)) < stale_seconds:
            return False
        guards[scope_key] = {"ts": now}
        st.session_state["_signal_inflight_guards"] = guards
        return True
    except Exception:
        return True


def _signal_inflight_exit(scope_key: str):
    try:
        guards = st.session_state.get("_signal_inflight_guards", {})
        if scope_key in guards:
            guards.pop(scope_key, None)
            st.session_state["_signal_inflight_guards"] = guards
    except Exception:
        pass


def _signal_recent_fetch_get(scope_key: str, max_age_seconds: int = RECENT_FETCH_FALLBACK_SECONDS):
    try:
        cache = st.session_state.get("_signal_recent_fetch_cache", {})
        item = cache.get(scope_key)
        if not item:
            return None
        if time.time() - float(item.get("ts", 0.0)) > max_age_seconds:
            return None
        return {
            "df": item.get("df", pd.DataFrame()).copy(),
            "err": item.get("err"),
            "meta": dict(item.get("meta", {})),
        }
    except Exception:
        return None


def _signal_recent_fetch_put(scope_key: str, df: pd.DataFrame, err=None, **meta):
    try:
        cache = st.session_state.setdefault("_signal_recent_fetch_cache", {})
        cache[scope_key] = {
            "ts": time.time(),
            "df": df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(),
            "err": err,
            "meta": meta,
        }
        if len(cache) > RECENT_FETCH_MAX_ITEMS:
            oldest_keys = sorted(cache.keys(), key=lambda k: cache[k].get("ts", 0.0))
            for old_key in oldest_keys[:-RECENT_FETCH_MAX_ITEMS]:
                cache.pop(old_key, None)
        st.session_state["_signal_recent_fetch_cache"] = cache
    except Exception:
        pass


def _fetch_intraday_guarded(ticker: str, interval: str, chart_mode: str, purpose: str):
    scope_key = _signal_scope_key(chart_mode=chart_mode, purpose=purpose, ticker=ticker, interval=interval)
    call_count = _signal_increment_counter("fetch_intraday_guarded")
    started = time.perf_counter()
    acquired = _signal_inflight_enter(scope_key)
    if not acquired:
        recent = _signal_recent_fetch_get(scope_key)
        if recent is not None:
            _signal_debug_log(
                "fetch_intraday_guarded_recent_reuse",
                ticker=ticker,
                interval=interval,
                chart_mode=chart_mode,
                purpose=purpose,
                call_count=call_count,
                df_shape=recent["df"].shape,
            )
            return recent["df"], recent.get("err")

    try:
        _signal_debug_log(
            "fetch_intraday_guarded_start",
            ticker=ticker,
            interval=interval,
            chart_mode=chart_mode,
            purpose=purpose,
            call_count=call_count,
        )
        df, err = fetch_intraday(ticker, interval)
        if not df.empty:
            _signal_recent_fetch_put(scope_key, df, err, ticker=ticker, interval=interval, purpose=purpose)
        else:
            recent = _signal_recent_fetch_get(scope_key)
            if recent is not None:
                _signal_debug_log(
                    "fetch_intraday_guarded_fallback",
                    ticker=ticker,
                    interval=interval,
                    chart_mode=chart_mode,
                    purpose=purpose,
                    df_shape=recent["df"].shape,
                )
                return recent["df"], recent.get("err") or err
        return df, err
    finally:
        if acquired:
            _signal_inflight_exit(scope_key)
        _signal_debug_log(
            "fetch_intraday_guarded_end",
            ticker=ticker,
            interval=interval,
            chart_mode=chart_mode,
            purpose=purpose,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )


def _fetch_intraday_batch_guarded(tickers_tuple, interval: str, chart_mode: str, purpose: str):
    scope_key = _signal_scope_key(chart_mode=chart_mode, purpose=purpose, interval=interval, tickers_tuple=tickers_tuple)
    call_count = _signal_increment_counter("fetch_intraday_batch_guarded")
    started = time.perf_counter()
    acquired = _signal_inflight_enter(scope_key)
    if not acquired:
        recent = _signal_recent_fetch_get(scope_key)
        if recent is not None:
            _signal_debug_log(
                "fetch_intraday_batch_guarded_recent_reuse",
                interval=interval,
                chart_mode=chart_mode,
                purpose=purpose,
                tickers=len(tickers_tuple or ()),
                call_count=call_count,
                df_shape=recent["df"].shape,
            )
            return recent["df"]

    try:
        _signal_debug_log(
            "fetch_intraday_batch_guarded_start",
            interval=interval,
            chart_mode=chart_mode,
            purpose=purpose,
            tickers=len(tickers_tuple or ()),
            call_count=call_count,
        )
        df = fetch_intraday_batch(tickers_tuple, interval)
        if not df.empty:
            _signal_recent_fetch_put(scope_key, df, None, interval=interval, purpose=purpose, tickers=len(tickers_tuple or ()))
        else:
            recent = _signal_recent_fetch_get(scope_key)
            if recent is not None:
                _signal_debug_log(
                    "fetch_intraday_batch_guarded_fallback",
                    interval=interval,
                    chart_mode=chart_mode,
                    purpose=purpose,
                    tickers=len(tickers_tuple or ()),
                    df_shape=recent["df"].shape,
                )
                return recent["df"]
        return df
    finally:
        if acquired:
            _signal_inflight_exit(scope_key)
        _signal_debug_log(
            "fetch_intraday_batch_guarded_end",
            interval=interval,
            chart_mode=chart_mode,
            purpose=purpose,
            tickers=len(tickers_tuple or ()),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )


@st.cache_data(ttl=60)
def fetch_intraday(ticker, interval):
    """분봉 OHLCV (5m/15m/30m/60m). TTL=60s → 새로고침 시 최신 분봉 반영.
    반환: (DataFrame, error_str | None)
    """
    _call_count = _signal_increment_counter("fetch_intraday")
    _started = time.perf_counter()
    _signal_debug_log("fetch_intraday_start", ticker=ticker, interval=interval, call_count=_call_count)
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
        out = df_hist[cols].copy()
        _signal_debug_log(
            "fetch_intraday_end",
            ticker=ticker,
            interval=interval,
            call_count=_call_count,
            elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
            df_shape=out.shape,
            error=err_str,
        )
        return out, err_str

    err_str = " | ".join(errors)
    _signal_debug_log(
        "fetch_intraday_end",
        ticker=ticker,
        interval=interval,
        call_count=_call_count,
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
        df_shape=(0, 0),
        error=err_str,
    )
    return pd.DataFrame(), err_str


@st.cache_data(ttl=60)
def fetch_intraday_batch(tickers_tuple, interval):
    """분봉 Close 일괄 조회 (스캐너용).

    우선 yfinance batch 요청 1회로 최대한 묶고, 배치 누락 종목만 개별 fetch로 보완한다.
    """
    tickers = list(tickers_tuple)
    if not tickers:
        return pd.DataFrame()

    _call_count = _signal_increment_counter("fetch_intraday_batch")
    _started = time.perf_counter()
    _signal_debug_log("fetch_intraday_batch_start", interval=interval, tickers=len(tickers), call_count=_call_count)

    result = pd.DataFrame()
    period = {"5m": "5d", "15m": "7d", "30m": "14d", "60m": "30d"}.get(interval, "30d")

    try:
        raw = yf.download(
            tickers,
            period=period,
            interval=interval,
            progress=False,
            group_by='ticker',
            threads=False,
        )
        result = _extract_close_df(raw, tickers)
    except Exception:
        pass

    frames = {}
    if not result.empty:
        for ticker in result.columns:
            series = result[ticker].dropna()
            if not series.empty:
                frames[ticker] = series

    for ticker in tickers:
        if ticker in frames and not frames[ticker].empty:
            continue
        try:
            df, _ = fetch_intraday(ticker, interval)
            if not df.empty and 'Close' in df.columns:
                frames[ticker] = df['Close']
        except Exception:
            pass

    if not frames:
        _signal_debug_log(
            "fetch_intraday_batch_end",
            interval=interval,
            tickers=len(tickers),
            call_count=_call_count,
            elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
            df_shape=(0, 0),
        )
        return pd.DataFrame()

    result = pd.DataFrame(frames)
    result.index = _strip_tz(result.index)
    _signal_debug_log(
        "fetch_intraday_batch_end",
        interval=interval,
        tickers=len(tickers),
        call_count=_call_count,
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
        df_shape=result.shape,
    )
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

    # 동적 플래그는 상태가 여러 봉 지속될 수 있으므로 "플래그 진입 시점"만 마커로 표시
    dyn_buy_flag_start = dyn_of & ~dyn_of.shift(1, fill_value=False)
    dyn_sell_flag_start = dyn_oh & ~dyn_oh.shift(1, fill_value=False)
    dyn_buy_flag_idx = disp[dyn_buy_flag_start[disp].values]
    dyn_sell_flag_idx = disp[dyn_sell_flag_start[disp].values]

    # 보유 중 구간: 동적 매수 확정 이후 동적 매도 확정 전까지 가격선에 오버레이
    dyn_holding_state = pd.Series(False, index=close.index)
    _in_dyn_position = False
    for _i in range(len(close)):
        if bool(dyn_buy.iloc[_i]):
            _in_dyn_position = True
        dyn_holding_state.iloc[_i] = _in_dyn_position
        if bool(dyn_sell.iloc[_i]):
            dyn_holding_state.iloc[_i] = _in_dyn_position
            _in_dyn_position = False
    dyn_holding_disp = close[disp].where(dyn_holding_state[disp])

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
    fig.add_trace(go.Scatter(x=disp, y=dyn_holding_disp,
        name="★ 보유 중", line=dict(color="#C8C850", width=1.5),
        connectgaps=False, hoverinfo='skip'), row=1, col=1)
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
        (dyn_buy_flag_idx,  '#4F88C6', 'rgba(79,136,198,0.42)', 'triangle-up',   10, "▲ 매수 플래그"),
        (dyn_sell_flag_idx, '#E08A3A', 'rgba(224,138,58,0.42)', 'triangle-down', 10, "▼ 매도 플래그"),
        (dyn_buy_idx,  '#22C55E', 'rgba(34,197,94,0.42)',  'star',        11, "★ 동적+BB 매수"),
        (dyn_sell_idx, '#FF4B6E', 'rgba(255,75,110,0.4)',  'star',        11, "★ 동적+BB 매도"),
    ]:
        _x = _idx if len(_idx) > 0 else []
        _y = close[_idx] if len(_idx) > 0 else []
        fig.add_trace(go.Scatter(x=_x, y=_y, mode='markers',
            marker=dict(symbol=_sym, color=_color, size=_sz,
                        line=dict(color=_outline, width=1)),
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

    # 동적 플래그/확정 (Row2)
    if len(dyn_buy_flag_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_buy_flag_idx, y=rsi[dyn_buy_flag_idx], mode='markers',
            marker=dict(symbol='triangle-up', color='#4F88C6', size=10,
                        line=dict(color='rgba(79,136,198,0.42)', width=1)),
            showlegend=False), row=2, col=1)
    if len(dyn_sell_flag_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_sell_flag_idx, y=rsi[dyn_sell_flag_idx], mode='markers',
            marker=dict(symbol='triangle-down', color='#E08A3A', size=10,
                        line=dict(color='rgba(224,138,58,0.42)', width=1)),
            showlegend=False), row=2, col=1)

    # 동적+BB 확정 ★ (Row2: 초록=매수, 빨강=매도)
    if len(dyn_buy_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_buy_idx, y=rsi[dyn_buy_idx], mode='markers',
            marker=dict(symbol='star', color='#22C55E', size=11),
            showlegend=False), row=2, col=1)
    if len(dyn_sell_idx) > 0:
        fig.add_trace(go.Scatter(x=dyn_sell_idx, y=rsi[dyn_sell_idx], mode='markers',
            marker=dict(symbol='star', color='#FF4B6E', size=11),
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


def _empty_signal_row(code, name):
    return {
        'code': code, 'name': name,
        'close': None, 'pct_change': None, 'rsi': None,
        'bb_upper_touch': False, 'bb_lower_touch': False,
        'dyn_buy_signal': False, 'dyn_sell_signal': False,
        'band_buy_signal': False, 'band_sell_signal': False,
        'dyn_buy_flag': False, 'dyn_sell_flag': False,
        'band_buy_flag': False, 'band_sell_flag': False,
        'dyn_holding': False, 'band_holding': False,
    }


def _build_signal_rows_for_items(items, closes, highs, lows,
                                 bb_window, bb_std, rsi_period,
                                 rsi_buy_center, rsi_sell_center,
                                 rsi_band, rsi_lookback, persist,
                                 phase2_rsi):
    rows = []
    for item in items:
        code = item['code']
        row = _empty_signal_row(code, item['name'])
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
                last = float(series.iloc[-1])
                prev = float(series.iloc[-2])
                row['close'] = last
                row['pct_change'] = (last / prev - 1) * 100 if prev else 0.0
        rows.append(row)
    return rows


def _coerce_aware_datetime(now, tz_name: str):
    tz = ZoneInfo(tz_name)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _is_kr_market_active(now=None):
    now_kst = _coerce_aware_datetime(now, "Asia/Seoul")
    if now_kst.weekday() >= 5:
        return False
    current_minutes = now_kst.hour * 60 + now_kst.minute
    start_minutes = 8 * 60
    end_minutes = 16 * 60 + 30
    return start_minutes <= current_minutes <= end_minutes


def _is_us_market_active(now=None):
    now_et = _coerce_aware_datetime(now, "America/New_York")
    if now_et.weekday() >= 5:
        return False
    current_minutes = now_et.hour * 60 + now_et.minute
    start_minutes = 8 * 60 + 30
    end_minutes = 17 * 60
    return start_minutes <= current_minutes <= end_minutes


def _get_market_refresh_policy(auto_refresh=False, now=None):
    kr_active = _is_kr_market_active(now)
    us_active = _is_us_market_active(now)
    if not auto_refresh:
        return {
            "kr_active": kr_active,
            "us_active": us_active,
            "refresh_kr_snapshot": False,
            "refresh_us_snapshot": False,
        }
    return {
        "kr_active": kr_active,
        "us_active": us_active,
        "refresh_kr_snapshot": kr_active,
        "refresh_us_snapshot": us_active,
    }


def _signal_snapshot_required_keys():
    return {"signal_rows", "us_signal_rows", "missing_kr", "missing_us"}


def _make_signal_market_snapshot_signature(items_tuple, market_key, chart_mode,
                                           yf_interval, higher_interval, period_days,
                                           bb_window, bb_std, rsi_period,
                                           rsi_buy_center, rsi_sell_center,
                                           rsi_band, rsi_lookback, persist,
                                           phase2_rsi):
    payload = {
        "items": list(items_tuple),
        "market": market_key,
        "chart_mode": chart_mode,
        "yf_interval": yf_interval,
        "higher_interval": higher_interval,
        "period_days": int(period_days),
        "bb_window": int(bb_window),
        "bb_std": float(bb_std),
        "rsi_period": int(rsi_period),
        "rsi_buy_center": float(rsi_buy_center),
        "rsi_sell_center": float(rsi_sell_center),
        "rsi_band": float(rsi_band),
        "rsi_lookback": int(rsi_lookback),
        "persist": int(persist),
        "phase2_rsi": float(phase2_rsi),
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@st.cache_data(ttl=300, show_spinner=False)
def _build_signal_market_rows(items_tuple, market_key, chart_mode,
                              yf_interval, higher_interval, data_start, data_end,
                              bb_window, bb_std, rsi_period,
                              rsi_buy_center, rsi_sell_center,
                              rsi_band, rsi_lookback, persist,
                              phase2_rsi):
    items = [{"code": code, "name": name} for code, name in items_tuple]
    tickers_tuple = tuple(code for code, _ in items_tuple)

    if chart_mode == "분봉":
        closes = _fetch_intraday_batch_guarded(
            tickers_tuple,
            yf_interval,
            chart_mode,
            f"watchlist_batch_{market_key}",
        )
        highs = lows = pd.DataFrame()
    else:
        closes, highs, lows = fetch_ohlcv_batch(tickers_tuple, data_start, data_end, higher_interval)

    missing_items = [
        item["name"] for item in items
        if item["code"] not in closes.columns or closes[item["code"]].dropna().empty
    ]

    signal_rows = _build_signal_rows_for_items(
        items, closes, highs, lows,
        bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
        rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
        rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
        phase2_rsi=phase2_rsi,
    )
    signal_rows.sort(key=_signal_row_sort_key)

    if ENABLE_SIGNAL_TABLE_TF_BADGES:
        tf_labels = ("일봉", "주봉", "월봉")
        tf_maps = _build_multitimeframe_signal_maps(
            tuple((item["code"], item["name"]) for item in items),
            tickers_tuple,
            data_end,
            bb_window=bb_window,
            bb_std=bb_std,
            rsi_period=rsi_period,
            rsi_buy_center=rsi_buy_center,
            rsi_sell_center=rsi_sell_center,
            rsi_band=rsi_band,
            rsi_lookback=rsi_lookback,
            persist=persist,
            phase2_rsi=phase2_rsi,
        )
        for row in signal_rows:
            row["tf_signals"] = {
                tf_label: tf_maps.get(tf_label, {}).get(row["code"], _empty_signal_row(row["code"], row["name"]))
                for tf_label in tf_labels
            }

    return signal_rows, missing_items, closes.shape if isinstance(closes, pd.DataFrame) else None


@st.cache_data(ttl=300, show_spinner=False)
def _build_multitimeframe_signal_maps(items_tuple, tickers, data_end,
                                      bb_window, bb_std, rsi_period,
                                      rsi_buy_center, rsi_sell_center,
                                      rsi_band, rsi_lookback, persist,
                                      phase2_rsi):
    _started = time.perf_counter()
    _signal_debug_log("multitimeframe_signal_maps_start", items=len(items_tuple), tickers=len(tickers or ()))
    items = [{"code": code, "name": name} for code, name in items_tuple]
    tf_specs = [
        ("일봉", "1d", 63),
        ("주봉", "1wk", 504),
        ("월봉", "1mo", 2520),
    ]
    today = datetime.now().date()
    tf_maps = {}
    for tf_label, tf_interval, tf_days in tf_specs:
        tf_start = str(today - timedelta(days=tf_days + 400))
        tf_closes, tf_highs, tf_lows = fetch_ohlcv_batch(tickers, tf_start, data_end, tf_interval)
        tf_rows = _build_signal_rows_for_items(
            items, tf_closes, tf_highs, tf_lows,
            bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
            rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
            rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
            phase2_rsi=phase2_rsi,
        )
        tf_maps[tf_label] = {row["code"]: row for row in tf_rows}
    _signal_debug_log(
        "multitimeframe_signal_maps_end",
        items=len(items_tuple),
        tickers=len(tickers or ()),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return tf_maps


def _signal_row_sort_key(row):
    buy_sig = row.get('dyn_buy_signal')
    buy_flag = row.get('dyn_buy_flag') and not row.get('dyn_buy_signal')
    holding = row.get('dyn_holding')
    sell_sig = row.get('dyn_sell_signal')
    sell_flag = row.get('dyn_sell_flag') and not row.get('dyn_sell_signal')
    if buy_sig:
        return 0
    if buy_flag:
        return 1
    if holding:
        return 2
    if sell_sig:
        return 3
    if sell_flag:
        return 4
    return 5


@st.cache_data(ttl=300, show_spinner=False)
def _build_signal_dashboard_rows(favorites_tuple, us_watchlist_tuple, chart_mode,
                                 yf_interval, higher_interval, data_start, data_end,
                                 bb_window, bb_std, rsi_period,
                                 rsi_buy_center, rsi_sell_center,
                                 rsi_band, rsi_lookback, persist,
                                 phase2_rsi):
    _started = time.perf_counter()
    _signal_debug_log(
        "build_signal_dashboard_rows_start",
        chart_mode=chart_mode,
        favorites=len(favorites_tuple),
        us_favorites=len(us_watchlist_tuple),
        interval=yf_interval if chart_mode == "분봉" else higher_interval,
    )
    signal_rows, missing_kr, kr_shape = _build_signal_market_rows(
        favorites_tuple,
        "kr",
        chart_mode,
        yf_interval,
        higher_interval,
        data_start,
        data_end,
        bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
        rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
        rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
        phase2_rsi=phase2_rsi,
    )
    us_signal_rows, missing_us, us_shape = _build_signal_market_rows(
        us_watchlist_tuple,
        "us",
        chart_mode,
        yf_interval,
        higher_interval,
        data_start,
        data_end,
        bb_window=bb_window, bb_std=bb_std, rsi_period=rsi_period,
        rsi_buy_center=rsi_buy_center, rsi_sell_center=rsi_sell_center,
        rsi_band=rsi_band, rsi_lookback=rsi_lookback, persist=persist,
        phase2_rsi=phase2_rsi,
    )

    _signal_debug_log(
        "build_signal_dashboard_rows_end",
        chart_mode=chart_mode,
        favorites=len(favorites_tuple),
        us_favorites=len(us_watchlist_tuple),
        interval=yf_interval if chart_mode == "분봉" else higher_interval,
        kr_shape=kr_shape,
        us_shape=us_shape,
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return signal_rows, us_signal_rows, missing_kr, missing_us


def _make_signal_table_snapshot_signature(favorites_tuple, us_watchlist_tuple, chart_mode,
                                          yf_interval, higher_interval, period_days,
                                          bb_window, bb_std, rsi_period,
                                          rsi_buy_center, rsi_sell_center,
                                          rsi_band, rsi_lookback, persist,
                                          phase2_rsi):
    payload = {
        "favorites": list(favorites_tuple),
        "us_watchlist": list(us_watchlist_tuple),
        "chart_mode": chart_mode,
        "yf_interval": yf_interval,
        "higher_interval": higher_interval,
        "period_days": int(period_days),
        "bb_window": int(bb_window),
        "bb_std": float(bb_std),
        "rsi_period": int(rsi_period),
        "rsi_buy_center": float(rsi_buy_center),
        "rsi_sell_center": float(rsi_sell_center),
        "rsi_band": float(rsi_band),
        "rsi_lookback": int(rsi_lookback),
        "persist": int(persist),
        "phase2_rsi": float(phase2_rsi),
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _compose_signal_snapshot_from_market_payloads(market_payloads):
    market_payloads = market_payloads if isinstance(market_payloads, dict) else {}
    kr_payload = market_payloads.get("kr") if isinstance(market_payloads.get("kr"), dict) else {}
    us_payload = market_payloads.get("us") if isinstance(market_payloads.get("us"), dict) else {}
    return {
        "signal_rows": list(kr_payload.get("signal_rows", [])),
        "us_signal_rows": list(us_payload.get("signal_rows", [])),
        "missing_kr": list(kr_payload.get("missing_items", [])),
        "missing_us": list(us_payload.get("missing_items", [])),
        "_market_payloads": {
            "kr": {
                "signal_rows": list(kr_payload.get("signal_rows", [])),
                "missing_items": list(kr_payload.get("missing_items", [])),
            },
            "us": {
                "signal_rows": list(us_payload.get("signal_rows", [])),
                "missing_items": list(us_payload.get("missing_items", [])),
            },
        },
    }


def _signal_snapshot_has_required_keys(snapshot):
    return isinstance(snapshot, dict) and _signal_snapshot_required_keys().issubset(snapshot.keys())


def _get_signal_table_snapshot(favorites_tuple, us_watchlist_tuple, chart_mode,
                               yf_interval, higher_interval, period_days,
                               data_start, data_end,
                               bb_window, bb_std, rsi_period,
                               rsi_buy_center, rsi_sell_center,
                               rsi_band, rsi_lookback, persist,
                               phase2_rsi, force_refresh=False, auto_refresh=False):
    _started = time.perf_counter()
    snapshot_key = "_signal_table_snapshot_data"
    signature_key = "_signal_table_snapshot_signature"
    created_at_key = "_signal_table_snapshot_created_at"

    combined_signature = _make_signal_table_snapshot_signature(
        favorites_tuple,
        us_watchlist_tuple,
        chart_mode,
        yf_interval,
        higher_interval,
        period_days,
        bb_window,
        bb_std,
        rsi_period,
        rsi_buy_center,
        rsi_sell_center,
        rsi_band,
        rsi_lookback,
        persist,
        phase2_rsi,
    )
    kr_signature = _make_signal_market_snapshot_signature(
        favorites_tuple, "kr", chart_mode, yf_interval, higher_interval, period_days,
        bb_window, bb_std, rsi_period, rsi_buy_center, rsi_sell_center,
        rsi_band, rsi_lookback, persist, phase2_rsi,
    )
    us_signature = _make_signal_market_snapshot_signature(
        us_watchlist_tuple, "us", chart_mode, yf_interval, higher_interval, period_days,
        bb_window, bb_std, rsi_period, rsi_buy_center, rsi_sell_center,
        rsi_band, rsi_lookback, persist, phase2_rsi,
    )

    snapshot = st.session_state.get(snapshot_key)
    snapshot_signature_state = st.session_state.get(signature_key)
    snapshot_created_state = st.session_state.get(created_at_key)

    signature_map = snapshot_signature_state if isinstance(snapshot_signature_state, dict) else {}
    created_at_map = snapshot_created_state if isinstance(snapshot_created_state, dict) else {}
    market_payloads = snapshot.get("_market_payloads") if isinstance(snapshot, dict) else None

    policy = _get_market_refresh_policy(auto_refresh=auto_refresh)
    action = "reuse"

    if not auto_refresh:
        needs_refresh = force_refresh or signature_map.get("_combined", snapshot_signature_state) != combined_signature
        if not needs_refresh and not _signal_snapshot_has_required_keys(snapshot):
            needs_refresh = True
            action = "repair_refresh"
        elif needs_refresh:
            action = "refresh"

        if needs_refresh:
            signal_rows, us_signal_rows, missing_kr, missing_us = _build_signal_dashboard_rows(
                favorites_tuple,
                us_watchlist_tuple,
                chart_mode,
                yf_interval,
                higher_interval,
                data_start,
                data_end,
                bb_window=bb_window,
                bb_std=bb_std,
                rsi_period=rsi_period,
                rsi_buy_center=rsi_buy_center,
                rsi_sell_center=rsi_sell_center,
                rsi_band=rsi_band,
                rsi_lookback=rsi_lookback,
                persist=persist,
                phase2_rsi=phase2_rsi,
            )
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            snapshot = {
                "signal_rows": signal_rows,
                "us_signal_rows": us_signal_rows,
                "missing_kr": missing_kr,
                "missing_us": missing_us,
                "_market_payloads": {
                    "kr": {"signal_rows": list(signal_rows), "missing_items": list(missing_kr)},
                    "us": {"signal_rows": list(us_signal_rows), "missing_items": list(missing_us)},
                },
            }
            st.session_state[snapshot_key] = snapshot
            st.session_state[signature_key] = {
                "_combined": combined_signature,
                "kr": kr_signature,
                "us": us_signature,
            }
            st.session_state[created_at_key] = {
                "_combined": now_text,
                "kr": now_text,
                "us": now_text,
            }
    else:
        legacy_snapshot = not isinstance(market_payloads, dict) or not all(
            isinstance(market_payloads.get(market), dict) for market in ("kr", "us")
        )
        if legacy_snapshot:
            market_payloads = {"kr": None, "us": None}
            action = "legacy_refresh"
        refresh_flags = {
            "kr": force_refresh or legacy_snapshot or signature_map.get("kr") != kr_signature or policy["refresh_kr_snapshot"],
            "us": force_refresh or legacy_snapshot or signature_map.get("us") != us_signature or policy["refresh_us_snapshot"],
        }
        if action == "reuse" and any(refresh_flags.values()):
            action = "market_refresh"

        for market_key, items_tuple, market_signature in (
            ("kr", favorites_tuple, kr_signature),
            ("us", us_watchlist_tuple, us_signature),
        ):
            payload = market_payloads.get(market_key) if isinstance(market_payloads, dict) else None
            payload_valid = isinstance(payload, dict) and {"signal_rows", "missing_items"}.issubset(payload.keys())
            if not refresh_flags[market_key] and not payload_valid:
                refresh_flags[market_key] = True
                action = "repair_refresh"
            if refresh_flags[market_key]:
                signal_rows, missing_items, _shape = _build_signal_market_rows(
                    items_tuple,
                    market_key,
                    chart_mode,
                    yf_interval,
                    higher_interval,
                    data_start,
                    data_end,
                    bb_window=bb_window,
                    bb_std=bb_std,
                    rsi_period=rsi_period,
                    rsi_buy_center=rsi_buy_center,
                    rsi_sell_center=rsi_sell_center,
                    rsi_band=rsi_band,
                    rsi_lookback=rsi_lookback,
                    persist=persist,
                    phase2_rsi=phase2_rsi,
                )
                market_payloads[market_key] = {
                    "signal_rows": list(signal_rows),
                    "missing_items": list(missing_items),
                }
                signature_map[market_key] = market_signature
                created_at_map[market_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        signature_map["_combined"] = combined_signature
        created_at_map["_combined"] = max(
            [v for v in (created_at_map.get("kr"), created_at_map.get("us")) if isinstance(v, str)],
            default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        snapshot = _compose_signal_snapshot_from_market_payloads(market_payloads)
        st.session_state[snapshot_key] = snapshot
        st.session_state[signature_key] = signature_map
        st.session_state[created_at_key] = created_at_map

    _signal_debug_log(
        "signal_table_snapshot",
        action=action,
        chart_mode=chart_mode,
        favorites=len(favorites_tuple),
        us_favorites=len(us_watchlist_tuple),
        interval=yf_interval if chart_mode == "분봉" else higher_interval,
        auto_refresh=auto_refresh,
        kr_active=policy["kr_active"],
        us_active=policy["us_active"],
        refresh_kr=policy["refresh_kr_snapshot"],
        refresh_us=policy["refresh_us_snapshot"],
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    created_state = st.session_state.get(created_at_key, "")
    if isinstance(created_state, dict):
        created_value = created_state.get("_combined", "")
    else:
        created_value = created_state
    return snapshot, created_value


def _single_tf_badge_html(sig: dict | None):
    if not sig:
        return _badge("─", "#666", "#111113", "rgba(255,255,255,0.06)")
    if sig.get('dyn_buy_signal'):
        return _badge("★ 매수", "#4BFFB3", "#0a2b1e", "rgba(75,255,179,0.3)")
    if sig.get('dyn_buy_flag'):
        return _badge("▲ 플래그", "#7AAFD4", "#0a1520", "rgba(120,175,212,0.2)")
    if sig.get('dyn_holding'):
        return _badge("보유", "#C8C850", "#1c1c08", "rgba(200,200,80,0.3)")
    if sig.get('dyn_sell_signal'):
        return _badge("★ 매도", "#FF4B6E", "#2d0d1a", "rgba(255,75,110,0.25)")
    if sig.get('dyn_sell_flag'):
        return _badge("▼ 플래그", "#E08A3A", "#221207", "rgba(224,138,58,0.2)")
    return _badge("─", "#666", "#111113", "rgba(255,255,255,0.06)")


def render_signal_table(signal_rows, market=None, current_chart_mode=None, current_intra_interval=None):
    from urllib.parse import quote_plus

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
        if ENABLE_SIGNAL_TABLE_TF_BADGES:
            tf_signals = row.get('tf_signals') or {}
            tf_day_badge = _single_tf_badge_html(tf_signals.get("일봉"))
            tf_week_badge = _single_tf_badge_html(tf_signals.get("주봉"))
            tf_month_badge = _single_tf_badge_html(tf_signals.get("월봉"))
        else:
            tf_day_badge = _single_tf_badge_html(None)
            tf_week_badge = _single_tf_badge_html(None)
            tf_month_badge = _single_tf_badge_html(None)

        _name_html = row['name']
        if ENABLE_SIGNAL_TABLE_ROW_LINKS and market in {"kr", "us"}:
            _params = [
                ("scan_market", market),
                ("scan_code", row["code"]),
            ]
            if current_chart_mode:
                _params.append(("chart_mode", current_chart_mode))
                if current_chart_mode == "분봉" and current_intra_interval:
                    _params.append(("intra_interval", current_intra_interval))
            _scan_href = "?" + "&".join(f"{k}={quote_plus(str(v))}" for k, v in _params)
            _name_html = (
                f'<a href="{_scan_href}" style="color:#EDEDED;text-decoration:none;display:block;">'
                f'{star}{row["name"]}'
                f'</a>'
            )
        else:
            _name_html = f"{star}{row['name']}"

        rows_html.append(f"""
        <tr style="background:{row_bg};border-bottom:1px solid rgba(255,255,255,0.04);">
            <td style="padding:2px 14px;font-size:13px;color:#EDEDED;font-weight:500;white-space:nowrap;">{_name_html}</td>
            <td style="padding:2px 14px;font-size:13px;color:#EDEDED;text-align:right;font-variant-numeric:tabular-nums;">{close_str}</td>
            <td style="padding:2px 14px;font-size:13px;color:{pct_color};text-align:right;font-variant-numeric:tabular-nums;">{pct_str}</td>
            <td style="padding:2px 14px;font-size:13px;color:{rsi_color};text-align:right;font-variant-numeric:tabular-nums;">{rsi_str}</td>
            <td style="padding:2px 14px;">{badges}</td>
            <td style="padding:2px 10px;text-align:center;">{tf_day_badge}</td>
            <td style="padding:2px 10px;text-align:center;">{tf_week_badge}</td>
            <td style="padding:2px 10px;text-align:center;">{tf_month_badge}</td>
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
                <th style="padding:8px 10px;font-size:10px;color:#555;font-weight:600;text-align:center;text-transform:uppercase;letter-spacing:0.8px;">일봉</th>
                <th style="padding:8px 10px;font-size:10px;color:#555;font-weight:600;text-align:center;text-transform:uppercase;letter-spacing:0.8px;">주봉</th>
                <th style="padding:8px 10px;font-size:10px;color:#555;font-weight:600;text-align:center;text-transform:uppercase;letter-spacing:0.8px;">월봉</th>
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
def _fred(series_id: str, years: int = 5, sync_bucket: str | None = None) -> pd.Series:
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
def _credit_spread_series(series_id: str, years: int = 5, sync_bucket: str | None = None) -> pd.Series:
    """HY/IG OAS는 최근 3년 원본 + 이전 구간은 장기 프록시로 이어 붙여 반환."""
    exact = _fred(series_id, years, sync_bucket=sync_bucket)
    proxy_meta = _CREDIT_SPREAD_PROXY_MAP.get(series_id)
    if proxy_meta is None:
        return exact

    corp_id, treasury_id, label = proxy_meta
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    fetch_years = max(years + 2, 6)
    corp_yield = _fred(corp_id, fetch_years, sync_bucket=sync_bucket)
    treasury_yield = _fred(treasury_id, fetch_years, sync_bucket=sync_bucket)
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
def _yf_close(ticker: str, years: int = 5, sync_bucket: str | None = None) -> pd.Series:
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


def _macro_sync_bucket(minutes: int = 60) -> str:
    minutes = max(5, int(minutes))
    ts = pd.Timestamp.now().floor(f"{minutes}min")
    return ts.strftime("%Y%m%d%H%M")


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


def _tune_macro_main_chart(fig: go.Figure | None):
    """매크로 메인 페이지 전용 차트 타이포/여백 미세 조정."""
    if fig is None:
        return None
    fig.update_layout(
        title=dict(font=dict(size=14, color='#B5B5B5'), x=0, y=0.985),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.08,
            xanchor='right',
            x=1,
            font=dict(size=10),
            bgcolor='rgba(0,0,0,0)',
        ),
        margin=dict(l=50, r=20, t=56, b=36),
    )
    return fig


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


def _korean_credit_proxy_series(years: int, quality: str = 'AA', sync_bucket: str | None = None) -> pd.Series:
    treasury_3y = _yf_close('114260.KS', years + 1, sync_bucket=sync_bucket)   # KODEX 국고채3년
    corp_map = {
        'AA': ('273130.KS', '종합채권(AA-이상)'),
        'A': ('385540.KS', '종합채권(A-이상)'),
    }
    corp_ticker, _ = corp_map.get(quality, corp_map['AA'])
    corp = _yf_close(corp_ticker, years + 1, sync_bucket=sync_bucket)
    return _relative_strength_spread(treasury_3y, corp)


def _korean_fx_stress_series(years: int, sync_bucket: str | None = None) -> pd.Series:
    return _yf_close('KRW=X', years + 1, sync_bucket=sync_bucket)


def _korean_volatility_series(years: int, benchmark_s: pd.Series | None = None, window: int = 20, sync_bucket: str | None = None) -> pd.Series:
    if benchmark_s is None or benchmark_s.empty:
        benchmark_s = _yf_close('^KS11', years + 1, sync_bucket=sync_bucket)
    return _realized_volatility(benchmark_s, window=window)


def _korean_vol_term_spread_series(years: int, benchmark_s: pd.Series | None = None, sync_bucket: str | None = None) -> pd.Series:
    if benchmark_s is None or benchmark_s.empty:
        benchmark_s = _yf_close('^KS11', years + 1, sync_bucket=sync_bucket)
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


def _add_price_signal_markers(fig, signal_df: pd.DataFrame, price_s: pd.Series, yaxis='y2', prefix='리스크 사이클'):
    """신호 마커를 가격 오버레이 축 위에 표시한다."""
    if signal_df is None or signal_df.empty or price_s is None or price_s.empty:
        return

    start_marker_color = 'rgba(210,55,55,0.95)'
    end_marker_color = 'rgba(80,160,255,0.92)'

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
            marker=dict(symbol='triangle-down', size=9, color=start_marker_color),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>리스크 시작<extra></extra>',
        ))
    if not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name=f'{prefix} 종료',
            mode='markers', yaxis=yaxis,
            marker=dict(symbol='triangle-up', size=9, color=end_marker_color),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>리스크 종료<extra></extra>',
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
    """단일 지표의 리스크 사이클 상태를 계산한다."""
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
    """EMA 기반 리스크 시작/종료 이벤트를 추가."""
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
            x=sig1_start.index, y=sig1_start, name=f'1: 리스크 시작 ({start_count}/5 하락 + EMA{ema_span}<{ema_compare_days}D전)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=8, color='rgba(210,55,55,0.90)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>최근 5일 중 slope < -0.5*{std_window}일 std 가 {start_count}일 이상<br>현재 EMA{ema_span} < {ema_compare_days}일 전 EMA{ema_span}<extra></extra>',
        ))
    if not sig1_end.empty:
        fig.add_trace(go.Scatter(
            x=sig1_end.index, y=sig1_end, name=f'1: 리스크 종료 ({end_count}/5 상승 + EMA{ema_span}>{ema_compare_days}D전)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=8, color='rgba(80,160,255,0.90)'),
            hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>최근 5일 중 slope > +0.5*{std_window}일 std 가 {end_count}일 이상<br>현재 EMA{ema_span} > {ema_compare_days}일 전 EMA{ema_span}<extra></extra>',
        ))


def _add_threshold_ema_signals(fig, s: pd.Series, threshold: float, ema_span: int = 20,
                               overlay_price=None, overlay_yaxis='y2', prefix='리스크 사이클'):
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
                marker=dict(symbol='triangle-down', size=8, color='rgba(210,55,55,0.92)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(80,160,255,0.92)'),
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
    prefix='리스크 사이클',
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
                marker=dict(symbol='triangle-down', size=8, color='rgba(210,55,55,0.92)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(80,160,255,0.92)'),
            ))


def _compute_dynamic_quantile_signal_frame(
    s: pd.Series,
    window: int = 126,
    start_quantile: float = 0.4,
    end_quantile: float = 0.2,
    ema_span: int = 20,
) -> pd.DataFrame:
    """동적 분위수 라인 기반 리스크 사이클 상태를 계산한다."""
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
    prefix='리스크 사이클',
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
        line=dict(color='rgba(216,195,106,0.32)', width=1.1),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>EMA{int(ema_span)}  %{{y:.2f}}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df['risk_start_line'],
        name=f'시작선 Q{start_pct}',
        line=dict(color='rgba(255,140,105,0.55)', width=1.2, dash='dot'),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>리스크 시작선 (Q{start_pct})  %{{y:.2f}}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=signal_df.index, y=signal_df['risk_end_line'],
        name=f'종료선 Q{end_pct}',
        line=dict(color='rgba(120,220,255,0.60)', width=1.2, dash='dot'),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>리스크 종료선 (Q{end_pct})  %{{y:.2f}}<extra></extra>',
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
                marker=dict(symbol='triangle-down', size=8, color='rgba(210,55,55,0.92)'),
            ))
        if not sig_end.empty:
            fig.add_trace(go.Scatter(
                x=sig_end.index, y=sig_end, name=f'{prefix} 종료',
                mode='markers',
                marker=dict(symbol='triangle-up', size=8, color='rgba(80,160,255,0.92)'),
            ))


def _compute_combo_downturn_frame(parts: dict[str, pd.Series], params=None) -> pd.DataFrame:
    """0~4 개별 리스크 상태를 합성한 종합 하락 사이클 상태를 계산한다."""
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
                                 ema_span: int | None = None, sync_bucket: str | None = None):
    """⓪ 선택 지수 자체의 EMA 기반 리스크 사이클."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if spx_s is None or spx_s.empty:
        spx_s = _yf_close(benchmark['code'], years, sync_bucket=sync_bucket)
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
        **_ml(f'⓪ {benchmark["label"]} 지수 리스크 사이클', height=300),
    )
    return fig


def make_macro_combo_downturn_chart(years: int = 5, spx_s=None, signal_modes=None, downturn_params=None, benchmark_name='S&P500'):
    """⑤ 0~4 종합 리스크 사이클."""
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
        title = f'⑤ 종합 리스크 사이클 (KOSPI 한국형 5지표 조합, {benchmark["label"]} 위 표시)'
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
        title = f'⑤ 종합 리스크 사이클 (0~4 조합, {benchmark["label"]} 위 시작/종료 표시)'

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
            x=risk_start_y.index, y=risk_start_y, name='⑤ 리스크 시작 (4/5)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(255,75,110,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>리스크 시작: active_down_count >= 4<extra></extra>',
        ))
    if show_risk and not risk_end_y.empty:
        fig.add_trace(go.Scatter(
            x=risk_end_y.index, y=risk_end_y, name='⑤ 리스크 종료 (3/5)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>리스크 종료: active_down_count <= 3<extra></extra>',
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
    "4": "④ VIX",
    "6": "⑥ VIX 스프레드",
}


def _get_macro2_dynamic_defaults():
    return {
        "0": {"label": "⓪ 지수", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "1": {"label": "① HY", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "2": {"label": "② IG", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "3": {"label": "③ 신용스트레스", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "4": {"label": "④ VIX", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
        "6": {"label": "⑥ VIX 스프레드", "ema": 20, "window": 126, "start": 0.40, "end": 0.20},
    }


def _macro_dynamic_cfg_signature(cfgs: dict, codes=None) -> str:
    codes = list(codes or cfgs.keys())
    parts = []
    for code in codes:
        cfg = cfgs.get(code)
        if not cfg:
            continue
        parts.append(
            f"{code}-E{int(cfg['ema'])}-W{int(cfg['window'])}-S{int(round(float(cfg['start']) * 100))}-X{int(round(float(cfg['end']) * 100))}"
        )
    return "__".join(parts)


def _macro2_debug_name(code: str) -> str:
    return {
        "0": "Index",
        "1": "HY",
        "2": "IG",
        "3": "CreditStress",
        "4": "VIX",
        "6": "VIXSpread",
    }.get(str(code), str(code))


def _make_combo_slug(benchmark_name: str, selected_codes, cfgs: dict, combo_k: int) -> str:
    ordered_codes = list(selected_codes or [])
    signature = _macro_dynamic_cfg_signature(cfgs, ordered_codes)
    raw = f"{benchmark_name}_{'_'.join(ordered_codes)}_k{combo_k}_{signature}"
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', raw).strip('-').lower()
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"{safe[:96]}_{digest}"


def _macro_combo_warmup_years(visible_years: int, cfgs: dict, selected_codes) -> int:
    codes = list(selected_codes or [])
    windows = [int(cfgs[code]["window"]) for code in codes if code in cfgs and "window" in cfgs[code]]
    ema_spans = [int(cfgs[code]["ema"]) for code in codes if code in cfgs and "ema" in cfgs[code]]
    max_window = max(windows) if windows else 252
    max_ema = max(ema_spans) if ema_spans else 20
    extra_years = max(2, int(np.ceil(max_window / 252.0)) + int(np.ceil(max_ema / 252.0)) + 1)
    return int(visible_years) + extra_years


def _build_macro2_dynamic_charts(years: int, spx_s, show_raw: bool, benchmark_name: str, cfgs: dict, sync_bucket: str | None = None):
    _started = time.perf_counter()
    charts = [
        make_macro_index_cycle_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["0"]["ema"],
            dynamic_window=cfgs["0"]["window"],
            dynamic_start_quantile=cfgs["0"]["start"],
            dynamic_end_quantile=cfgs["0"]["end"],
            sync_bucket=sync_bucket,
        ),
        make_macro_hy_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["1"]["ema"],
            dynamic_window=cfgs["1"]["window"],
            dynamic_start_quantile=cfgs["1"]["start"],
            dynamic_end_quantile=cfgs["1"]["end"],
            sync_bucket=sync_bucket,
        ),
        make_macro_ig_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["2"]["ema"],
            dynamic_window=cfgs["2"]["window"],
            dynamic_start_quantile=cfgs["2"]["start"],
            dynamic_end_quantile=cfgs["2"]["end"],
            sync_bucket=sync_bucket,
        ),
        make_macro_credit_stress_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["3"]["ema"],
            dynamic_window=cfgs["3"]["window"],
            dynamic_start_quantile=cfgs["3"]["start"],
            dynamic_end_quantile=cfgs["3"]["end"],
            sync_bucket=sync_bucket,
        ),
        make_macro_options_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["4"]["ema"],
            dynamic_window=cfgs["4"]["window"],
            dynamic_start_quantile=cfgs["4"]["start"],
            dynamic_end_quantile=cfgs["4"]["end"],
            sync_bucket=sync_bucket,
        ),
        make_macro_vix_spread_chart(
            years, spx_s, show_raw, benchmark_name=benchmark_name,
            dynamic_mode=True, ema_span=cfgs["6"]["ema"],
            dynamic_window=cfgs["6"]["window"],
            dynamic_start_quantile=cfgs["6"]["start"],
            dynamic_end_quantile=cfgs["6"]["end"],
            sync_bucket=sync_bucket,
        ),
    ]
    _macro_debug_log(
        "build_macro2_dynamic_charts",
        benchmark_name=benchmark_name,
        years=years,
        chart_count=len(charts),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return charts


def _get_macro2_signal_series(signal_code: str, years: int, benchmark_name: str = 'S&P500', spx_s=None, sync_bucket: str | None = None) -> pd.Series:
    benchmark = _get_macro_benchmark(benchmark_name)
    if signal_code == "0":
        if spx_s is None or spx_s.empty:
            spx_s = _yf_close(benchmark['code'], years, sync_bucket=sync_bucket)
        return spx_s.dropna() if spx_s is not None else pd.Series(dtype=float)

    if signal_code == "1":
        if benchmark['kind'] == 'kr':
            hy = _korean_credit_proxy_series(years, 'A', sync_bucket=sync_bucket)
        else:
            hy = _credit_spread_series('BAMLH0A0HYM2', years, sync_bucket=sync_bucket)
        return (-hy).dropna() if hy is not None else pd.Series(dtype=float)

    if signal_code == "2":
        if benchmark['kind'] == 'kr':
            ig = _korean_credit_proxy_series(years, 'AA', sync_bucket=sync_bucket)
        else:
            ig = _credit_spread_series('BAMLC0A0CM', years, sync_bucket=sync_bucket)
        return (-ig).dropna() if ig is not None else pd.Series(dtype=float)

    if signal_code == "3":
        parts = []
        if benchmark['kind'] == 'kr':
            hy = _korean_credit_proxy_series(years + 1, 'A', sync_bucket=sync_bucket)
            ig = _korean_credit_proxy_series(years + 1, 'AA', sync_bucket=sync_bucket)
            fx = _korean_fx_stress_series(years + 1, sync_bucket=sync_bucket)
            hv20 = _korean_volatility_series(years + 1, benchmark_s=spx_s, window=20, sync_bucket=sync_bucket)
            if not hy.empty:
                parts.append(_zscore(hy).rename('CorpA'))
            if not ig.empty:
                parts.append(_zscore(ig).rename('CorpAA'))
            if not fx.empty:
                parts.append(_zscore(fx).rename('USDKRW'))
            if not hv20.empty:
                parts.append(_zscore(hv20).rename('HV20'))
        else:
            hy = _credit_spread_series('BAMLH0A0HYM2', years + 1, sync_bucket=sync_bucket)
            nfci = _fred('NFCI', years + 1, sync_bucket=sync_bucket)
            vix = _yf_close('^VIX', years + 1, sync_bucket=sync_bucket)
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
            vol = _korean_volatility_series(years, benchmark_s=spx_s, window=20, sync_bucket=sync_bucket)
        else:
            vol = _yf_close('^VIX', years, sync_bucket=sync_bucket)
        return (-vol).dropna() if vol is not None else pd.Series(dtype=float)

    if signal_code == "6":
        if benchmark['kind'] == 'kr':
            spread = _korean_vol_term_spread_series(years, benchmark_s=spx_s, sync_bucket=sync_bucket)
        else:
            vix = _yf_close('^VIX', years, sync_bucket=sync_bucket)
            vix3m = _yf_close('^VIX3M', years, sync_bucket=sync_bucket)
            if vix.empty or vix3m.empty:
                return pd.Series(dtype=float)
            spread = (vix - vix3m.reindex(vix.index)).dropna()
        return (-spread).dropna() if spread is not None else pd.Series(dtype=float)

    return pd.Series(dtype=float)


def _compute_macro_combo_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    selected_codes,
    cfgs: dict,
    combo_k: int,
    sync_bucket: str | None = None,
):
    if spx_s is None or spx_s.empty:
        return pd.DataFrame(), []

    selected_codes = list(selected_codes or [])
    if not selected_codes:
        return pd.DataFrame(), []

    frames = {}
    active_codes = []
    for code in selected_codes:
        fetch_years = max(1, int(np.ceil(len(spx_s.dropna()) / 252.0)) + 1)
        series = _get_macro2_signal_series(code, fetch_years, benchmark_name=benchmark_name, spx_s=spx_s, sync_bucket=sync_bucket)
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
        frames[code] = signal_df[["down_start_signal", "down_end_signal"]].rename(columns={
            "down_start_signal": f"{code}_start_signal",
            "down_end_signal": f"{code}_end_signal",
        })
        active_codes.append(code)

    if not frames:
        return pd.DataFrame(), []

    spx_aligned = spx_s.dropna().copy()
    if spx_aligned.empty:
        return pd.DataFrame(), []

    combo = pd.DataFrame(index=spx_aligned.index.copy())
    start_cols = [f"{code}_start_signal" for code in active_codes]
    end_cols = [f"{code}_end_signal" for code in active_codes]
    signal_frame = pd.concat(frames.values(), axis=1).sort_index()
    signal_frame = signal_frame.reindex(spx_aligned.index).fillna(False).astype(bool)

    indicator_states = {code: False for code in active_codes}
    flag_cols = [f"{code}_down_flag" for code in active_codes]
    for code in active_codes:
        combo[f"{code}_start_signal"] = signal_frame[f"{code}_start_signal"]
        combo[f"{code}_end_signal"] = signal_frame[f"{code}_end_signal"]
        combo[f"{code}_down_flag"] = False

    combo_k = max(1, min(int(combo_k), len(flag_cols)))
    combo["active_count"] = 0
    combo["combo_risk_state"] = False
    combo["combo_start_signal"] = False
    combo["combo_end_signal"] = False

    combo_in_cycle = False
    for idx in combo.index:
        for code in active_codes:
            start_hit = bool(combo.at[idx, f"{code}_start_signal"])
            end_hit = bool(combo.at[idx, f"{code}_end_signal"])
            if start_hit:
                indicator_states[code] = True
            elif end_hit:
                indicator_states[code] = False
            combo.at[idx, f"{code}_down_flag"] = indicator_states[code]

        active_count = sum(1 for code in active_codes if indicator_states[code])
        combo.at[idx, "active_count"] = active_count

        if not combo_in_cycle and active_count >= combo_k:
            combo_in_cycle = True
            combo.at[idx, "combo_start_signal"] = True
        elif combo_in_cycle and active_count < combo_k:
            combo_in_cycle = False
            combo.at[idx, "combo_end_signal"] = True

        combo.at[idx, "combo_risk_state"] = combo_in_cycle

    combo["active_count"] = combo["active_count"].astype(int)
    combo[flag_cols + start_cols + end_cols + ["combo_risk_state", "combo_start_signal", "combo_end_signal"]] = (
        combo[flag_cols + start_cols + end_cols + ["combo_risk_state", "combo_start_signal", "combo_end_signal"]]
        .astype(bool)
    )
    return combo, active_codes


def _build_macro_combo_event_df(
    combo: pd.DataFrame,
    active_codes,
    benchmark_name: str,
    selected_codes,
    cfgs: dict,
    combo_k: int,
) -> pd.DataFrame:
    if combo is None or combo.empty:
        return pd.DataFrame()

    ordered_codes = [code for code in list(selected_codes or []) if code in active_codes]
    event_df = combo.copy().rename_axis("date").reset_index()
    event_df["date"] = pd.to_datetime(event_df["date"])
    event_df["prev_active_count"] = event_df["active_count"].shift(1).fillna(0).astype(int)
    event_df["combo_state_before"] = event_df["combo_risk_state"].shift(1).fillna(False).astype(bool)

    flag_cols = []
    label_cols = []
    for code in ordered_codes:
        source_col = f"{code}_down_flag"
        start_col = f"{code}_start_signal"
        end_col = f"{code}_end_signal"
        label = _macro2_debug_name(code)
        target_col = f"{label}_flag"
        target_start_col = f"{label}_start_signal"
        target_end_col = f"{label}_end_signal"
        if source_col in event_df.columns:
            event_df[target_col] = event_df[source_col].astype(bool)
            flag_cols.append(target_col)
            label_cols.append((code, label, target_col))
        if start_col in event_df.columns:
            event_df[target_start_col] = event_df[start_col].astype(bool)
        if end_col in event_df.columns:
            event_df[target_end_col] = event_df[end_col].astype(bool)

    def _flag_names(row, expect_true: bool) -> str:
        names = [label for _code, label, col in label_cols if bool(row.get(col, False)) is expect_true]
        return ", ".join(names)

    def _flag_binary(row) -> str:
        return "/".join(["1" if bool(row.get(col, False)) else "0" for _code, _label, col in label_cols])

    event_df["active_flags"] = event_df.apply(lambda r: _flag_names(r, True), axis=1)
    event_df["inactive_flags"] = event_df.apply(lambda r: _flag_names(r, False), axis=1)
    event_df["prev_active_flags"] = event_df["active_flags"].shift(1).fillna("")
    event_df["prev_inactive_flags"] = event_df["inactive_flags"].shift(1).fillna("")
    event_df["flag_state_string"] = event_df.apply(_flag_binary, axis=1)
    event_df["selected_codes"] = ",".join(ordered_codes)
    event_df["selected_labels"] = ", ".join([_MACRO2_SIGNAL_LABELS.get(code, code) for code in ordered_codes])
    event_df["benchmark_name"] = benchmark_name
    event_df["combo_k"] = int(combo_k)
    event_df["combo_n"] = len(ordered_codes)
    event_df["initial_state_at_visible_start"] = bool(event_df["combo_risk_state"].iloc[0]) if not event_df.empty else False
    event_df["combo_slug"] = _make_combo_slug(benchmark_name, ordered_codes, cfgs, combo_k)
    event_df["param_signature"] = " | ".join(
        [
            f"{_macro2_debug_name(code)}=EMA{int(cfgs[code]['ema'])}_W{int(cfgs[code]['window'])}_S{int(round(float(cfgs[code]['start']) * 100))}_E{int(round(float(cfgs[code]['end']) * 100))}"
            for code in ordered_codes
            if code in cfgs
        ]
    )
    event_df["combo_label"] = " + ".join([_macro2_debug_name(code) for code in ordered_codes])
    return event_df


def _extract_combo_marker_dates(fig: go.Figure):
    start_dates = []
    end_dates = []
    start_counts = {}
    end_counts = {}

    for trace in fig.data:
        trace_name = str(getattr(trace, "name", "") or "")
        legend_group = str(getattr(trace, "legendgroup", "") or "")
        x_raw = getattr(trace, "x", None)
        x_iter = [] if x_raw is None else list(x_raw)
        x_vals = [pd.Timestamp(x).normalize() for x in x_iter if x is not None]
        if trace_name == "__COMBO_START_MARKER__" or legend_group == "__COMBO_START_MARKER__":
            for dt in x_vals:
                start_dates.append(dt)
                start_counts[dt] = start_counts.get(dt, 0) + 1
        elif trace_name == "__COMBO_END_MARKER__" or legend_group == "__COMBO_END_MARKER__":
            for dt in x_vals:
                end_dates.append(dt)
                end_counts[dt] = end_counts.get(dt, 0) + 1

    return start_dates, end_dates, start_counts, end_counts


def _evaluate_combo_cycle_invariants(combo_event_df: pd.DataFrame) -> dict:
    if combo_event_df is None or combo_event_df.empty:
        return {
            "start_transition_fail_count": 0,
            "end_transition_fail_count": 0,
            "event_order_fail_count": 0,
            "cycle_invariant_fail_count": 0,
            "cycle_invariant_status": "PASS",
        }

    starts = combo_event_df["combo_start_signal"].fillna(False)
    ends = combo_event_df["combo_end_signal"].fillna(False)
    before = combo_event_df["combo_state_before"].fillna(False)
    after = combo_event_df["combo_risk_state"].fillna(False)

    start_transition_fail_count = int((starts & (before | ~after)).sum())
    end_transition_fail_count = int((ends & (~before | after)).sum())

    event_order_fail_count = 0
    in_cycle = False
    event_rows = combo_event_df.loc[starts | ends, ["combo_start_signal", "combo_end_signal"]]
    for _, row in event_rows.iterrows():
        start_hit = bool(row["combo_start_signal"])
        end_hit = bool(row["combo_end_signal"])
        if start_hit and end_hit:
            event_order_fail_count += 1
            continue
        if start_hit:
            if in_cycle:
                event_order_fail_count += 1
            in_cycle = True
        elif end_hit:
            if not in_cycle:
                event_order_fail_count += 1
            in_cycle = False

    cycle_invariant_fail_count = start_transition_fail_count + end_transition_fail_count + event_order_fail_count
    return {
        "start_transition_fail_count": start_transition_fail_count,
        "end_transition_fail_count": end_transition_fail_count,
        "event_order_fail_count": event_order_fail_count,
        "cycle_invariant_fail_count": cycle_invariant_fail_count,
        "cycle_invariant_status": "PASS" if cycle_invariant_fail_count == 0 else "FAIL",
    }


def _build_combo_debug_tables(combo_event_df: pd.DataFrame, fig: go.Figure) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if combo_event_df is None or combo_event_df.empty or fig is None:
        return pd.DataFrame(), pd.DataFrame(), {}

    start_dates_raw, end_dates_raw, start_counts, end_counts = _extract_combo_marker_dates(fig)
    computed_start_dates = [pd.Timestamp(x).normalize() for x in combo_event_df.loc[combo_event_df["combo_start_signal"], "date"]]
    computed_end_dates = [pd.Timestamp(x).normalize() for x in combo_event_df.loc[combo_event_df["combo_end_signal"], "date"]]
    plotted_start_dates = sorted(set(start_dates_raw))
    plotted_end_dates = sorted(set(end_dates_raw))

    computed_start_set = set(computed_start_dates)
    computed_end_set = set(computed_end_dates)
    plotted_start_set = set(plotted_start_dates)
    plotted_end_set = set(plotted_end_dates)

    row_map = combo_event_df.set_index(combo_event_df["date"].dt.normalize())
    all_dates = sorted(computed_start_set | computed_end_set | plotted_start_set | plotted_end_set)
    debug_rows = []

    for dt in all_dates:
        row = row_map.loc[dt] if dt in row_map.index else None
        row_dict = row.iloc[0].to_dict() if isinstance(row, pd.DataFrame) else (row.to_dict() if row is not None else {})

        start_expected = dt in computed_start_set
        end_expected = dt in computed_end_set
        start_plotted = dt in plotted_start_set
        end_plotted = dt in plotted_end_set
        start_dup = start_counts.get(dt, 0) > 1
        end_dup = end_counts.get(dt, 0) > 1

        issues = []
        if start_expected and not start_plotted:
            issues.append("MISSING_PLOTTED_MARKER")
        if end_expected and not end_plotted:
            issues.append("MISSING_PLOTTED_MARKER")
        if start_plotted and not start_expected:
            issues.append("UNEXPECTED_PLOTTED_MARKER")
        if end_plotted and not end_expected:
            issues.append("UNEXPECTED_PLOTTED_MARKER")
        if start_dup or end_dup:
            issues.append("DUPLICATE_PLOTTED_MARKER")
        if (start_plotted and end_expected and not start_expected) or (end_plotted and start_expected and not end_expected):
            issues.append("START_END_EVENT_TYPE_MISMATCH")
        if not row_dict and (start_plotted or end_plotted):
            issues.append("MARKER_DATE_NOT_IN_COMPUTED_INDEX")

        expected_event = "START" if start_expected else "END" if end_expected else "NONE"
        actual_event = "START" if start_plotted else "END" if end_plotted else "NONE"
        event_type = expected_event if expected_event != "NONE" else actual_event
        debug_rows.append({
            "date": dt,
            "event_type": event_type,
            "expected_event": expected_event,
            "actual_marker_event": actual_event,
            "prev_active_count": int(row_dict.get("prev_active_count", 0)) if row_dict else np.nan,
            "active_count": int(row_dict.get("active_count", 0)) if row_dict else np.nan,
            "combo_state_before": bool(row_dict.get("combo_state_before", False)) if row_dict else False,
            "combo_state_after": bool(row_dict.get("combo_risk_state", False)) if row_dict else False,
            "active_flags": row_dict.get("active_flags", "") if row_dict else "",
            "inactive_flags": row_dict.get("inactive_flags", "") if row_dict else "",
            "issue_reason": " | ".join(issues),
        })

    debug_df = pd.DataFrame(debug_rows)
    mismatch_df = debug_df[debug_df["issue_reason"] != ""].head(50).copy() if not debug_df.empty else pd.DataFrame()
    invariant_summary = _evaluate_combo_cycle_invariants(combo_event_df)
    summary = {
        "computed_start_count": len(computed_start_dates),
        "plotted_start_marker_count": len(start_dates_raw),
        "start_marker_mismatch_count": int(
            len(computed_start_set.symmetric_difference(plotted_start_set))
            + sum(max(0, c - 1) for c in start_counts.values())
        ),
        "computed_end_count": len(computed_end_dates),
        "plotted_end_marker_count": len(end_dates_raw),
        "end_marker_mismatch_count": int(
            len(computed_end_set.symmetric_difference(plotted_end_set))
            + sum(max(0, c - 1) for c in end_counts.values())
        ),
        **invariant_summary,
    }
    return debug_df, mismatch_df, summary


def _build_combo_local_debug_table(combo_event_df: pd.DataFrame, selected_codes, debug_date, window: int = 15) -> pd.DataFrame:
    if combo_event_df is None or combo_event_df.empty:
        return pd.DataFrame()

    out = combo_event_df.sort_values("date").reset_index(drop=True)
    target = pd.Timestamp(debug_date).normalize()
    date_norm = out["date"].dt.normalize()
    nearest_idx = int((date_norm - target).abs().argmin())
    start_idx = max(0, nearest_idx - int(window))
    end_idx = min(len(out), nearest_idx + int(window) + 1)

    cols = ["date"]
    for code in list(selected_codes or []):
        label = _macro2_debug_name(code)
        for suffix in ["flag", "start_signal", "end_signal"]:
            col = f"{label}_{suffix}"
            if col in out.columns:
                cols.append(col)
    cols.extend([
        "active_count",
        "prev_active_count",
        "combo_risk_state",
        "combo_start_signal",
        "combo_end_signal",
        "prev_active_flags",
        "active_flags",
        "prev_inactive_flags",
        "inactive_flags",
    ])
    return out.loc[start_idx:end_idx - 1, cols].copy()


def _macro_status_circle(on: bool, color_on: str = "#4BFFB3", color_off: str = "rgba(255,255,255,0.18)") -> str:
    color = color_on if bool(on) else color_off
    return (
        f'<span style="display:inline-block;width:10px;height:10px;'
        f'border-radius:50%;background:{color};vertical-align:middle;"></span>'
    )


def _macro_metric_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-"}:
        return None
    if text.endswith("%"):
        text = text[:-1]
    if text.endswith("x"):
        text = text[:-1]
    try:
        return float(text)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _get_macro_signal_latest_date(code: str, years: int, benchmark_name: str = 'S&P500', sync_bucket: str | None = None):
    series = _get_macro2_signal_series(
        code,
        years,
        benchmark_name=benchmark_name,
        spx_s=None,
        sync_bucket=sync_bucket,
    )
    if series is None or series.empty:
        return None
    return series.index.max()


@st.cache_data(show_spinner=False)
def _compute_macro_preset_current_state_cached(preset_cfg: dict, years: int, sync_bucket: str | None = None):
    benchmark_name = preset_cfg.get("benchmark", "S&P500")
    benchmark = _get_macro_benchmark(benchmark_name)
    spx_s = _yf_close(benchmark["code"], years, sync_bucket=sync_bucket)
    if spx_s is None or spx_s.empty:
        return None

    meta_cfg = preset_cfg.get("meta")
    if meta_cfg:
        combo_a_cfg = meta_cfg.get("combo_a", {})
        combo_b_cfg = meta_cfg.get("combo_b", {})
        combo_a_combo, combo_a_active = _compute_macro_combo_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            selected_codes=combo_a_cfg.get("selected_codes", []),
            cfgs=combo_a_cfg.get("cfgs", {}),
            combo_k=int(combo_a_cfg.get("combo_k", 1)),
            sync_bucket=sync_bucket,
        )
        combo_b_combo, combo_b_active = _compute_macro_combo_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            selected_codes=combo_b_cfg.get("selected_codes", []),
            cfgs=combo_b_cfg.get("cfgs", {}),
            combo_k=int(combo_b_cfg.get("combo_k", 1)),
            sync_bucket=sync_bucket,
        )
        combo_a_event_df = _build_macro_combo_event_df(
            combo=combo_a_combo,
            active_codes=combo_a_active,
            benchmark_name=benchmark_name,
            selected_codes=combo_a_cfg.get("selected_codes", []),
            cfgs=combo_a_cfg.get("cfgs", {}),
            combo_k=int(combo_a_cfg.get("combo_k", 1)),
        )
        combo_b_event_df = _build_macro_combo_event_df(
            combo=combo_b_combo,
            active_codes=combo_b_active,
            benchmark_name=benchmark_name,
            selected_codes=combo_b_cfg.get("selected_codes", []),
            cfgs=combo_b_cfg.get("cfgs", {}),
            combo_k=int(combo_b_cfg.get("combo_k", 1)),
        )
        meta_event_df = _build_macro_meta_combo_event_df(
            combo_a_event_df=combo_a_event_df,
            combo_b_event_df=combo_b_event_df,
            combo_a_label="조합 A",
            combo_b_label="조합 B",
            benchmark_name=benchmark_name,
            exit_mode=str(meta_cfg.get("exit_mode", "AND_EXIT")),
            start_persist=int(meta_cfg.get("start_persist", 1)),
            end_persist=int(meta_cfg.get("end_persist", 1)),
            min_hold_days=int(meta_cfg.get("min_hold_days", 0)),
            cooldown_days=int(meta_cfg.get("cooldown_days", 0)),
        )
        if meta_event_df is None or meta_event_df.empty:
            return None
        latest = meta_event_df.sort_values("date").iloc[-1]
        a_on = bool(latest.get("a_state", False))
        b_on = bool(latest.get("b_state", False))
        return {
            "is_on": bool(latest.get("combo_risk_state", False)),
            "on_count": int(a_on) + int(b_on),
            "total_count": 2,
            "start_count": 2,
        }

    combo, active_codes = _compute_macro_combo_signal_frame(
        spx_s=spx_s,
        benchmark_name=benchmark_name,
        selected_codes=preset_cfg.get("selected_codes", []),
        cfgs=preset_cfg.get("cfgs", {}),
        combo_k=int(preset_cfg.get("combo_k", 1)),
        sync_bucket=sync_bucket,
    )
    combo_event_df = _build_macro_combo_event_df(
        combo=combo,
        active_codes=active_codes,
        benchmark_name=benchmark_name,
        selected_codes=preset_cfg.get("selected_codes", []),
        cfgs=preset_cfg.get("cfgs", {}),
        combo_k=int(preset_cfg.get("combo_k", 1)),
    )
    if combo_event_df is None or combo_event_df.empty:
        return None
    latest = combo_event_df.sort_values("date").iloc[-1]
    return {
        "is_on": bool(latest.get("combo_risk_state", False)),
        "on_count": int(latest.get("active_count", 0)),
        "total_count": int(latest.get("combo_n", max(1, len(active_codes)))),
        "start_count": int(latest.get("combo_k", preset_cfg.get("combo_k", 1))),
    }


def _compute_macro_preset_current_state(preset_cfg: dict, years: int, sync_bucket: str | None = None):
    _started = time.perf_counter()
    preset_name = str(preset_cfg.get("label") or preset_cfg.get("benchmark") or "unknown")
    benchmark_name = preset_cfg.get("benchmark", "S&P500")
    meta_cfg = preset_cfg.get("meta")
    _macro_debug_log(
        "compute_macro_preset_current_state_start",
        preset_key=preset_name,
        benchmark_name=benchmark_name,
        years=years,
        is_meta=bool(meta_cfg),
    )
    result = _compute_macro_preset_current_state_cached(
        preset_cfg=preset_cfg,
        years=years,
        sync_bucket=sync_bucket,
    )
    _macro_debug_log(
        "compute_macro_preset_current_state_end",
        preset_key=preset_name,
        benchmark_name=benchmark_name,
        years=years,
        is_meta=bool(meta_cfg),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
        has_result=result is not None,
    )
    return result


def _resolve_macro_backtest_preset_cfg(key: str, preset_defs: dict | None):
    if not preset_defs:
        return None
    direct = preset_defs.get(key)
    if direct:
        return direct
    if key == "nasdaq_common":
        base = preset_defs.get("common")
        if base:
            resolved = copy.deepcopy(base)
            resolved["benchmark"] = "Nasdaq"
            return resolved
    return None


def _macro_date_text(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _macro_on_k_text(on_count: int, start_k: int) -> str:
    return f"{max(0, int(on_count))}/K{max(1, int(start_k))}"


def _macro_flag_ratio_html(on_count: int, start_k: int, is_on: bool | None = None) -> str:
    k_value = max(1, int(start_k))
    on = max(0, int(on_count))
    if is_on is not None:
        color = "#FF8C69" if bool(is_on) else "#66D9B8"
    else:
        color = "#FF8C69" if on >= k_value else "#66D9B8"
    return (
        f"<span style='color:{color};font-weight:700;font-variant-numeric:tabular-nums;'>"
        f"{_macro_on_k_text(on, k_value)}</span>"
    )


def _build_macro_combo_status_panel(
    benchmark_name: str,
    years: int,
    spx_s: pd.Series,
    selected_codes,
    combo_event_df: pd.DataFrame,
    sync_bucket: str | None = None,
):
    _started = time.perf_counter()
    selected_codes = list(selected_codes or [])
    if combo_event_df is None or combo_event_df.empty:
        return "", ""

    latest_row = combo_event_df.sort_values("date").iloc[-1]
    combo_state = bool(latest_row.get("combo_risk_state", False))
    active_count = int(latest_row.get("active_count", 0))
    combo_n = int(latest_row.get("combo_n", len(selected_codes)))
    combo_k = int(latest_row.get("combo_k", max(1, combo_n)))
    basis_date = _macro_date_text(latest_row.get("date"))
    status_text = "리스크 사이클 ON" if combo_state else "리스크 사이클 OFF"
    status_color = "#FF8C69" if combo_state else "#4BFFB3"
    active_flag_labels = []
    entries = []

    for code, label in _MACRO2_SIGNAL_LABELS.items():
        latest_date = _get_macro_signal_latest_date(
            code,
            years,
            benchmark_name=benchmark_name,
            sync_bucket=sync_bucket,
        )
        flag_col = f"{_macro2_debug_name(code)}_flag"
        is_selected = code in selected_codes
        is_on = bool(latest_row.get(flag_col, False)) if flag_col in latest_row.index else False
        if is_on:
            active_flag_labels.append(label)
        entries.append({
            "label": label,
            "selected": is_selected,
            "flag": is_on,
            "latest_date": _macro_date_text(latest_date),
        })

    active_flags_text = ", ".join(active_flag_labels) if active_flag_labels else "없음"

    summary_html = (
        '<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;'
        'padding:0 0 18px 0;color:#CFCFCF;font-size:13px;">'
        f'<span><b>기준일</b> {basis_date}</span>'
        f'<span><b>현재 플래그</b> {_macro_on_k_text(active_count, combo_k)} ({active_flags_text})</span>'
        f'<span><b>상태</b> <span style="color:{status_color};font-weight:700;">{status_text}</span></span>'
        '</div>'
    )

    left_entries = entries[:3]
    right_entries = entries[3:]
    row_count = max(len(left_entries), len(right_entries))

    def _entry_cells(entry):
        if not entry:
            return (
                "<td style='padding:6px 8px;'></td>"
                "<td style='padding:6px 8px;'></td>"
                "<td style='padding:6px 8px;'></td>"
                "<td style='padding:6px 8px;'></td>"
            )
        return (
            f"<td style='padding:6px 8px;color:#D6D6D6;'>{entry['label']}</td>"
            f"<td style='padding:6px 8px;text-align:center;'>{_macro_status_circle(entry['selected'], color_on='#7C7CF7')}</td>"
            f"<td style='padding:6px 8px;text-align:center;'>{_macro_status_circle(entry['flag'], color_on='#4BFFB3')}</td>"
            f"<td style='padding:6px 8px;color:#AFAFAF;'>{entry['latest_date']}</td>"
        )

    rows_html = []
    for idx in range(row_count):
        left = left_entries[idx] if idx < len(left_entries) else None
        right = right_entries[idx] if idx < len(right_entries) else None
        rows_html.append(f"<tr>{_entry_cells(left)}<td style='width:12px;'></td>{_entry_cells(right)}</tr>")

    table_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.25;'>"
        "<thead>"
        "<tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "<th style='width:12px;border-bottom:1px solid rgba(255,255,255,0.08);'></th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )

    _macro_debug_log(
        "build_macro_combo_status_panel",
        benchmark_name=benchmark_name,
        years=years,
        selected_codes=len(selected_codes),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return summary_html, table_html


def _build_macro_meta_combo_status_panel(
    benchmark_name: str,
    years: int,
    spx_s: pd.Series,
    meta_event_df: pd.DataFrame,
    combo_a_event_df: pd.DataFrame,
    combo_b_event_df: pd.DataFrame,
    combo_a_cfg: dict,
    combo_b_cfg: dict,
    sync_bucket: str | None = None,
):
    _started = time.perf_counter()
    if meta_event_df is None or meta_event_df.empty:
        return "", ""

    latest_meta = meta_event_df.sort_values("date").iloc[-1]
    combo_state = bool(latest_meta.get("combo_risk_state", False))
    basis_date = _macro_date_text(latest_meta.get("date"))
    status_text = "리스크 사이클 ON" if combo_state else "리스크 사이클 OFF"
    status_color = "#FF8C69" if combo_state else "#4BFFB3"
    a_on = bool(latest_meta.get("a_state", False))
    b_on = bool(latest_meta.get("b_state", False))
    active_count = int(a_on) + int(b_on)
    active_names = []
    if a_on:
        active_names.append("조합 A")
    if b_on:
        active_names.append("조합 B")
    active_flags_text = ", ".join(active_names) if active_names else "없음"

    combo_a_latest = combo_a_event_df.sort_values("date").iloc[-1] if combo_a_event_df is not None and not combo_a_event_df.empty else pd.Series(dtype=object)
    combo_b_latest = combo_b_event_df.sort_values("date").iloc[-1] if combo_b_event_df is not None and not combo_b_event_df.empty else pd.Series(dtype=object)

    def _build_entries(combo_label: str, combo_latest, combo_cfg: dict):
        entries = [{
            "label": combo_label,
            "flag": bool(combo_latest.get("combo_risk_state", False)),
            "latest_date": _macro_date_text(combo_latest.get("date")),
        }]
        for code in combo_cfg["selected_codes"]:
            latest_date = _get_macro_signal_latest_date(
                code,
                years,
                benchmark_name=benchmark_name,
                sync_bucket=sync_bucket,
            )
            flag_col = f"{_macro2_debug_name(code)}_flag"
            entries.append({
                "label": _MACRO2_SIGNAL_LABELS.get(code, code),
                "flag": bool(combo_latest.get(flag_col, False)),
                "latest_date": _macro_date_text(latest_date),
            })
        return entries

    left_entries = _build_entries("조합 A", combo_a_latest, combo_a_cfg)
    right_entries = _build_entries("조합 B", combo_b_latest, combo_b_cfg)
    row_count = max(len(left_entries), len(right_entries))

    def _entry_cells(entry):
        if not entry:
            return (
                "<td style='padding:6px 8px;'></td>"
                "<td style='padding:6px 8px;'></td>"
                "<td style='padding:6px 8px;'></td>"
            )
        return (
            f"<td style='padding:6px 8px;color:#D6D6D6;'>{entry['label']}</td>"
            f"<td style='padding:6px 8px;text-align:center;'>{_macro_status_circle(entry['flag'], color_on='#4BFFB3')}</td>"
            f"<td style='padding:6px 8px;color:#AFAFAF;'>{entry['latest_date']}</td>"
        )

    rows_html = []
    for idx in range(row_count):
        left = left_entries[idx] if idx < len(left_entries) else None
        right = right_entries[idx] if idx < len(right_entries) else None
        rows_html.append(f"<tr>{_entry_cells(left)}<td style='width:14px;'></td>{_entry_cells(right)}</tr>")

    summary_html = (
        '<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;'
        'padding:0 0 18px 0;color:#CFCFCF;font-size:13px;">'
        f'<span><b>기준일</b> {basis_date}</span>'
        f'<span><b>현재 플래그</b> {_macro_on_k_text(active_count, 2)} ({active_flags_text})</span>'
        f'<span><b>상태</b> <span style="color:{status_color};font-weight:700;">{status_text}</span></span>'
        '</div>'
    )

    table_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.25;'>"
        "<thead>"
        "<tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>조합 A</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "<th style='width:14px;border-bottom:1px solid rgba(255,255,255,0.08);'></th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>조합 B</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )

    _macro_debug_log(
        "build_macro_meta_combo_status_panel",
        benchmark_name=benchmark_name,
        years=years,
        combo_a_codes=len(combo_a_cfg.get("selected_codes", [])),
        combo_b_codes=len(combo_b_cfg.get("selected_codes", [])),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return summary_html, table_html


def _build_macro_meta_backtest_panel(
    preset_key: str,
    preset_defs: dict | None = None,
    years: int = 3,
    sync_bucket: str | None = None,
) -> tuple[str, str]:
    _started = time.perf_counter()
    selected = _MACRO_META_BACKTEST_COMPARE.get(preset_key)
    if not selected:
        return "", ""
    group = selected.get("group")
    header = (
        "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>후보</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>10Y 자산</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y 자산</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>10Y MDD</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y MDD</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y Risk-off</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y Cycle</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>짧은 Cycle</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>현재</th>"
        "</tr></thead><tbody>"
    )
    rows = []
    group_items = [(key, meta) for key, meta in _MACRO_META_BACKTEST_COMPARE.items() if meta.get("group") == group]
    sort_orders = {
        "sp500": ["sp500_buyhold", "snp", "common", "snp_meta_1", "snp_meta_2", "snp_meta_stab", "snp_meta_stab_2", "snp_meta_stab_3"],
        "nasdaq": ["nasdaq_buyhold", "nasdaq", "nasdaq_common", "nasdaq_meta", "nasdaq_meta_stab_1"],
    }
    sort_order = sort_orders.get(group, [])
    group_items.sort(key=lambda item: sort_order.index(item[0]) if item[0] in sort_order else 999)
    hold_key = "sp500_buyhold" if group == "sp500" else "nasdaq_buyhold"
    hold_metrics = _MACRO_META_BACKTEST_COMPARE.get(hold_key, {}).get("metrics", {})
    hold_10y = _macro_metric_float(hold_metrics.get("10Y 자산"))
    hold_20y = _macro_metric_float(hold_metrics.get("20Y 자산"))
    hold_mdd_10y = _macro_metric_float(hold_metrics.get("10Y MDD"))
    hold_mdd_20y = _macro_metric_float(hold_metrics.get("20Y MDD"))
    def _ratio_span(ratio: float, good: bool) -> str:
        color = "#7FE7B1" if good else "#8F8F8F"
        weight = "700" if good else "400"
        return f"<span style='color:{color};font-size:11px;font-weight:{weight};'>({ratio:.2f}x)</span>"
    current_state_map = {}
    if preset_defs:
        for key, _meta in group_items:
            preset_cfg = _resolve_macro_backtest_preset_cfg(key, preset_defs)
            if not preset_cfg:
                current_state_map[key] = None
                continue
            try:
                current_state_map[key] = _compute_macro_preset_current_state(
                    preset_cfg=preset_cfg,
                    years=years,
                    sync_bucket=sync_bucket,
                )
            except Exception:
                current_state_map[key] = None
    for key, meta in group_items:
        is_selected = key == preset_key
        bg = "rgba(120,126,231,0.16)" if is_selected else "transparent"
        border = "1px solid rgba(120,126,231,0.34)" if is_selected else "1px solid transparent"
        summary = meta["metrics"]
        asset_10y = summary["10Y 자산"]
        asset_20y = summary["20Y 자산"]
        mdd_10y = summary["10Y MDD"]
        mdd_20y = summary["20Y MDD"]
        asset_10y_num = _macro_metric_float(asset_10y)
        asset_20y_num = _macro_metric_float(asset_20y)
        mdd_10y_num = _macro_metric_float(mdd_10y)
        mdd_20y_num = _macro_metric_float(mdd_20y)
        if hold_10y and asset_10y_num is not None and key != hold_key:
            _ratio = asset_10y_num / hold_10y
            asset_10y = f"{asset_10y} {_ratio_span(_ratio, _ratio >= 1.5)}"
        if hold_20y and asset_20y_num is not None and key != hold_key:
            _ratio = asset_20y_num / hold_20y
            asset_20y = f"{asset_20y} {_ratio_span(_ratio, _ratio >= 1.5)}"
        if hold_mdd_10y and mdd_10y_num is not None and key != hold_key:
            _ratio = abs(mdd_10y_num) / abs(hold_mdd_10y)
            mdd_10y = f"{mdd_10y} {_ratio_span(_ratio, _ratio <= 0.5)}"
        if hold_mdd_20y and mdd_20y_num is not None and key != hold_key:
            _ratio = abs(mdd_20y_num) / abs(hold_mdd_20y)
            mdd_20y = f"{mdd_20y} {_ratio_span(_ratio, _ratio <= 0.5)}"
        current_state = current_state_map.get(key)
        if current_state is None:
            current_state_html = "-"
        else:
            current_state_html = _macro_flag_ratio_html(
                current_state.get("on_count", 0),
                current_state.get("start_count", current_state.get("total_count", 1)),
                current_state.get("is_on"),
            )
        rows.append(
            f"<tr style='background:{bg};border-top:{border};border-bottom:{border};'>"
            f"<td style='padding:7px 8px;color:#EDEDED;font-weight:700;'>{meta['label']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{asset_10y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{asset_20y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{mdd_10y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{mdd_20y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['20Y Risk-off']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['20Y Cycle']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['짧은 Cycle']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:center;'>{current_state_html}</td>"
            "</tr>"
        )
    compare_html = header + "".join(rows) + "</tbody></table>"
    _macro_debug_log(
        "build_macro_meta_backtest_panel",
        preset_key=preset_key,
        group=group,
        years=years,
        candidate_count=len(group_items),
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return "", compare_html


_MACRO3_FINAL8_CSV = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "sp500_final8",
    "sp500_dashboard_review_final8.csv",
)
_MACRO3_ROBUSTNESS_V2_CSV = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "robustness_44_v1",
    "robustness_44_reweighted_v2.csv",
)
_MACRO3_COMBO2_FINAL8_CSV = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "combo2_final8_selected_v1",
    "combo2_final8_selected_v1.csv",
)
_MACRO3_TOP44_DICTIONARY_PARQUET = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "combo2_exhaustive_v1",
    "combo1_top44_candidate_dictionary.parquet",
)
_MACRO3_COMBO1_FROZEN_SIGNALS_PARQUET = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "top15_signal_similarity_v1",
    "top15_daily_signal_timeseries.parquet",
)
_MACRO3_COMBO2_FROZEN_SIGNALS_PARQUET = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "combo2_exhaustive_v1",
    "combo2_robustness100_v1",
    "combo2_robustness100_daily_signals.parquet",
)
_MACRO3_PARITY_OUTPUT_DIR = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "macro3_dashboard_validation_v1",
)
_MACRO6_PROXY_REVIEW_CSV = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "credit_proxy_kl_restore_pre20y_check_v1",
    "final_user_review_candidates_updated.csv",
)
_MACRO6_PROXY_BACKTEST_CSV = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "credit_proxy_selection_rerun_v1",
    "proxy_only_dashboard_review_candidates.csv",
)
_MACRO6_OFFICIAL_FROZEN_DIR = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_sp500_final_v1",
    "sp500",
    "credit_proxy_full_reselection_v1",
)
_MACRO6_OFFICIAL_FROZEN_SNAPSHOT_PARQUET = os.path.join(
    _DIR,
    "combo1_expanded_v1",
    "outputs_single_full_v1",
    "sp500",
    "market_data_snapshot.parquet",
)
_MACRO6_OFFICIAL_FROZEN_PROXY_RAW_PARQUET = os.path.join(
    _MACRO6_OFFICIAL_FROZEN_DIR,
    "proxy_raw_fred_sources.parquet",
)
_MACRO6_OFFICIAL_BASELINE_TIMELINE_SOURCES = (
    os.path.join(_DIR, "combo1_expanded_v1", "outputs_sp500_final_v1", "sp500", "single_indicator", "indicator_candidate_timeline.parquet"),
    os.path.join(_DIR, "combo1_expanded_v1", "outputs_sp500_final_v1", "sp500", "focused_search_run_v1", "_runtime_candidate_timeline_tier6.parquet"),
    os.path.join(_DIR, "combo1_expanded_v1", "outputs_sp500_final_v1", "sp500", "focused_search_run_v1", "n=7", "_runtime_candidate_timeline_tier4.parquet"),
    os.path.join(_DIR, "combo1_expanded_v1", "outputs_sp500_final_v1", "sp500", "focused_search_run_v1", "n=8", "_runtime_candidate_timeline_tier4.parquet"),
    os.path.join(_DIR, "combo1_expanded_v1", "outputs_sp500_final_v1", "sp500", "focused_search_n9_local_run_v1", "n=9", "_runtime_candidate_timeline_tier4.parquet"),
)
_MACRO6_CREDIT_PROXY_INDICATORS = {"HY", "IG", "Credit Stress"}
_MACRO3_BACKTEST_GROUP_SA = (
    "macro5_combo2_final8_1",
    "macro5_combo2_final8_2",
    "macro5_combo2_final8_5",
    "macro5_combo2_final8_7",
    "macro5_combo2_final8_4",
    "macro5_combo2_final8_6",
    "macro5_combo2_final8_3",
)
_MACRO3_BACKTEST_GROUP_BCD = (
    "macro5_combo1_final8_1",
    "macro5_combo1_final8_8",
    "macro5_combo1_final8_3",
    "macro5_combo2_final8_8",
    "macro5_combo1_final8_2",
    "macro5_combo1_final8_4",
    "macro5_combo1_final8_6",
    "macro5_combo1_final8_5",
    "macro5_combo1_final8_7",
)
_MACRO6_COMBO2_CANDIDATES = (
    ("macro6_combo2_1", "m8_8112998890601066", "Main"),
    ("macro6_combo2_6", "m5_5010704845", "고수익 방어형"),
    ("macro6_combo2_2", "m6_6624758514725359", "시장참여형"),
    ("macro6_combo2_3", "m7_7836479199389981", "안정 방어형"),
    ("macro6_combo2_4", "m7_7304308638289210", "고수익형"),
    ("macro6_combo2_5", "m4_4001137875", "T+2 균형형"),
)
_MACRO6_COMBO1_CANDIDATES = (
    ("macro6_combo1_1", "combo1_proxy_540347d549244000", "Main"),
    ("macro6_combo1_4", "combo1_proxy_f37033c32516e147", "강방어형"),
    ("macro6_combo1_2", "combo1_proxy_ece4aa198a4060ff", "수익형"),
    ("macro6_combo1_3", "combo1_proxy_08160f7db8770aa9", "균형 방어형"),
    ("macro6_combo1_5", "combo1_proxy_c3a64264c2e842f5", "저이탈형"),
)
_MACRO6_DISPLAY_LABEL_OVERRIDES = {
    "m8_8112998890601066": "[조합2] Main1 수익·방어 균형형 (조합1 8개/K6/L5)",
    "m5_5010704845": "[조합2] Main2 고수익 방어형 (조합1 5개/K3/L2)",
    "combo1_proxy_540347d549244000": "[조합1] Main1 핵심 리스크 균형형 (지표 4개/K3/L2)",
    "combo1_proxy_f37033c32516e147": "[조합1] Main2 강방어형 (지표 7개/K4/L3)",
}
_MACRO6_COMBO2_ORDER = tuple(key for key, _, _ in _MACRO6_COMBO2_CANDIDATES)
_MACRO6_COMBO1_ORDER = tuple(key for key, _, _ in _MACRO6_COMBO1_CANDIDATES)
_MACRO3_INDICATOR_ORDER = [
    "Index",
    "HY",
    "IG",
    "Credit Stress",
    "VIX",
    "VIX Spread",
    "10Y Real Yield",
    "10Y-2Y Spread",
    "10Y-3M Spread",
    "10Y Nominal Yield Slope",
    "Bollinger Band",
]
_MACRO6_COMPONENT_INDICATOR_ORDER = _MACRO3_INDICATOR_ORDER[:-1] + ["RSI", _MACRO3_INDICATOR_ORDER[-1]]
_MACRO3_LAGGED_INDICATORS = {
    "HY",
    "IG",
    "10Y Real Yield",
    "10Y-2Y Spread",
    "10Y-3M Spread",
    "10Y Nominal Yield Slope",
}
_MACRO3_INDICATOR_LABELS = {
    "Index": "① 지수",
    "HY": "② HY",
    "IG": "③ IG",
    "Credit Stress": "④ 신용스트레스",
    "VIX": "⑤ VIX",
    "VIX Spread": "⑥ VIX 스프레드",
    "10Y Real Yield": "⑦ 10Y 실질금리",
    "10Y-2Y Spread": "⑧ 10Y-2Y 스프레드",
    "10Y-3M Spread": "⑨ 10Y-3M 스프레드",
    "10Y Nominal Yield Slope": "⑩ 10Y 금리기울기",
    "Bollinger Band": "⑪ 볼린저밴드",
    "RSI": "⑫ RSI",
}


def _macro3_eastern_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=ZoneInfo("America/New_York"))


def _macro3_last_confirmed_us_date(now_et: pd.Timestamp | None = None) -> pd.Timestamp:
    now_et = now_et or _macro3_eastern_now()
    today = pd.Timestamp(now_et.date())
    if now_et.weekday() < 5 and now_et.time() < datetime.strptime("18:00", "%H:%M").time():
        return today - pd.Timedelta(days=1)
    return today


def _macro3_completed_us_trading_days(years: int = 5, now_et: pd.Timestamp | None = None) -> pd.DatetimeIndex:
    now_et = now_et or _macro3_eastern_now()
    start_date = (pd.Timestamp(now_et.date()) - pd.DateOffset(years=max(1, int(years))) - pd.Timedelta(days=14)).date()
    end_date = pd.Timestamp(now_et.date()).date()
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=start_date, end_date=end_date)
        if schedule.empty:
            return pd.DatetimeIndex([])
        now_utc = now_et.tz_convert("UTC") if getattr(now_et, "tzinfo", None) else now_et.tz_localize("America/New_York").tz_convert("UTC")
        completed = schedule[schedule["market_close"] <= now_utc]
        if completed.empty:
            return pd.DatetimeIndex([])
        return pd.DatetimeIndex(completed.index).tz_localize(None).normalize().sort_values().unique()
    except Exception:
        cutoff = _macro3_last_confirmed_us_date(now_et)
        idx = pd.date_range(start=start_date, end=cutoff.date(), freq="B")
        return pd.DatetimeIndex(idx).normalize().sort_values().unique()


def _macro3_latest_completed_us_trading_date(years: int = 5, now_et: pd.Timestamp | None = None) -> pd.Timestamp | None:
    idx = _macro3_completed_us_trading_days(years=years, now_et=now_et)
    return None if len(idx) == 0 else pd.Timestamp(idx[-1]).normalize()

def _macro3_filter_confirmed_us_daily(data):
    if data is None or getattr(data, "empty", True):
        return data
    out = data.copy()
    out.index = pd.DatetimeIndex(_strip_tz(out.index)).normalize()
    cutoff = _macro3_latest_completed_us_trading_date() or _macro3_last_confirmed_us_date()
    return out[out.index <= cutoff]


def _macro6_inner_vix_spread(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    if vix is None or vix3m is None or vix.empty or vix3m.empty:
        return pd.Series(dtype=float)
    pair = (
        pd.to_numeric(vix, errors="coerce")
        .dropna()
        .rename("vix")
        .to_frame()
        .join(pd.to_numeric(vix3m, errors="coerce").dropna().rename("vix3m").to_frame(), how="inner")
        .dropna()
    )
    if pair.empty:
        return pd.Series(dtype=float)
    pair.index = pd.DatetimeIndex(_strip_tz(pair.index)).normalize()
    pair = pair.sort_index().loc[~pair.index.duplicated(keep="last")]
    return (pair["vix"] - pair["vix3m"]).dropna()


def _macro6_lag_trading_days(expected_date, latest_date, benchmark_index) -> int | None:
    if expected_date is None or latest_date is None or pd.isna(expected_date) or pd.isna(latest_date):
        return None
    try:
        expected = pd.Timestamp(expected_date).normalize()
        latest = pd.Timestamp(latest_date).normalize()
        idx = pd.DatetimeIndex(pd.to_datetime(benchmark_index)).normalize().sort_values().unique()
        return int(((idx > latest) & (idx <= expected)).sum())
    except Exception:
        return None


def _macro6_expected_latest_trading_date(
    benchmark_name: str = "S&P500",
    years: int = 5,
    spx_s: pd.Series | None = None,
    sync_bucket: str | None = None,
):
    calendar_index = _macro3_completed_us_trading_days(years=years)
    if len(calendar_index):
        return pd.Timestamp(calendar_index[-1]).normalize(), calendar_index
    source = spx_s
    if source is None or getattr(source, "empty", True):
        benchmark = _get_macro_benchmark(benchmark_name)
        source = _yf_close(benchmark["code"], years, sync_bucket=sync_bucket)
    source = _macro3_filter_confirmed_us_daily(source).dropna() if source is not None else pd.Series(dtype=float)
    if source.empty:
        return None, pd.DatetimeIndex([])
    return source.index.max(), pd.DatetimeIndex(source.index).normalize().sort_values().unique()


@st.cache_data(ttl=3600, show_spinner=False)
def _macro6_vix_spread_with_fallback(
    years: int,
    benchmark_name: str = "S&P500",
    expected_latest_date=None,
    benchmark_dates: tuple | None = None,
    sync_bucket: str | None = None,
):
    expected_latest = pd.Timestamp(expected_latest_date).normalize() if expected_latest_date is not None and not pd.isna(expected_latest_date) else None
    benchmark_index = pd.DatetimeIndex(pd.to_datetime(list(benchmark_dates or []))).normalize().sort_values().unique()

    yahoo_vix = _macro3_filter_confirmed_us_daily(_yf_close("^VIX", years, sync_bucket=sync_bucket))
    yahoo_vix3m = _macro3_filter_confirmed_us_daily(_yf_close("^VIX3M", years, sync_bucket=sync_bucket))
    yahoo_spread = _macro6_inner_vix_spread(yahoo_vix, yahoo_vix3m)

    fred_vix = _macro3_filter_confirmed_us_daily(_fred("VIXCLS", years, sync_bucket=sync_bucket))
    fred_vix3m = _macro3_filter_confirmed_us_daily(_fred("VXVCLS", years, sync_bucket=sync_bucket))
    fred_spread = _macro6_inner_vix_spread(fred_vix, fred_vix3m)
    if expected_latest is not None:
        if not fred_spread.empty:
            fred_spread = fred_spread[fred_spread.index <= expected_latest]
        if not yahoo_spread.empty:
            yahoo_spread = yahoo_spread[yahoo_spread.index <= expected_latest]

    yahoo_last = None if yahoo_spread.empty else yahoo_spread.index.max()
    fred_last = None if fred_spread.empty else fred_spread.index.max()
    source_status = "NO_DATA"
    source_label = "데이터 없음"
    final_spread = pd.Series(dtype=float)
    fred_supplement_days = None
    fred_supplement_trading_days = None

    if not yahoo_spread.empty:
        final_spread = yahoo_spread.copy()
        source_status = "YAHOO"
        source_label = "Yahoo"
        yahoo_is_stale = expected_latest is not None and yahoo_last < expected_latest
        fred_is_newer = fred_last is not None and fred_last > yahoo_last
        if yahoo_is_stale and fred_is_newer:
            fred_tail = fred_spread[fred_spread.index > yahoo_last]
            final_spread = pd.concat([final_spread, fred_tail]).sort_index()
            source_status = "YAHOO_PLUS_FRED_FALLBACK"
            fred_tail_last = None if fred_tail.empty else fred_tail.index.max()
            if fred_tail_last is not None:
                fred_supplement_days = int(max(0, (fred_tail_last - yahoo_last).days))
                fred_supplement_trading_days = int(len(fred_tail))
                source_label = f"FRED 보완 {fred_supplement_days}일"
            else:
                source_label = "FRED 보완"
        elif yahoo_is_stale:
            source_status = "YAHOO_STALE"
            source_label = "Yahoo"
    elif not fred_spread.empty:
        final_spread = fred_spread.copy()
        source_status = "FRED_ONLY"
        source_label = "FRED"

    final_spread = final_spread.replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    final_spread = final_spread.loc[~final_spread.index.duplicated(keep="first")]
    final_latest = None if final_spread.empty else final_spread.index.max()
    lag_days = _macro6_lag_trading_days(expected_latest, final_latest, benchmark_index)
    if lag_days is None and expected_latest is not None and final_latest is not None:
        lag_days = int(max(0, (expected_latest - final_latest).days))
    note = "확인 불가" if final_latest is None else ("지연" if (lag_days or 0) > 0 else "정상")
    detail_parts = [source_label]
    if lag_days is not None and lag_days > 0:
        detail_parts.append(f"{lag_days}거래일 지연")
    detail = " · ".join(detail_parts)

    return {
        "series": (-final_spread).dropna(),
        "raw_spread": final_spread,
        "source_status": source_status,
        "source_label": source_label,
        "note": note,
        "detail": detail,
        "lag_trading_days": lag_days,
        "expected_latest_date": expected_latest,
        "final_latest_date": final_latest,
        "yahoo_common_latest_date": yahoo_last,
        "fred_common_latest_date": fred_last,
        "fred_supplement_days": fred_supplement_days,
        "fred_supplement_trading_days": fred_supplement_trading_days,
    }


def _macro6_debug_series_latest_summary(obj) -> dict:
    if obj is None or getattr(obj, "empty", True):
        return {"rows": 0, "first_date": None, "latest_date": None, "tail": ""}
    data = obj.copy()
    if isinstance(data, pd.DataFrame):
        normalized = _normalize_yf_ohlcv(data)
        if normalized is not None and not normalized.empty and "Close" in normalized.columns:
            data = normalized["Close"]
        elif "Close" in data.columns:
            data = data["Close"]
        else:
            data = data.iloc[:, 0]
    if isinstance(data, pd.DataFrame):
        data = data.squeeze("columns")
    series = pd.to_numeric(pd.Series(data), errors="coerce").dropna()
    if series.empty:
        return {"rows": 0, "first_date": None, "latest_date": None, "tail": ""}
    idx = pd.DatetimeIndex(pd.to_datetime(series.index, errors="coerce")).tz_localize(None).normalize()
    series = pd.Series(series.to_numpy(), index=idx).dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    tail = " | ".join(f"{d.strftime('%Y-%m-%d')}={v:.4g}" for d, v in series.tail(3).items())
    return {
        "rows": int(len(series)),
        "first_date": series.index.min().strftime("%Y-%m-%d"),
        "latest_date": series.index.max().strftime("%Y-%m-%d"),
        "tail": tail,
    }


def _macro6_latest_date_debug_rows(years: int, benchmark_name: str, sync_bucket: str | None = None) -> pd.DataFrame:
    rows = []

    def _append(label: str, route: str, obj=None, note: str = "", **extra):
        summary = _macro6_debug_series_latest_summary(obj)
        row = {
            "label": label,
            "route": route,
            "rows": summary["rows"],
            "first_date": summary["first_date"],
            "latest_date": summary["latest_date"],
            "tail": summary["tail"],
            "note": note,
        }
        row.update(extra)
        rows.append(row)

    benchmark = _get_macro_benchmark(benchmark_name)
    ticker = benchmark["code"]
    try:
        raw_download = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=False, threads=False)
        _append("S&P500", "yf.download(period=1mo)", raw_download)
    except Exception as exc:
        _append("S&P500", "yf.download(period=1mo)", None, note=f"ERROR: {exc}")
    try:
        raw_history = yf.Ticker(ticker).history(period="1mo", interval="1d", auto_adjust=False)
        _append("S&P500", "Ticker.history(period=1mo)", raw_history)
    except Exception as exc:
        _append("S&P500", "Ticker.history(period=1mo)", None, note=f"ERROR: {exc}")
    try:
        _append("S&P500", "_yf_close cached route", _yf_close(ticker, years, sync_bucket=sync_bucket), sync_bucket=sync_bucket or "")
    except Exception as exc:
        _append("S&P500", "_yf_close cached route", None, note=f"ERROR: {exc}", sync_bucket=sync_bucket or "")
    try:
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, years)
        _append("Bollinger Band", "_macro3_fetch_benchmark_ohlcv", ohlc)
    except Exception as exc:
        _append("Bollinger Band", "_macro3_fetch_benchmark_ohlcv", None, note=f"ERROR: {exc}")

    try:
        expected_latest, benchmark_index = _macro6_expected_latest_trading_date(
            benchmark_name=benchmark_name,
            years=years,
            sync_bucket=sync_bucket,
        )
        rows.append({
            "label": "Expected latest",
            "route": "_macro6_expected_latest_trading_date",
            "rows": int(len(benchmark_index)),
            "first_date": None if len(benchmark_index) == 0 else pd.Timestamp(benchmark_index[0]).strftime("%Y-%m-%d"),
            "latest_date": None if expected_latest is None or pd.isna(expected_latest) else pd.Timestamp(expected_latest).strftime("%Y-%m-%d"),
            "tail": "",
            "note": "NYSE 최신 완료 거래일 기준",
        })
    except Exception as exc:
        expected_latest, benchmark_index = None, pd.DatetimeIndex([])
        _append("Expected latest", "_macro6_expected_latest_trading_date", None, note=f"ERROR: {exc}")

    for indicator in _MACRO3_INDICATOR_ORDER:
        try:
            status = _macro6_indicator_data_status_row(
                indicator,
                years,
                benchmark_name=benchmark_name,
                sync_bucket=sync_bucket,
            )
            latest = status.get("latest_date")
            note_parts = [str(status.get("latest_text") or "")]
            if status.get("source_status"):
                note_parts.append(f"source={status.get('source_status')}")
            if status.get("lag_trading_days") is not None:
                note_parts.append(f"lag={status.get('lag_trading_days')}거래일")
            if status.get("yahoo_common_latest_date") is not None:
                note_parts.append(f"yahoo={_macro_date_text(status.get('yahoo_common_latest_date'))}")
            if status.get("fred_common_latest_date") is not None:
                note_parts.append(f"fred={_macro_date_text(status.get('fred_common_latest_date'))}")
            rows.append({
                "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
                "route": "_macro6_indicator_data_status_row",
                "rows": None,
                "first_date": None,
                "latest_date": None if latest is None or pd.isna(latest) else pd.Timestamp(latest).strftime("%Y-%m-%d"),
                "tail": "",
                "note": " | ".join(part for part in note_parts if part),
            })
        except Exception as exc:
            _append(indicator, "_macro6_indicator_data_status_row", None, note=f"ERROR: {exc}")

    return pd.DataFrame(rows)

def _macro3_next_execution_date(signal_date, benchmark_index) -> pd.Timestamp | None:
    try:
        signal_date = pd.Timestamp(signal_date).normalize()
    except Exception:
        return None
    try:
        idx = pd.DatetimeIndex(pd.to_datetime(benchmark_index)).normalize().sort_values().unique()
        future = idx[idx > signal_date]
        if len(future):
            return pd.Timestamp(future[0]).normalize()
    except Exception:
        pass
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(
            start_date=(signal_date + pd.Timedelta(days=1)).date(),
            end_date=(signal_date + pd.Timedelta(days=10)).date(),
        )
        if not schedule.empty:
            return pd.Timestamp(schedule.index[0]).normalize()
    except Exception:
        return None
    return None


def _macro3_indicator_needs_availability(indicator: str) -> bool:
    return indicator in _MACRO3_LAGGED_INDICATORS or indicator == "Credit Stress"


def _macro3_preset_indicators(preset_cfg: dict) -> list[str]:
    if preset_cfg.get("kind") == "combo2_final8":
        indicators = []
        for component_cfg in preset_cfg.get("component_cfgs", {}).values():
            indicators.extend(component_cfg.get("selected_indicators", []))
        return list(dict.fromkeys(indicators))
    return list(preset_cfg.get("selected_indicators", []))


def _macro3_preset_blocking_reasons(preset_cfg: dict) -> list[str]:
    if preset_cfg.get("kind") == "unavailable":
        return [str(preset_cfg.get("unavailable_reason", "후보 정의를 불러오지 못했습니다."))]
    indicators = _macro3_preset_indicators(preset_cfg)
    reasons = []
    if not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        reasons.append("공통 신호 계산 함수를 불러오지 못했습니다.")
    if any(_macro3_indicator_needs_availability(name) for name in indicators) and (
        not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE or _MACRO3_AVAILABILITY_CONFIG is None
    ):
        reasons.append("백테스트 availability 정책 모듈을 불러오지 못했습니다.")
    if "Credit Stress" in indicators and (
        not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE or _MACRO3_AVAILABILITY_CONFIG is None
    ):
        reasons.append("Credit Stress 구성요소별 availability 계산을 사용할 수 없습니다.")
    return list(dict.fromkeys(reasons))


def _macro3_freshness_note(indicator: str, latest_date) -> str:
    if latest_date is None or pd.isna(latest_date):
        return "확인 불가"
    latest = pd.Timestamp(latest_date).normalize()
    now_date = pd.Timestamp.now(tz=ZoneInfo("Asia/Seoul")).tz_localize(None).normalize()
    age_days = int(max(0, (now_date - latest).days))
    if indicator == "Credit Stress":
        return "지연" if age_days > 10 else "정상"
    if indicator in {"Index", "VIX", "VIX Spread", "Bollinger Band"}:
        return "지연" if age_days > 5 else "정상"
    return "지연" if age_days > 7 else "정상"


def _macro3_component_data_status(
    component_cfg: dict,
    years: int,
    benchmark_name: str = "S&P500",
    sync_bucket: str | None = None,
) -> dict:
    rows = []
    for indicator in component_cfg.get("selected_indicators", []):
        latest_date = _get_macro3_signal_latest_date(
            indicator,
            years,
            benchmark_name=benchmark_name,
            sync_bucket=sync_bucket,
        )
        rows.append({
            "indicator": indicator,
            "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
            "latest_date": latest_date,
            "note": _macro3_freshness_note(indicator, latest_date),
        })
    valid_rows = [row for row in rows if row["latest_date"] is not None and not pd.isna(row["latest_date"])]
    bottleneck = min(valid_rows, key=lambda row: pd.Timestamp(row["latest_date"])) if valid_rows else None
    return {"rows": rows, "bottleneck": bottleneck}


def _macro3_indicator_key(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())
    return text.strip("_")


def _macro3_metric_percent(value) -> str:
    return f"{float(value) * 100:.1f}%"


def _macro3_metric_asset(value) -> str:
    return f"{float(value):.1f}"


def _parse_macro3_param_token(raw_value: str) -> dict | None:
    value = str(raw_value).strip()
    m_level = re.fullmatch(r"EMA(\d+)_W(\d+)_S(\d+)_E(\d+)", value)
    if m_level:
        return {
            "kind": "level",
            "ema": int(m_level.group(1)),
            "window": int(m_level.group(2)),
            "start": int(m_level.group(3)) / 100.0,
            "end": int(m_level.group(4)) / 100.0,
            "raw": value,
        }
    m_slope = re.fullmatch(r"SW(\d+)_EMA(\d+)_W(\d+)_S(\d+)_E(\d+)", value)
    if m_slope:
        return {
            "kind": "yield_slope",
            "slope_window": int(m_slope.group(1)),
            "ema": int(m_slope.group(2)),
            "window": int(m_slope.group(3)),
            "start": int(m_slope.group(4)) / 100.0,
            "end": int(m_slope.group(5)) / 100.0,
            "raw": value,
        }
    m_bb = re.fullmatch(r"BBW(\d+)_STD([0-9p]+)", value)
    if m_bb:
        return {
            "kind": "bollinger",
            "window": int(m_bb.group(1)),
            "std": float(m_bb.group(2).replace("p", ".")),
            "raw": value,
        }
    m_rsi = re.fullmatch(r"RSI(\d+)_LB(\d+)_Q10_90", value)
    if m_rsi:
        return {
            "kind": "rsi",
            "period": int(m_rsi.group(1)),
            "lookback": int(m_rsi.group(2)),
            "lower_q": 0.10,
            "upper_q": 0.90,
            "raw": value,
        }
    return None


def _parse_macro3_combo_key(combo_key: str, indicator_order=None) -> dict:
    indicator_order = list(indicator_order or _MACRO3_INDICATOR_ORDER)
    cfgs = {}
    start_k = None
    end_l = None
    for token in str(combo_key).split("|"):
        if "=" not in token:
            continue
        name, raw_value = token.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        if name == "start_k":
            start_k = int(raw_value)
            continue
        if name == "end_l":
            end_l = int(raw_value)
            continue
        parsed = _parse_macro3_param_token(raw_value)
        if parsed:
            cfgs[name] = parsed
    selected_indicators = [name for name in indicator_order if name in cfgs]
    return {
        "cfgs": cfgs,
        "selected_indicators": selected_indicators,
        "start_k": start_k,
        "end_l": end_l,
    }


def _macro3_apply_indicator_availability(indicator: str, series: pd.Series) -> pd.Series:
    if (
        not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE
        or _MACRO3_AVAILABILITY_CONFIG is None
        or series is None
        or series.empty
    ):
        if _macro3_indicator_needs_availability(indicator):
            return pd.Series(dtype=float)
        return series
    return _combo1_apply_availability_lag(series.dropna(), indicator, _MACRO3_AVAILABILITY_CONFIG)


def _macro3_component_label(component_key: str, component_cfg: dict | None = None) -> str:
    if not component_cfg:
        return str(component_key)
    n = component_cfg.get("n")
    combo_id = component_cfg.get("combo_id")
    if n and combo_id:
        return f"{component_key} ({int(n)}개 조합)"
    return str(component_key)


@st.cache_data(show_spinner=False)
def _load_macro3_top44_component_presets():
    if not os.path.exists(_MACRO3_TOP44_DICTIONARY_PARQUET):
        return {}
    dictionary = pd.read_parquet(_MACRO3_TOP44_DICTIONARY_PARQUET)
    presets = {}
    required_cols = {"candidate_key", "reconstructed_combo_key", "n", "combo_id", "start_k", "end_l"}
    if not required_cols.issubset(set(dictionary.columns)):
        return {}
    for row in dictionary.to_dict("records"):
        parsed = _parse_macro3_combo_key(row.get("reconstructed_combo_key", ""))
        if not parsed["selected_indicators"] or parsed["start_k"] is None or parsed["end_l"] is None:
            continue
        key = str(row["candidate_key"])
        presets[key] = {
            "kind": "combo1_component",
            "label": _macro3_component_label(key, row),
            "benchmark": "S&P500",
            "candidate_key": key,
            "combo_id": int(row["combo_id"]),
            "n": int(row["n"]),
            "selected_indicators": parsed["selected_indicators"],
            "combo_k": int(parsed["start_k"]),
            "combo_l": int(parsed["end_l"]),
            "cfgs": parsed["cfgs"],
            "reconstructed_combo_key": str(row.get("reconstructed_combo_key", "")).strip(),
            "role_tags": str(row.get("role_tags", "")).strip(),
        }
    return presets


@st.cache_data(show_spinner=False)
def _load_macro6_top44_component_presets():
    if not os.path.exists(_MACRO3_TOP44_DICTIONARY_PARQUET):
        return {}
    dictionary = pd.read_parquet(_MACRO3_TOP44_DICTIONARY_PARQUET)
    presets = {}
    required_cols = {"candidate_key", "reconstructed_combo_key", "n", "combo_id", "start_k", "end_l"}
    if not required_cols.issubset(set(dictionary.columns)):
        return {}
    for row in dictionary.to_dict("records"):
        parsed = _parse_macro3_combo_key(
            row.get("reconstructed_combo_key", ""),
            indicator_order=_MACRO6_COMPONENT_INDICATOR_ORDER,
        )
        if not parsed["selected_indicators"] or parsed["start_k"] is None or parsed["end_l"] is None:
            continue
        key = str(row["candidate_key"])
        presets[key] = {
            "kind": "combo1_component",
            "label": _macro3_component_label(key, row),
            "benchmark": "S&P500",
            "candidate_key": key,
            "combo_id": int(row["combo_id"]),
            "n": int(row["n"]),
            "selected_indicators": parsed["selected_indicators"],
            "combo_k": int(parsed["start_k"]),
            "combo_l": int(parsed["end_l"]),
            "cfgs": parsed["cfgs"],
            "reconstructed_combo_key": str(row.get("reconstructed_combo_key", "")).strip(),
            "role_tags": str(row.get("role_tags", "")).strip(),
        }
    return presets


@st.cache_data(show_spinner=False)
def _load_macro3_final8_presets():
    presets = {}
    if os.path.exists(_MACRO3_FINAL8_CSV) and os.path.exists(_MACRO3_ROBUSTNESS_V2_CSV):
        final8 = pd.read_csv(_MACRO3_FINAL8_CSV)
        robust = pd.read_csv(_MACRO3_ROBUSTNESS_V2_CSV)
        merged = final8.merge(
            robust[["candidate_key", "reconstructed_combo_key"]],
            on="candidate_key",
            how="left",
        ).sort_values("dashboard_priority").reset_index(drop=True)
        for row in merged.to_dict("records"):
            preset_key = f"macro5_combo1_final8_{int(row['dashboard_priority'])}"
            role = str(row.get("role_tags", "")).strip()
            label = f"조합1 Final {int(row['dashboard_priority'])}. {role}" if role else f"조합1 Final {int(row['dashboard_priority'])}"
            parsed = _parse_macro3_combo_key(row.get("reconstructed_combo_key", ""))
            if not parsed["selected_indicators"] or parsed["start_k"] is None or parsed["end_l"] is None:
                presets[preset_key] = {
                    "kind": "unavailable",
                    "label": f"{label} (계산 불가)",
                    "benchmark": "S&P500",
                    "candidate_key": str(row.get("candidate_key", "")),
                    "combo_id": row.get("combo_id", ""),
                    "combo_k": 1,
                    "combo_l": 0,
                    "selected_indicators": [],
                    "cfgs": {},
                    "metrics": {},
                    "unavailable_reason": "조합1 후보 정의 또는 reconstructed_combo_key를 해석하지 못했습니다.",
                }
                continue
            short_cycle_count = int(round(float(row["cycle_count_20y"]) * float(row["short_cycle_ratio_20y"])))
            presets[preset_key] = {
                "kind": "combo1_final8",
                "label": label,
                "benchmark": "S&P500",
                "candidate_key": str(row["candidate_key"]),
                "combo_id": int(row["combo_id"]),
                "selected_indicators": parsed["selected_indicators"],
                "combo_k": int(parsed["start_k"]),
                "combo_l": int(parsed["end_l"]),
                "cfgs": parsed["cfgs"],
                "metrics": {
                    "10Y 자산": _macro3_metric_asset(row["final_asset_10y"]),
                    "20Y 자산": _macro3_metric_asset(row["final_asset_20y"]),
                    "10Y MDD": _macro3_metric_percent(row["total_mdd_10y"]),
                    "20Y MDD": _macro3_metric_percent(row["total_mdd_20y"]),
                    "20Y Risk-off": _macro3_metric_percent(row["risk_off_share_20y"]),
                    "20Y Cycle": str(int(row["cycle_count_20y"])),
                    "짧은 Cycle": str(short_cycle_count),
                },
                "role_tags": role,
                "selection_reason": str(row.get("selection_reason", "")).strip(),
                "dashboard_review_focus": str(row.get("dashboard_review_focus", "")).strip(),
                "reconstructed_combo_key": str(row.get("reconstructed_combo_key", "")).strip(),
            }
    component_presets = _load_macro3_top44_component_presets()
    if os.path.exists(_MACRO3_COMBO2_FINAL8_CSV) and component_presets:
        combo2 = pd.read_csv(_MACRO3_COMBO2_FINAL8_CSV).sort_values("최종선정순서").reset_index(drop=True)
        component_cols = [f"component_{idx}" for idx in range(1, 9)]
        for row in combo2.to_dict("records"):
            components = [str(row.get(col)).strip() for col in component_cols if pd.notna(row.get(col)) and str(row.get(col)).strip()]
            missing = [key for key in components if key not in component_presets]
            m = int(row["m"])
            combo_k = int(row["k"])
            combo_l = int(row["l"])
            order = int(row["최종선정순서"])
            role = str(row.get("역할", "")).strip()
            preset_key = f"macro5_combo2_final8_{order}"
            label = f"조합2 Final {order}. {role}" if role else f"조합2 Final {order}"
            if missing or not components or len(components) != m or not (0 <= combo_l < combo_k <= m):
                reason_parts = []
                if missing:
                    reason_parts.append(f"component 정의 누락: {', '.join(missing)}")
                if not components:
                    reason_parts.append("component 목록이 비어 있습니다.")
                if len(components) != m:
                    reason_parts.append(f"component 수 불일치: {len(components)} / {m}")
                if not (0 <= combo_l < combo_k <= m):
                    reason_parts.append("k/l 조건이 유효하지 않습니다.")
                presets[preset_key] = {
                    "kind": "unavailable",
                    "label": f"{label} (계산 불가)",
                    "benchmark": "S&P500",
                    "candidate_key": str(row.get("후보ID", "")),
                    "combo_id": str(row.get("후보ID", "")),
                    "selected_indicators": components,
                    "components": components,
                    "component_cfgs": {},
                    "combo_k": max(1, combo_k),
                    "combo_l": max(0, combo_l),
                    "combo_m": m,
                    "cfgs": {},
                    "metrics": {},
                    "unavailable_reason": " · ".join(reason_parts),
                }
                continue
            short_cycle_count = int(round(float(row.get("사이클수_20Y", 0)) * float(row.get("짧은사이클비율_20Y", 0))))
            presets[preset_key] = {
                "kind": "combo2_final8",
                "label": label,
                "benchmark": "S&P500",
                "candidate_key": str(row["후보ID"]),
                "combo_id": str(row["후보ID"]),
                "selected_indicators": components,
                "components": components,
                "component_cfgs": {key: component_presets[key] for key in components},
                "combo_k": combo_k,
                "combo_l": combo_l,
                "combo_m": m,
                "cfgs": {},
                "metrics": {
                    "10Y 자산": _macro3_metric_asset(row["최종자산_10Y"]),
                    "20Y 자산": _macro3_metric_asset(row["최종자산_20Y"]),
                    "10Y MDD": _macro3_metric_percent(row["MDD_10Y"]),
                    "20Y MDD": _macro3_metric_percent(row["MDD_20Y"]),
                    "20Y Risk-off": _macro3_metric_percent(row["RiskOff비중_20Y"]),
                    "20Y Cycle": str(int(row["사이클수_20Y"])),
                    "짧은 Cycle": str(short_cycle_count),
                },
                "role_tags": role,
                "selection_reason": str(row.get("선정이유", "")).strip(),
                "dashboard_review_focus": str(row.get("주의사항", "")).strip(),
                "reconstructed_combo_key": "|".join(components) + f"|start_k={combo_k}|end_l={combo_l}",
            }
    combo2_first = {key: value for key, value in presets.items() if value.get("kind") == "combo2_final8"}
    combo1_after = {key: value for key, value in presets.items() if value.get("kind") != "combo2_final8"}
    return {**combo2_first, **combo1_after}


def _macro6_safe_row_value(row: dict | None, key: str, default=None):
    if not row or key not in row:
        return default
    value = row.get(key)
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    return value


def _macro6_metric_asset_from_rows(primary: dict, secondary: dict | None, key: str) -> str:
    value = _macro6_safe_row_value(primary, key, _macro6_safe_row_value(secondary, key))
    if value is None:
        return "-"
    try:
        return _macro3_metric_asset(value)
    except Exception:
        return "-"


def _macro6_metric_percent_from_rows(primary: dict, secondary: dict | None, key: str) -> str:
    value = _macro6_safe_row_value(primary, key, _macro6_safe_row_value(secondary, key))
    if value is None:
        return "-"
    try:
        return _macro3_metric_percent(value)
    except Exception:
        return "-"


def _macro6_metric_int_from_rows(primary: dict, secondary: dict | None, key: str) -> str:
    value = _macro6_safe_row_value(primary, key, _macro6_safe_row_value(secondary, key))
    if value is None:
        return "-"
    try:
        return str(int(round(float(value))))
    except Exception:
        return "-"


def _macro6_metric_cagr_from_rows(primary: dict, secondary: dict | None) -> str:
    asset = _macro6_safe_row_value(primary, "final_asset_20y", _macro6_safe_row_value(secondary, "final_asset_20y"))
    start = _macro6_safe_row_value(primary, "date_start", _macro6_safe_row_value(secondary, "date_start"))
    end = _macro6_safe_row_value(primary, "date_end", _macro6_safe_row_value(secondary, "date_end"))
    try:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        years = max((end_dt - start_dt).days / 365.25, 0.01)
        cagr = (float(asset) / 100.0) ** (1.0 / years) - 1.0
        return _macro3_metric_percent(cagr)
    except Exception:
        return "-"


def _macro6_metrics_from_rows(primary: dict, secondary: dict | None = None) -> dict:
    short_cycle_count = _macro6_metric_int_from_rows(primary, secondary, "short_cycle_count_20y")
    if short_cycle_count == "-":
        try:
            cycles = float(_macro6_safe_row_value(primary, "cycle_count_20y", _macro6_safe_row_value(secondary, "cycle_count_20y", 0)))
            ratio = float(_macro6_safe_row_value(primary, "short_cycle_ratio_20y", _macro6_safe_row_value(secondary, "short_cycle_ratio_20y", 0)))
            short_cycle_count = str(int(round(cycles * ratio)))
        except Exception:
            short_cycle_count = "-"
    return {
        "10Y 자산": _macro6_metric_asset_from_rows(primary, secondary, "final_asset_10y"),
        "20Y 자산": _macro6_metric_asset_from_rows(primary, secondary, "final_asset_20y"),
        "20Y CAGR": _macro6_metric_cagr_from_rows(primary, secondary),
        "10Y MDD": _macro6_metric_percent_from_rows(primary, secondary, "total_mdd_10y"),
        "20Y MDD": _macro6_metric_percent_from_rows(primary, secondary, "total_mdd_20y"),
        "20Y Risk-off": _macro6_metric_percent_from_rows(primary, secondary, "risk_off_share_20y"),
        "20Y Cycle": _macro6_metric_int_from_rows(primary, secondary, "cycle_count_20y"),
        "짧은 Cycle": short_cycle_count,
    }


def _macro6_unavailable_preset(preset_key: str, candidate_key: str, role: str, group_label: str, reason: str) -> dict:
    return {
        "kind": "unavailable",
        "label": _MACRO6_DISPLAY_LABEL_OVERRIDES.get(str(candidate_key), f"{group_label} · {role} ({candidate_key})"),
        "benchmark": "S&P500",
        "candidate_key": candidate_key,
        "combo_id": candidate_key,
        "selected_indicators": [],
        "components": [],
        "component_cfgs": {},
        "combo_k": 1,
        "combo_l": 0,
        "combo_m": 0,
        "cfgs": {},
        "metrics": {},
        "review_status": "사용자 선택 완료·운영 미승인 대시보드 검토 후보",
        "unavailable_reason": reason,
        "preset_key": preset_key,
    }


@st.cache_data(show_spinner=False)
def _load_macro6_proxy_final_presets():
    presets = {}
    candidate_defs = list(_MACRO6_COMBO2_CANDIDATES) + list(_MACRO6_COMBO1_CANDIDATES)
    if not os.path.exists(_MACRO6_PROXY_REVIEW_CSV):
        for preset_key, candidate_key, role in candidate_defs:
            group_label = "조합2" if preset_key.startswith("macro6_combo2") else "조합1"
            presets[preset_key] = _macro6_unavailable_preset(
                preset_key,
                candidate_key,
                role,
                group_label,
                "Proxy-only 사용자 검토 후보 source-of-truth 파일이 없습니다.",
            )
        return presets

    review = pd.read_csv(_MACRO6_PROXY_REVIEW_CSV)
    review_by_key = {str(row.get("candidate_key")): row for row in review.to_dict("records") if pd.notna(row.get("candidate_key"))}
    backtest_by_key = {}
    if os.path.exists(_MACRO6_PROXY_BACKTEST_CSV):
        backtest = pd.read_csv(_MACRO6_PROXY_BACKTEST_CSV)
        backtest_by_key = {str(row.get("candidate_key")): row for row in backtest.to_dict("records") if pd.notna(row.get("candidate_key"))}
    component_presets = _load_macro6_top44_component_presets()

    for preset_key, candidate_key, role in _MACRO6_COMBO2_CANDIDATES:
        row = review_by_key.get(candidate_key)
        backtest_row = backtest_by_key.get(candidate_key)
        label = f"조합2 · {role} ({candidate_key})"
        if row is None:
            presets[preset_key] = _macro6_unavailable_preset(
                preset_key,
                candidate_key,
                role,
                "조합2",
                "지정한 사용자 검토 후보 파일에 candidate_key가 없습니다.",
            )
            continue
        raw_components = str(_macro6_safe_row_value(row, "component_keys", "")).strip()
        components = [part.strip() for part in raw_components.split("+") if part.strip()]
        missing = [key for key in components if key not in component_presets]
        try:
            m = int(round(float(_macro6_safe_row_value(row, "m", len(components)))))
            combo_k = int(round(float(_macro6_safe_row_value(row, "start_k"))))
            combo_l = int(round(float(_macro6_safe_row_value(row, "end_l"))))
        except Exception:
            m = len(components)
            combo_k = 1
            combo_l = 0
        if missing or not components or len(components) != m or not (0 <= combo_l < combo_k <= m):
            reasons = []
            if missing:
                reasons.append(f"component 정의 누락: {', '.join(missing)}")
            if not components:
                reasons.append("component_keys가 비어 있습니다.")
            if len(components) != m:
                reasons.append(f"component 수 불일치: {len(components)} / {m}")
            if not (0 <= combo_l < combo_k <= m):
                reasons.append("k/l 조건이 유효하지 않습니다.")
            presets[preset_key] = _macro6_unavailable_preset(
                preset_key,
                candidate_key,
                role,
                "조합2",
                " · ".join(reasons),
            )
            continue
        preset_cfg = {
            "kind": "combo2_final8",
            "label": label,
            "benchmark": "S&P500",
            "candidate_key": candidate_key,
            "combo_id": candidate_key,
            "selected_indicators": components,
            "components": components,
            "component_cfgs": {key: component_presets[key] for key in components},
            "combo_k": combo_k,
            "combo_l": combo_l,
            "combo_m": m,
            "cfgs": {},
            "metrics": _macro6_metrics_from_rows(row, backtest_row),
            "role_tags": role,
            "review_status": "사용자 선택 완료·운영 미승인 대시보드 검토 후보",
            "selection_reason": str(_macro6_safe_row_value(row, "final_selection_reason", _macro6_safe_row_value(row, "selection_reason", ""))).strip(),
            "dashboard_review_focus": str(_macro6_safe_row_value(row, "dashboard_review_focus", "")).strip(),
            "reconstructed_combo_key": "|".join(components) + f"|start_k={combo_k}|end_l={combo_l}",
            "preset_key": preset_key,
        }
        preset_cfg["label"] = _macro6_preset_display_label(preset_cfg)
        presets[preset_key] = preset_cfg

    for preset_key, candidate_key, role in _MACRO6_COMBO1_CANDIDATES:
        row = review_by_key.get(candidate_key)
        backtest_row = backtest_by_key.get(candidate_key)
        label = f"조합1 · {role} ({candidate_key})"
        if row is None:
            presets[preset_key] = _macro6_unavailable_preset(
                preset_key,
                candidate_key,
                role,
                "조합1",
                "지정한 사용자 검토 후보 파일에 candidate_key가 없습니다.",
            )
            continue
        parsed = _parse_macro3_combo_key(
            _macro6_safe_row_value(row, "combo_key", ""),
            indicator_order=_MACRO6_COMPONENT_INDICATOR_ORDER,
        )
        if not parsed["selected_indicators"] or parsed["start_k"] is None or parsed["end_l"] is None:
            presets[preset_key] = _macro6_unavailable_preset(
                preset_key,
                candidate_key,
                role,
                "조합1",
                "조합1 combo_key를 기존 parser로 해석하지 못했습니다.",
            )
            continue
        preset_cfg = {
            "kind": "combo1_final8",
            "label": label,
            "benchmark": "S&P500",
            "candidate_key": candidate_key,
            "combo_id": candidate_key,
            "selected_indicators": parsed["selected_indicators"],
            "combo_k": int(parsed["start_k"]),
            "combo_l": int(parsed["end_l"]),
            "combo_m": len(parsed["selected_indicators"]),
            "cfgs": parsed["cfgs"],
            "metrics": _macro6_metrics_from_rows(row, backtest_row),
            "role_tags": role,
            "review_status": "사용자 선택 완료·운영 미승인 대시보드 검토 후보",
            "selection_reason": str(_macro6_safe_row_value(row, "final_selection_reason", _macro6_safe_row_value(row, "selection_reason", ""))).strip(),
            "dashboard_review_focus": str(_macro6_safe_row_value(row, "dashboard_review_focus", "")).strip(),
            "reconstructed_combo_key": str(_macro6_safe_row_value(row, "combo_key", "")).strip(),
            "preset_key": preset_key,
        }
        preset_cfg["label"] = _macro6_preset_display_label(preset_cfg)
        presets[preset_key] = preset_cfg
    return {key: presets[key] for key, _, _ in candidate_defs if key in presets}


def _macro3_fetch_benchmark_ohlcv(benchmark_name: str, years: int) -> pd.DataFrame:
    benchmark = _get_macro_benchmark(benchmark_name)
    end = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
    df = fetch_ohlcv(benchmark["code"], start, end, interval="1d")
    return pd.DataFrame() if df is None else _macro3_filter_confirmed_us_daily(df.sort_index())


def _macro3_credit_stress_series(years: int, sync_bucket: str | None = None) -> pd.Series:
    if not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE or _MACRO3_AVAILABILITY_CONFIG is None:
        return pd.Series(dtype=float)
    hy = _credit_spread_series("BAMLH0A0HYM2", years + 1, sync_bucket=sync_bucket)
    nfci = _fred("NFCI", years + 1, sync_bucket=sync_bucket)
    vix = _macro3_filter_confirmed_us_daily(_yf_close("^VIX", years + 1, sync_bucket=sync_bucket))
    if COMBO1_EXPANDED_AVAILABILITY_AVAILABLE and _MACRO3_AVAILABILITY_CONFIG is not None:
        snapshot = pd.concat(
            [
                hy.rename("hy_raw") if hy is not None else pd.Series(dtype=float, name="hy_raw"),
                nfci.rename("nfci_raw") if nfci is not None else pd.Series(dtype=float, name="nfci_raw"),
                vix.rename("vix_raw") if vix is not None else pd.Series(dtype=float, name="vix_raw"),
            ],
            axis=1,
        )
        if {"hy_raw", "nfci_raw", "vix_raw"}.issubset(set(snapshot.columns)):
            try:
                return _combo1_build_credit_stress_safe_from_components(
                    snapshot,
                    _MACRO3_AVAILABILITY_CONFIG,
                    require_all_components=True,
                ).dropna()
            except Exception:
                return pd.Series(dtype=float)
    return pd.Series(dtype=float)


def _macro3_get_indicator_raw_series(
    indicator: str,
    years: int,
    benchmark_name: str = "S&P500",
    spx_s: pd.Series | None = None,
    sync_bucket: str | None = None,
):
    benchmark = _get_macro_benchmark(benchmark_name)
    if indicator == "Index":
        if spx_s is None or spx_s.empty:
            spx_s = _yf_close(benchmark["code"], years, sync_bucket=sync_bucket)
        return _macro3_filter_confirmed_us_daily(spx_s).dropna() if spx_s is not None else pd.Series(dtype=float)
    if indicator == "HY":
        return _macro3_apply_indicator_availability(
            "HY",
            (-_credit_spread_series("BAMLH0A0HYM2", years, sync_bucket=sync_bucket)).dropna(),
        ).dropna()
    if indicator == "IG":
        return _macro3_apply_indicator_availability(
            "IG",
            (-_credit_spread_series("BAMLC0A0CM", years, sync_bucket=sync_bucket)).dropna(),
        ).dropna()
    if indicator == "Credit Stress":
        return _macro3_credit_stress_series(years, sync_bucket=sync_bucket)
    if indicator == "VIX":
        return (-_macro3_filter_confirmed_us_daily(_yf_close("^VIX", years, sync_bucket=sync_bucket))).dropna()
    if indicator == "VIX Spread":
        vix = _macro3_filter_confirmed_us_daily(_yf_close("^VIX", years, sync_bucket=sync_bucket))
        vix3m = _macro3_filter_confirmed_us_daily(_yf_close("^VIX3M", years, sync_bucket=sync_bucket))
        if vix.empty or vix3m.empty:
            return pd.Series(dtype=float)
        return (-(vix - vix3m.reindex(vix.index))).dropna()

    bundle = _get_macro_yield_bundle(years, benchmark_name, sync_bucket=sync_bucket)
    if indicator == "10Y Real Yield":
        return _macro3_apply_indicator_availability(
            "10Y Real Yield",
            (-bundle.get("dfii10", pd.Series(dtype=float))).dropna(),
        ).dropna()
    if indicator == "10Y-2Y Spread":
        return _macro3_apply_indicator_availability(
            "10Y-2Y Spread",
            bundle.get("spread_10y2y", pd.Series(dtype=float)).dropna(),
        ).dropna()
    if indicator == "10Y-3M Spread":
        return _macro3_apply_indicator_availability(
            "10Y-3M Spread",
            bundle.get("spread_10y3m", pd.Series(dtype=float)).dropna(),
        ).dropna()
    if indicator == "10Y Nominal Yield Slope":
        return _macro3_apply_indicator_availability(
            "10Y Nominal Yield Slope",
            bundle.get("dgs10", pd.Series(dtype=float)).dropna(),
        ).dropna()
    return pd.Series(dtype=float)


@st.cache_data(ttl=86400, show_spinner=False)
def _macro6_proxy_credit_spread_series(kind: str, years: int = 5, sync_bucket: str | None = None) -> pd.Series:
    """Proxy-only credit spread: DBAA/DAAA - DGS10, same-date observations only."""
    mapping = {
        "HY": ("DBAA", "DGS10", "hy_proxy_only"),
        "IG": ("DAAA", "DGS10", "ig_proxy_only"),
    }
    corp_id, treasury_id, name = mapping.get(str(kind).upper(), (None, None, None))
    if corp_id is None:
        return pd.Series(dtype=float)
    fetch_years = max(int(years) + 2, 6)
    corp = _fred(corp_id, fetch_years, sync_bucket=sync_bucket)
    treasury = _fred(treasury_id, fetch_years, sync_bucket=sync_bucket)
    if corp is None or treasury is None or corp.empty or treasury.empty:
        return pd.Series(dtype=float, name=name)
    joined = pd.concat([corp.rename("corp"), treasury.rename("dgs10")], axis=1, join="inner").dropna().sort_index()
    if joined.empty:
        return pd.Series(dtype=float, name=name)
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=int(years))
    spread = (joined["corp"] - joined["dgs10"]).rename(name)
    return spread.loc[spread.index >= cutoff].dropna()


def _macro6_credit_stress_series(years: int, sync_bucket: str | None = None) -> pd.Series:
    if not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE or _MACRO3_AVAILABILITY_CONFIG is None:
        return pd.Series(dtype=float)
    hy = _macro6_proxy_credit_spread_series("HY", years + 1, sync_bucket=sync_bucket)
    nfci = _fred("NFCI", years + 1, sync_bucket=sync_bucket)
    vix = _macro3_filter_confirmed_us_daily(_yf_close("^VIX", years + 1, sync_bucket=sync_bucket))
    snapshot = pd.concat(
        [
            hy.rename("hy_raw") if hy is not None else pd.Series(dtype=float, name="hy_raw"),
            nfci.rename("nfci_raw") if nfci is not None else pd.Series(dtype=float, name="nfci_raw"),
            vix.rename("vix_raw") if vix is not None else pd.Series(dtype=float, name="vix_raw"),
        ],
        axis=1,
    )
    if not {"hy_raw", "nfci_raw", "vix_raw"}.issubset(set(snapshot.columns)):
        return pd.Series(dtype=float)
    try:
        return _combo1_build_credit_stress_safe_from_components(
            snapshot,
            _MACRO3_AVAILABILITY_CONFIG,
            require_all_components=True,
        ).dropna()
    except Exception:
        return pd.Series(dtype=float)


def _macro6_get_indicator_raw_series(
    indicator: str,
    years: int,
    benchmark_name: str = "S&P500",
    spx_s: pd.Series | None = None,
    sync_bucket: str | None = None,
):
    if indicator == "VIX Spread":
        expected_latest, benchmark_index = _macro6_expected_latest_trading_date(
            benchmark_name=benchmark_name,
            years=years,
            spx_s=spx_s,
            sync_bucket=sync_bucket,
        )
        meta = _macro6_vix_spread_with_fallback(
            years=years,
            benchmark_name=benchmark_name,
            expected_latest_date=expected_latest,
            benchmark_dates=tuple(pd.Timestamp(d).isoformat() for d in benchmark_index),
            sync_bucket=sync_bucket,
        )
        return meta.get("series", pd.Series(dtype=float)).dropna()
    if indicator == "HY":
        return _macro3_apply_indicator_availability(
            "HY",
            (-_macro6_proxy_credit_spread_series("HY", years, sync_bucket=sync_bucket)).dropna(),
        ).dropna()
    if indicator == "IG":
        return _macro3_apply_indicator_availability(
            "IG",
            (-_macro6_proxy_credit_spread_series("IG", years, sync_bucket=sync_bucket)).dropna(),
        ).dropna()
    if indicator == "Credit Stress":
        return _macro6_credit_stress_series(years, sync_bucket=sync_bucket)
    return _macro3_get_indicator_raw_series(
        indicator=indicator,
        years=years,
        benchmark_name=benchmark_name,
        spx_s=spx_s,
        sync_bucket=sync_bucket,
    )


def _macro6_source_mode(source_mode: str | None = None) -> str:
    return "official_frozen" if str(source_mode or "").strip() == "official_frozen" else "live_raw"


@st.cache_data(show_spinner=False)
def _macro6_load_official_frozen_proxy_snapshot():
    if not os.path.exists(_MACRO6_OFFICIAL_FROZEN_SNAPSHOT_PARQUET):
        return pd.DataFrame()
    if not os.path.exists(_MACRO6_OFFICIAL_FROZEN_PROXY_RAW_PARQUET):
        return pd.DataFrame()
    if not COMBO1_EXPANDED_AVAILABILITY_AVAILABLE or _MACRO3_AVAILABILITY_CONFIG is None:
        return pd.DataFrame()
    snapshot = pd.read_parquet(_MACRO6_OFFICIAL_FROZEN_SNAPSHOT_PARQUET)
    if "date" in snapshot.columns:
        snapshot["date"] = pd.to_datetime(snapshot["date"]).dt.normalize()
        snapshot = snapshot.set_index("date")
    else:
        snapshot.index = pd.to_datetime(snapshot.index).normalize()
    snapshot = snapshot.sort_index()
    fred = pd.read_parquet(_MACRO6_OFFICIAL_FROZEN_PROXY_RAW_PARQUET)
    fred.index = pd.to_datetime(fred.index).normalize()
    required = {"DBAA", "DAAA", "DGS10"}
    if not required.issubset(set(fred.columns)):
        return pd.DataFrame()
    baa = pd.concat([fred["DBAA"].rename("corp"), fred["DGS10"].rename("dgs10")], axis=1, join="inner").dropna()
    aaa = pd.concat([fred["DAAA"].rename("corp"), fred["DGS10"].rename("dgs10")], axis=1, join="inner").dropna()
    if baa.empty or aaa.empty:
        return pd.DataFrame()
    out = snapshot.copy()
    out["hy_raw"] = (baa["corp"] - baa["dgs10"]).reindex(out.index)
    out["ig_raw"] = (aaa["corp"] - aaa["dgs10"]).reindex(out.index)
    out["hy_safe"] = -out["hy_raw"]
    out["ig_safe"] = -out["ig_raw"]
    try:
        out["credit_stress_safe"] = _combo1_build_credit_stress_safe_from_components(
            out,
            _MACRO3_AVAILABILITY_CONFIG,
            require_all_components=True,
        ).reindex(out.index)
        out["credit_stress_raw"] = -out["credit_stress_safe"]
    except Exception:
        return pd.DataFrame()
    return out


@st.cache_data(show_spinner=False)
def _macro6_load_official_baseline_indicator_state(indicator: str, param_id: str):
    needed_indicator = str(indicator)
    needed_param_id = str(param_id)
    for path in _MACRO6_OFFICIAL_BASELINE_TIMELINE_SOURCES:
        if not os.path.exists(path):
            continue
        try:
            frame = pd.read_parquet(path, columns=["date", "indicator", "param_id", "risk_state"])
        except Exception:
            continue
        frame = frame.loc[
            frame["indicator"].astype(str).eq(needed_indicator)
            & frame["param_id"].astype(str).eq(needed_param_id)
        ].copy()
        if frame.empty:
            continue
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        series = frame.drop_duplicates("date").set_index("date")["risk_state"].sort_index()
        if not series.empty:
            return series.astype(bool)
    return pd.Series(dtype=bool)


def _macro6_official_frozen_indicator_signal_frame(
    indicator: str,
    cfg: dict,
    benchmark_index: pd.DatetimeIndex,
):
    if not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame()
    benchmark_index = pd.DatetimeIndex(pd.to_datetime(benchmark_index)).normalize()
    if indicator not in _MACRO6_CREDIT_PROXY_INDICATORS:
        param_id = str(cfg.get("raw", "")).strip()
        if not param_id:
            return pd.DataFrame()
        baseline = _macro6_load_official_baseline_indicator_state(indicator, param_id)
        if baseline.empty:
            return pd.DataFrame()
        state = baseline.reindex(benchmark_index)
        if state.isna().any():
            return pd.DataFrame()
        values = state.astype(bool).to_numpy()
        starts = values & ~np.r_[False, values[:-1]]
        ends = (~values) & np.r_[False, values[:-1]]
        return pd.DataFrame(
            {
                "risk_state": values.astype(bool),
                "risk_start_signal": starts.astype(bool),
                "risk_end_signal": ends.astype(bool),
                "valid_signal": True,
            },
            index=benchmark_index,
        )

    snapshot = _macro6_load_official_frozen_proxy_snapshot()
    if snapshot.empty:
        return pd.DataFrame()
    kind = cfg.get("kind", "level")
    if indicator == "HY":
        raw_series = _combo1_apply_availability_lag(
            snapshot["hy_safe"].dropna(),
            "HY",
            _MACRO3_AVAILABILITY_CONFIG,
        ).dropna()
    elif indicator == "IG":
        raw_series = _combo1_apply_availability_lag(
            snapshot["ig_safe"].dropna(),
            "IG",
            _MACRO3_AVAILABILITY_CONFIG,
        ).dropna()
    elif indicator == "Credit Stress":
        raw_series = _combo1_build_credit_stress_safe_from_components(
            snapshot,
            _MACRO3_AVAILABILITY_CONFIG,
            require_all_components=True,
        ).dropna()
    else:
        return pd.DataFrame()
    if raw_series.empty:
        return pd.DataFrame()
    if kind == "yield_slope":
        signal = _combo1_compute_yield_slope_signal_frame(
            dgs10=raw_series,
            slope_window=int(cfg["slope_window"]),
            ema_span=int(cfg["ema"]),
            threshold_window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
        )
    else:
        signal = _combo1_compute_dynamic_quantile_signal_frame(
            series=raw_series,
            window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
            ema_span=int(cfg["ema"]),
        )
    return _combo1_align_signal_to_benchmark(signal, benchmark_index)


def _macro6_get_indicator_signal_frame(
    indicator: str,
    cfg: dict,
    benchmark_index: pd.DatetimeIndex,
    years: int,
    benchmark_name: str = "S&P500",
    spx_s: pd.Series | None = None,
    sync_bucket: str | None = None,
):
    if not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame()
    kind = cfg.get("kind", "level")
    if kind == "bollinger":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, years)
        if ohlc.empty:
            return pd.DataFrame()
        signal = _combo1_compute_bollinger_signal_frame(
            close=ohlc["Close"],
            high=ohlc["High"],
            low=ohlc["Low"],
            window=int(cfg["window"]),
            std_multiplier=float(cfg["std"]),
        )
        aligned = _combo1_align_signal_to_benchmark(signal, benchmark_index)
        for col in ["bb_middle", "bb_upper", "bb_lower"]:
            if col in signal.columns:
                source = signal.copy()
                source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
                source = source.sort_index().loc[~source.index.duplicated(keep="last")]
                aligned[col] = source[col].reindex(aligned.index).ffill()
        return aligned
    if kind == "rsi":
        if spx_s is None or spx_s.empty:
            benchmark = _get_macro_benchmark(benchmark_name)
            spx_s = _yf_close(benchmark["code"], years, sync_bucket=sync_bucket)
        close = _macro3_filter_confirmed_us_daily(spx_s)
        if close is None or close.empty:
            return pd.DataFrame()
        signal = _combo1_compute_rsi_signal_frame(
            close=close,
            period=int(cfg["period"]),
            lookback=int(cfg["lookback"]),
            lower_quantile=float(cfg["lower_q"]),
            upper_quantile=float(cfg["upper_q"]),
        )
        aligned = _combo1_align_signal_to_benchmark(signal, benchmark_index)
        source = signal.copy()
        source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
        source = source.sort_index().loc[~source.index.duplicated(keep="last")]
        for col in ["close", "rsi", "dyn_lower", "dyn_upper", "buy_on", "sell_on"]:
            if col in source.columns:
                aligned[col] = source[col].reindex(aligned.index).ffill()
        return aligned

    raw_series = _macro6_get_indicator_raw_series(
        indicator=indicator,
        years=years,
        benchmark_name=benchmark_name,
        spx_s=spx_s,
        sync_bucket=sync_bucket,
    )
    if raw_series is None or raw_series.empty:
        return pd.DataFrame()
    if kind == "yield_slope":
        signal = _combo1_compute_yield_slope_signal_frame(
            dgs10=raw_series,
            slope_window=int(cfg["slope_window"]),
            ema_span=int(cfg["ema"]),
            threshold_window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
        )
    else:
        signal = _combo1_compute_dynamic_quantile_signal_frame(
            series=raw_series,
            window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
            ema_span=int(cfg["ema"]),
        )
    aligned = _combo1_align_signal_to_benchmark(signal, benchmark_index)
    source = signal.copy()
    source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
    source = source.sort_index().loc[~source.index.duplicated(keep="last")]
    for col in [c for c in source.columns if c.startswith("ema")] + ["value", "risk_start_line", "risk_end_line"]:
        if col in source.columns:
            aligned[col] = source[col].reindex(aligned.index).ffill()
    return aligned


def _macro3_get_indicator_signal_frame(
    indicator: str,
    cfg: dict,
    benchmark_index: pd.DatetimeIndex,
    years: int,
    benchmark_name: str = "S&P500",
    spx_s: pd.Series | None = None,
    sync_bucket: str | None = None,
):
    if not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame()
    kind = cfg.get("kind", "level")
    if kind == "bollinger":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, years)
        if ohlc.empty:
            return pd.DataFrame()
        signal = _combo1_compute_bollinger_signal_frame(
            close=ohlc["Close"],
            high=ohlc["High"],
            low=ohlc["Low"],
            window=int(cfg["window"]),
            std_multiplier=float(cfg["std"]),
        )
        aligned = _combo1_align_signal_to_benchmark(signal, benchmark_index)
        for col in ["bb_middle", "bb_upper", "bb_lower"]:
            if col in signal.columns:
                source = signal.copy()
                source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
                source = source.sort_index().loc[~source.index.duplicated(keep="last")]
                aligned[col] = source[col].reindex(aligned.index).ffill()
        return aligned

    raw_series = _macro3_get_indicator_raw_series(
        indicator=indicator,
        years=years,
        benchmark_name=benchmark_name,
        spx_s=spx_s,
        sync_bucket=sync_bucket,
    )
    if raw_series is None or raw_series.empty:
        return pd.DataFrame()
    if kind == "yield_slope":
        signal = _combo1_compute_yield_slope_signal_frame(
            dgs10=raw_series,
            slope_window=int(cfg["slope_window"]),
            ema_span=int(cfg["ema"]),
            threshold_window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
        )
    else:
        signal = _combo1_compute_dynamic_quantile_signal_frame(
            series=raw_series,
            window=int(cfg["window"]),
            start_quantile=float(cfg["start"]),
            end_quantile=float(cfg["end"]),
            ema_span=int(cfg["ema"]),
        )
    aligned = _combo1_align_signal_to_benchmark(signal, benchmark_index)
    source = signal.copy()
    source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
    source = source.sort_index().loc[~source.index.duplicated(keep="last")]
    for col in [c for c in source.columns if c.startswith("ema")] + ["value", "risk_start_line", "risk_end_line"]:
        if col in source.columns:
            aligned[col] = source[col].reindex(aligned.index).ffill()
    return aligned


def _compute_macro3_combo_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    selected_indicators,
    cfgs: dict,
    combo_k: int,
    combo_l: int,
    sync_bucket: str | None = None,
):
    if spx_s is None or spx_s.empty or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame(), []
    selected_indicators = list(selected_indicators or [])
    if not selected_indicators:
        return pd.DataFrame(), []
    frames = {}
    active_indicators = []
    fetch_years = max(3, int(np.ceil(len(spx_s.dropna()) / 252.0)) + 2)
    for indicator in selected_indicators:
        cfg = cfgs.get(indicator)
        if not cfg:
            return pd.DataFrame(), []
        signal_df = _macro3_get_indicator_signal_frame(
            indicator=indicator,
            cfg=cfg,
            benchmark_index=spx_s.index,
            years=fetch_years,
            benchmark_name=benchmark_name,
            spx_s=spx_s,
            sync_bucket=sync_bucket,
        )
        if signal_df.empty:
            return pd.DataFrame(), []
        key = _macro3_indicator_key(indicator)
        frames[indicator] = signal_df.rename(columns={
            "risk_state": f"{key}_flag",
            "risk_start_signal": f"{key}_start_signal",
            "risk_end_signal": f"{key}_end_signal",
        })[[f"{key}_flag", f"{key}_start_signal", f"{key}_end_signal"]]
        active_indicators.append(indicator)
    if not frames:
        return pd.DataFrame(), []
    combo = pd.concat(frames.values(), axis=1).reindex(spx_s.index).fillna(False)
    flag_cols = [f"{_macro3_indicator_key(name)}_flag" for name in active_indicators]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    state, starts, ends = _combo1_build_hysteresis_combo_state(combo["active_count"].to_numpy(), int(combo_k), int(combo_l))
    combo["combo_risk_state"] = state.astype(bool)
    combo["combo_start_signal"] = starts.astype(bool)
    combo["combo_end_signal"] = ends.astype(bool)
    combo[flag_cols + [c for c in combo.columns if c.endswith("_signal")]] = combo[
        flag_cols + [c for c in combo.columns if c.endswith("_signal")]
    ].astype(bool)
    return combo, active_indicators


def _compute_macro3_combo2_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    preset_cfg: dict,
    sync_bucket: str | None = None,
):
    if spx_s is None or spx_s.empty or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame(), []
    components = list(preset_cfg.get("components", []))
    component_cfgs = dict(preset_cfg.get("component_cfgs", {}))
    if not components:
        return pd.DataFrame(), []
    frames = {}
    active_components = []
    for component_key in components:
        component_cfg = component_cfgs.get(component_key)
        if not component_cfg:
            return pd.DataFrame(), []
        component_combo, component_active = _compute_macro3_combo_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            selected_indicators=component_cfg.get("selected_indicators", []),
            cfgs=component_cfg.get("cfgs", {}),
            combo_k=int(component_cfg.get("combo_k", 1)),
            combo_l=int(component_cfg.get("combo_l", 0)),
            sync_bucket=sync_bucket,
        )
        if component_combo.empty or not component_active:
            return pd.DataFrame(), []
        key = _macro3_indicator_key(component_key)
        frames[component_key] = component_combo.rename(columns={
            "combo_risk_state": f"{key}_flag",
            "combo_start_signal": f"{key}_start_signal",
            "combo_end_signal": f"{key}_end_signal",
        })[[f"{key}_flag", f"{key}_start_signal", f"{key}_end_signal"]]
        active_components.append(component_key)
    if not frames:
        return pd.DataFrame(), []
    combo = pd.concat(frames.values(), axis=1).reindex(spx_s.index).fillna(False)
    flag_cols = [f"{_macro3_indicator_key(name)}_flag" for name in active_components]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    state, starts, ends = _combo1_build_hysteresis_combo_state(
        combo["active_count"].to_numpy(),
        int(preset_cfg.get("combo_k", 1)),
        int(preset_cfg.get("combo_l", 0)),
    )
    combo["combo_risk_state"] = state.astype(bool)
    combo["combo_start_signal"] = starts.astype(bool)
    combo["combo_end_signal"] = ends.astype(bool)
    combo[flag_cols + [c for c in combo.columns if c.endswith("_signal")]] = combo[
        flag_cols + [c for c in combo.columns if c.endswith("_signal")]
    ].astype(bool)
    return combo, active_components


def _compute_macro3_preset_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    preset_cfg: dict,
    sync_bucket: str | None = None,
):
    if preset_cfg.get("kind") == "combo2_final8":
        return _compute_macro3_combo2_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            preset_cfg=preset_cfg,
            sync_bucket=sync_bucket,
        )
    return _compute_macro3_combo_signal_frame(
        spx_s=spx_s,
        benchmark_name=benchmark_name,
        selected_indicators=preset_cfg.get("selected_indicators", []),
        cfgs=preset_cfg.get("cfgs", {}),
        combo_k=int(preset_cfg.get("combo_k", 1)),
        combo_l=int(preset_cfg.get("combo_l", 0)),
        sync_bucket=sync_bucket,
    )


def _compute_macro6_combo_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    selected_indicators,
    cfgs: dict,
    combo_k: int,
    combo_l: int,
    sync_bucket: str | None = None,
    source_mode: str | None = None,
):
    if spx_s is None or spx_s.empty or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame(), []
    source_mode = _macro6_source_mode(source_mode)
    selected_indicators = list(selected_indicators or [])
    if not selected_indicators:
        return pd.DataFrame(), []
    frames = {}
    active_indicators = []
    fetch_years = max(3, int(np.ceil(len(spx_s.dropna()) / 252.0)) + 2)
    for indicator in selected_indicators:
        cfg = cfgs.get(indicator)
        if not cfg:
            return pd.DataFrame(), []
        if source_mode == "official_frozen":
            signal_df = _macro6_official_frozen_indicator_signal_frame(
                indicator=indicator,
                cfg=cfg,
                benchmark_index=spx_s.index,
            )
        else:
            signal_df = _macro6_get_indicator_signal_frame(
                indicator=indicator,
                cfg=cfg,
                benchmark_index=spx_s.index,
                years=fetch_years,
                benchmark_name=benchmark_name,
                spx_s=spx_s,
                sync_bucket=sync_bucket,
            )
        if signal_df.empty:
            return pd.DataFrame(), []
        key = _macro3_indicator_key(indicator)
        frames[indicator] = signal_df.rename(columns={
            "risk_state": f"{key}_flag",
            "risk_start_signal": f"{key}_start_signal",
            "risk_end_signal": f"{key}_end_signal",
        })[[f"{key}_flag", f"{key}_start_signal", f"{key}_end_signal"]]
        active_indicators.append(indicator)
    if not frames:
        return pd.DataFrame(), []
    combo = pd.concat(frames.values(), axis=1).reindex(spx_s.index).fillna(False)
    flag_cols = [f"{_macro3_indicator_key(name)}_flag" for name in active_indicators]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    state, starts, ends = _combo1_build_hysteresis_combo_state(combo["active_count"].to_numpy(), int(combo_k), int(combo_l))
    combo["combo_risk_state"] = state.astype(bool)
    combo["combo_start_signal"] = starts.astype(bool)
    combo["combo_end_signal"] = ends.astype(bool)
    combo[flag_cols + [c for c in combo.columns if c.endswith("_signal")]] = combo[
        flag_cols + [c for c in combo.columns if c.endswith("_signal")]
    ].astype(bool)
    return combo, active_indicators


def _compute_macro6_combo2_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    preset_cfg: dict,
    sync_bucket: str | None = None,
    source_mode: str | None = None,
):
    if spx_s is None or spx_s.empty or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return pd.DataFrame(), []
    source_mode = _macro6_source_mode(source_mode)
    components = list(preset_cfg.get("components", []))
    component_cfgs = dict(preset_cfg.get("component_cfgs", {}))
    if not components:
        return pd.DataFrame(), []
    frames = {}
    active_components = []
    for component_key in components:
        component_cfg = component_cfgs.get(component_key)
        if not component_cfg:
            return pd.DataFrame(), []
        component_combo, component_active = _compute_macro6_combo_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            selected_indicators=component_cfg.get("selected_indicators", []),
            cfgs=component_cfg.get("cfgs", {}),
            combo_k=int(component_cfg.get("combo_k", 1)),
            combo_l=int(component_cfg.get("combo_l", 0)),
            sync_bucket=sync_bucket,
            source_mode=source_mode,
        )
        if component_combo.empty or not component_active:
            return pd.DataFrame(), []
        key = _macro3_indicator_key(component_key)
        frames[component_key] = component_combo.rename(columns={
            "combo_risk_state": f"{key}_flag",
            "combo_start_signal": f"{key}_start_signal",
            "combo_end_signal": f"{key}_end_signal",
        })[[f"{key}_flag", f"{key}_start_signal", f"{key}_end_signal"]]
        active_components.append(component_key)
    if not frames:
        return pd.DataFrame(), []
    combo = pd.concat(frames.values(), axis=1).reindex(spx_s.index).fillna(False)
    flag_cols = [f"{_macro3_indicator_key(name)}_flag" for name in active_components]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    state, starts, ends = _combo1_build_hysteresis_combo_state(
        combo["active_count"].to_numpy(),
        int(preset_cfg.get("combo_k", 1)),
        int(preset_cfg.get("combo_l", 0)),
    )
    combo["combo_risk_state"] = state.astype(bool)
    combo["combo_start_signal"] = starts.astype(bool)
    combo["combo_end_signal"] = ends.astype(bool)
    combo[flag_cols + [c for c in combo.columns if c.endswith("_signal")]] = combo[
        flag_cols + [c for c in combo.columns if c.endswith("_signal")]
    ].astype(bool)
    return combo, active_components


def _compute_macro6_preset_signal_frame(
    spx_s: pd.Series,
    benchmark_name: str,
    preset_cfg: dict,
    sync_bucket: str | None = None,
    source_mode: str | None = None,
):
    if preset_cfg.get("kind") == "combo2_final8":
        return _compute_macro6_combo2_signal_frame(
            spx_s=spx_s,
            benchmark_name=benchmark_name,
            preset_cfg=preset_cfg,
            sync_bucket=sync_bucket,
            source_mode=source_mode,
        )
    return _compute_macro6_combo_signal_frame(
        spx_s=spx_s,
        benchmark_name=benchmark_name,
        selected_indicators=preset_cfg.get("selected_indicators", []),
        cfgs=preset_cfg.get("cfgs", {}),
        combo_k=int(preset_cfg.get("combo_k", 1)),
        combo_l=int(preset_cfg.get("combo_l", 0)),
        sync_bucket=sync_bucket,
        source_mode=source_mode,
    )


def _build_macro3_combo_event_df(
    combo: pd.DataFrame,
    active_indicators,
    benchmark_name: str,
    selected_indicators,
    cfgs: dict,
    combo_k: int,
    combo_l: int,
):
    if combo is None or combo.empty:
        return pd.DataFrame()
    ordered = [name for name in list(selected_indicators or []) if name in active_indicators]
    event_df = combo.copy().rename_axis("date").reset_index()
    event_df["date"] = pd.to_datetime(event_df["date"])
    event_df["prev_active_count"] = event_df["active_count"].shift(1).fillna(0).astype(int)
    event_df["combo_state_before"] = event_df["combo_risk_state"].shift(1).fillna(False).astype(bool)
    label_cols = []
    for indicator in ordered:
        flag_col = f"{_macro3_indicator_key(indicator)}_flag"
        if flag_col in event_df.columns:
            label_cols.append((indicator, flag_col))

    def _flag_text(row, expect_true: bool) -> str:
        labels = [_MACRO3_INDICATOR_LABELS.get(name, name) for name, col in label_cols if bool(row.get(col, False)) is expect_true]
        return ", ".join(labels)

    def _flag_bits(row) -> str:
        return "/".join(["1" if bool(row.get(col, False)) else "0" for _, col in label_cols])

    event_df["active_flags"] = event_df.apply(lambda r: _flag_text(r, True), axis=1)
    event_df["inactive_flags"] = event_df.apply(lambda r: _flag_text(r, False), axis=1)
    event_df["prev_active_flags"] = event_df["active_flags"].shift(1).fillna("")
    event_df["prev_inactive_flags"] = event_df["inactive_flags"].shift(1).fillna("")
    event_df["flag_state_string"] = event_df.apply(_flag_bits, axis=1)
    event_df["selected_labels"] = ", ".join([_MACRO3_INDICATOR_LABELS.get(name, name) for name in ordered])
    event_df["benchmark_name"] = benchmark_name
    event_df["combo_k"] = int(combo_k)
    event_df["combo_l"] = int(combo_l)
    event_df["combo_n"] = len(ordered)
    event_df["param_signature"] = " | ".join([f"{name}={cfgs[name]['raw']}" for name in ordered if name in cfgs])
    event_df["combo_label"] = " + ".join(ordered)
    return event_df


def make_macro3_combo_dynamic_chart(
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    return_debug: bool = False,
    sync_bucket: str | None = None,
):
    benchmark = _get_macro_benchmark(benchmark_name)
    visible_spx = _macro3_filter_confirmed_us_daily(_yf_close(benchmark["code"], years, sync_bucket=sync_bucket))
    if visible_spx is None or visible_spx.empty:
        return (None, pd.DataFrame()) if return_debug else None
    warmup_years = max(years + 2, 5)
    combo_spx = _macro3_filter_confirmed_us_daily(_yf_close(benchmark["code"], warmup_years, sync_bucket=sync_bucket))
    if combo_spx is None or combo_spx.empty:
        combo_spx = visible_spx
    combo, active_indicators = _compute_macro3_preset_signal_frame(
        spx_s=combo_spx,
        benchmark_name=benchmark_name,
        preset_cfg=preset_cfg,
        sync_bucket=sync_bucket,
    )
    if combo.empty or not active_indicators:
        return (None, pd.DataFrame()) if return_debug else None
    combo = combo.loc[combo.index >= visible_spx.dropna().index.min()].copy()
    spx_aligned = visible_spx.reindex(combo.index).dropna()
    combo = combo.reindex(spx_aligned.index)
    event_df = _build_macro3_combo_event_df(
        combo=combo,
        active_indicators=active_indicators,
        benchmark_name=benchmark_name,
        selected_indicators=preset_cfg.get("selected_indicators", []),
        cfgs=preset_cfg.get("cfgs", {}),
        combo_k=int(preset_cfg.get("combo_k", 1)),
        combo_l=int(preset_cfg.get("combo_l", 0)),
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark["label"],
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
        hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{benchmark['label']} %{{y:,.1f}}<extra></extra>",
    ))
    _add_macro_combo_risk_cycle_background(fig, event_df, spx_aligned.index)
    start_rows = event_df.loc[event_df["combo_start_signal"]].copy()
    end_rows = event_df.loc[event_df["combo_end_signal"]].copy()
    start_y = spx_aligned.reindex(pd.to_datetime(start_rows["date"])) if not start_rows.empty else pd.Series(dtype=float)
    end_y = spx_aligned.reindex(pd.to_datetime(end_rows["date"])) if not end_rows.empty else pd.Series(dtype=float)
    if not start_rows.empty and not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name="리스크 시작",
            mode="markers", marker=dict(symbol="triangle-down", size=10, color="rgba(210,55,55,0.95)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>리스크 시작: %{y:,.2f}<extra></extra>",
        ))
    if not end_rows.empty and not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name="리스크 종료",
            mode="markers", marker=dict(symbol="triangle-up", size=10, color="rgba(80,160,255,0.92)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>리스크 종료: %{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        **_ml(
            f"⓪ 최종 후보 리스크 사이클 ({benchmark['label']}, {int(preset_cfg.get('combo_k', 1))}/{len(active_indicators)}, 종료≤{int(preset_cfg.get('combo_l', 0))})",
            height=300,
        ),
    )
    fig.add_annotation(
        xref="paper", yref="paper", x=0.01, y=0.98, showarrow=False,
        text=f"<b>조합</b>: {event_df['selected_labels'].iloc[0]}",
        font=dict(size=11, color="#C8C8C8"),
        align="left",
        bgcolor="rgba(0,0,0,0.18)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
        borderpad=4,
    )
    return (fig, event_df) if return_debug else fig


def _macro6_event_metadata(preset_cfg: dict, active_indicators: list[str]) -> tuple[list[str], dict]:
    if preset_cfg.get("kind") == "combo2_final8":
        return list(active_indicators), {}
    return list(preset_cfg.get("selected_indicators", [])), dict(preset_cfg.get("cfgs", {}))


def _macro6_build_event_df(combo: pd.DataFrame, active_indicators, benchmark_name: str, preset_cfg: dict) -> pd.DataFrame:
    selected, cfgs = _macro6_event_metadata(preset_cfg, list(active_indicators or []))
    return _build_macro3_combo_event_df(
        combo=combo,
        active_indicators=active_indicators,
        benchmark_name=benchmark_name,
        selected_indicators=selected,
        cfgs=cfgs,
        combo_k=int(preset_cfg.get("combo_k", 1)),
        combo_l=int(preset_cfg.get("combo_l", 0)),
    )


def _make_macro6_combo_chart_from_snapshot(
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    snapshot: dict,
    return_debug: bool = False,
):
    combo_full = snapshot.get("combo_frame", pd.DataFrame()) if snapshot else pd.DataFrame()
    spx_full = snapshot.get("spx_s", pd.Series(dtype=float)) if snapshot else pd.Series(dtype=float)
    active_indicators = snapshot.get("active_indicators", []) if snapshot else []
    if combo_full is None or combo_full.empty or spx_full is None or spx_full.empty:
        return (None, pd.DataFrame()) if return_debug else None
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=int(years))
    visible_spx = spx_full.loc[spx_full.index >= cutoff].dropna()
    if visible_spx.empty:
        visible_spx = spx_full.dropna()
    combo = combo_full.loc[combo_full.index >= visible_spx.index.min()].copy()
    spx_aligned = visible_spx.reindex(combo.index).dropna()
    combo = combo.reindex(spx_aligned.index)
    event_df = _macro6_build_event_df(combo, active_indicators, benchmark_name, preset_cfg)
    benchmark = _get_macro_benchmark(benchmark_name)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark["label"],
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
        hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{benchmark['label']} %{{y:,.1f}}<extra></extra>",
    ))
    _add_macro_combo_risk_cycle_background(fig, event_df, spx_aligned.index)
    start_rows = event_df.loc[event_df["combo_start_signal"]].copy()
    end_rows = event_df.loc[event_df["combo_end_signal"]].copy()
    start_y = spx_aligned.reindex(pd.to_datetime(start_rows["date"])) if not start_rows.empty else pd.Series(dtype=float)
    end_y = spx_aligned.reindex(pd.to_datetime(end_rows["date"])) if not end_rows.empty else pd.Series(dtype=float)
    if not start_rows.empty and not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name="리스크 시작",
            mode="markers", marker=dict(symbol="triangle-down", size=10, color="rgba(210,55,55,0.95)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>리스크 시작: %{y:,.2f}<extra></extra>",
        ))
    if not end_rows.empty and not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name="리스크 종료",
            mode="markers", marker=dict(symbol="triangle-up", size=10, color="rgba(80,160,255,0.92)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>리스크 종료: %{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        **_ml(
            f"⓪ 최종 후보 리스크 사이클 ({benchmark['label']}, {int(preset_cfg.get('combo_k', 1))}/{len(active_indicators)}, 종료≤{int(preset_cfg.get('combo_l', 0))})",
            height=300,
        ),
    )
    labels = event_df["selected_labels"].iloc[0] if not event_df.empty and "selected_labels" in event_df.columns else ""
    fig.add_annotation(
        xref="paper", yref="paper", x=0.01, y=0.98, showarrow=False,
        text=f"<b>조합</b>: {labels}",
        font=dict(size=11, color="#C8C8C8"),
        align="left",
        bgcolor="rgba(0,0,0,0.18)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
        borderpad=4,
    )
    return (fig, event_df) if return_debug else fig


@st.cache_data(
    ttl=7200,
    max_entries=64,
    show_spinner=False,
)
def _compute_macro6_operating_snapshot_cached(preset_cfg: dict, sync_bucket: str | None = None):
    benchmark_name = preset_cfg.get("benchmark", "S&P500")
    benchmark = _get_macro_benchmark(benchmark_name)
    spx_s = _macro3_filter_confirmed_us_daily(_yf_close(benchmark["code"], 25, sync_bucket=sync_bucket))
    if spx_s is None or spx_s.empty:
        return None
    combo, active_indicators = _compute_macro6_preset_signal_frame(
        spx_s=spx_s,
        benchmark_name=benchmark_name,
        preset_cfg=preset_cfg,
        sync_bucket=sync_bucket,
    )
    if combo.empty or not active_indicators:
        return None
    event_df = _macro6_build_event_df(combo, active_indicators, benchmark_name, preset_cfg)
    if event_df.empty:
        return None
    ordered = event_df.sort_values("date").reset_index(drop=True)
    latest = ordered.iloc[-1]
    current_state = bool(latest.get("combo_risk_state", False))
    start_idx = len(ordered) - 1
    while start_idx > 0 and bool(ordered.iloc[start_idx - 1].get("combo_risk_state", False)) == current_state:
        start_idx -= 1
    return {
        "spx_s": spx_s,
        "combo_frame": combo,
        "event_frame": event_df,
        "active_indicators": list(active_indicators),
        "is_on": current_state,
        "on_count": int(latest.get("active_count", 0)),
        "total_count": len(active_indicators),
        "start_count": int(preset_cfg.get("combo_k", len(active_indicators))),
        "basis_date": pd.Timestamp(latest.get("date")).normalize(),
        "state_start_date": None if start_idx == 0 else pd.Timestamp(ordered.iloc[start_idx].get("date")).normalize(),
        "state_duration_days": int(len(ordered) - start_idx),
    }


def _compute_macro6_operating_snapshot(preset_cfg: dict, sync_bucket: str | None = None):
    return _compute_macro6_operating_snapshot_cached(preset_cfg=preset_cfg, sync_bucket=sync_bucket)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_macro3_signal_latest_date(indicator: str, years: int, benchmark_name: str = "S&P500", sync_bucket: str | None = None):
    if indicator == "Bollinger Band":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, years)
        return None if ohlc.empty else ohlc.index.max()
    series = _macro3_get_indicator_raw_series(indicator, years, benchmark_name=benchmark_name, sync_bucket=sync_bucket)
    return None if series is None or series.empty else series.index.max()


def _build_macro3_status_panel(
    benchmark_name: str,
    years: int,
    preset_cfg: dict,
    combo_event_df: pd.DataFrame,
    sync_bucket: str | None = None,
):
    if combo_event_df is None or combo_event_df.empty:
        return "", ""
    latest = combo_event_df.sort_values("date").iloc[-1]
    combo_state = bool(latest.get("combo_risk_state", False))
    active_count = int(latest.get("active_count", 0))
    combo_n = int(latest.get("combo_n", len(preset_cfg.get("selected_indicators", []))))
    combo_k = int(latest.get("combo_k", preset_cfg.get("combo_k", max(1, combo_n))))
    basis_date = _macro_date_text(latest.get("date"))
    expected_latest, expected_index = _macro6_expected_latest_trading_date(
        benchmark_name=benchmark_name,
        years=years,
        sync_bucket=sync_bucket,
    )
    basis_lag_days = _macro6_lag_trading_days(expected_latest, latest.get("date"), expected_index)
    if basis_lag_days is not None and basis_lag_days > 0:
        basis_date = (
            f"{basis_date} "
            f"<span style='color:#FFB36E;font-weight:700;'>"
            f"· Yahoo 데이터 {basis_lag_days}거래일 지연 · 실제 기준일 {_macro_date_text(latest.get('date'))}"
            "</span>"
        )
    next_exec = _macro3_next_execution_date(latest.get("date"), combo_event_df.get("date", []))
    next_exec_date = _macro_date_text(next_exec) if next_exec is not None else "확인 필요"
    status_text = "리스크 사이클 ON" if combo_state else "리스크 사이클 OFF"
    status_color = "#FF8C69" if combo_state else "#4BFFB3"
    if bool(latest.get("combo_start_signal", False)):
        execution_text = f"리스크 시작 신호 · T+1 {next_exec_date} 축소 검토"
    elif bool(latest.get("combo_end_signal", False)):
        execution_text = f"리스크 종료 신호 · T+1 {next_exec_date} 재진입 검토"
    else:
        execution_text = "신규 전환 신호 없음"
    active_labels = []
    entries = []
    if preset_cfg.get("kind") == "combo2_final8":
        component_cfgs = preset_cfg.get("component_cfgs", {})
        for component_key in preset_cfg.get("components", []):
            key = _macro3_indicator_key(component_key)
            is_on = bool(latest.get(f"{key}_flag", False))
            label = _macro3_component_label(component_key, component_cfgs.get(component_key))
            if is_on:
                active_labels.append(label)
            data_status = _macro3_component_data_status(
                component_cfgs.get(component_key, {}),
                years,
                benchmark_name=benchmark_name,
                sync_bucket=sync_bucket,
            )
            bottleneck = data_status.get("bottleneck")
            if bottleneck:
                latest_text = (
                    f"병목 {bottleneck['label']} "
                    f"{_macro_date_text(bottleneck['latest_date'])}"
                    f"{' · 지연' if bottleneck.get('note') == '지연' else ''}"
                )
            else:
                latest_text = "확인 불가"
            entries.append({
                "label": label,
                "selected": True,
                "flag": is_on,
                "latest_date": latest_text,
            })
    else:
        selected = set(preset_cfg.get("selected_indicators", []))
        for indicator in _MACRO3_INDICATOR_ORDER:
            key = _macro3_indicator_key(indicator)
            is_on = bool(latest.get(f"{key}_flag", False))
            if is_on:
                active_labels.append(_MACRO3_INDICATOR_LABELS.get(indicator, indicator))
            latest_date = _get_macro3_signal_latest_date(indicator, years, benchmark_name=benchmark_name, sync_bucket=sync_bucket)
            freshness = _macro3_freshness_note(indicator, latest_date)
            latest_text = _macro_date_text(latest_date)
            if freshness == "지연":
                latest_text = f"{latest_text} · 지연"
            elif freshness == "확인 불가":
                latest_text = "확인 불가"
            entries.append({
                "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
                "selected": indicator in selected,
                "flag": is_on,
                "latest_date": latest_text,
            })
    active_flags_text = ", ".join(active_labels) if active_labels else "없음"
    summary_html = (
        '<div style="display:flex;gap:12px 16px;align-items:center;flex-wrap:wrap;padding:0 0 14px 0;color:#CFCFCF;font-size:12px;line-height:1.42;">'
        f"<span><b>기준일</b> {basis_date}</span>"
        f"<span><b>현재 플래그</b> {_macro_on_k_text(active_count, combo_k)} ({active_flags_text})</span>"
        f"<span><b>상태</b> <span style='color:{status_color};font-weight:700;'>{status_text}</span></span>"
        f"<span><b>실행 안내</b> {execution_text}</span>"
        "</div>"
    )
    midpoint = int(np.ceil(len(entries) / 2))
    left_entries = entries[:midpoint]
    right_entries = entries[midpoint:]
    row_count = max(len(left_entries), len(right_entries))

    def _entry_cells(entry):
        if not entry:
            return "<td style='padding:6px 8px;'></td>" * 4
        return (
            f"<td style='padding:5px 8px;color:#D6D6D6;line-height:1.32;'>{entry['label']}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{_macro_status_circle(entry['selected'], color_on='#7C7CF7')}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{_macro_status_circle(entry['flag'], color_on='#4BFFB3')}</td>"
            f"<td style='padding:5px 8px;color:#AFAFAF;line-height:1.32;'>{entry['latest_date']}</td>"
        )

    rows_html = []
    for idx in range(row_count):
        left = left_entries[idx] if idx < len(left_entries) else None
        right = right_entries[idx] if idx < len(right_entries) else None
        rows_html.append(f"<tr>{_entry_cells(left)}<td style='width:12px;'></td>{_entry_cells(right)}</tr>")
    table_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "<th style='width:12px;border-bottom:1px solid rgba(255,255,255,0.08);'></th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )
    return summary_html, table_html


@st.cache_data(ttl=3600, show_spinner=False)
def _get_macro6_signal_latest_date(indicator: str, years: int, benchmark_name: str = "S&P500", sync_bucket: str | None = None):
    if indicator == "Bollinger Band":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, years)
        return None if ohlc.empty else ohlc.index.max()
    if indicator == "VIX Spread":
        expected_latest, benchmark_index = _macro6_expected_latest_trading_date(
            benchmark_name=benchmark_name,
            years=years,
            sync_bucket=sync_bucket,
        )
        meta = _macro6_vix_spread_with_fallback(
            years=years,
            benchmark_name=benchmark_name,
            expected_latest_date=expected_latest,
            benchmark_dates=tuple(pd.Timestamp(d).isoformat() for d in benchmark_index),
            sync_bucket=sync_bucket,
        )
        return meta.get("final_latest_date")
    series = _macro6_get_indicator_raw_series(indicator, years, benchmark_name=benchmark_name, sync_bucket=sync_bucket)
    return None if series is None or series.empty else series.index.max()


def _macro6_indicator_data_status_row(
    indicator: str,
    years: int,
    benchmark_name: str = "S&P500",
    sync_bucket: str | None = None,
) -> dict:
    if indicator == "VIX Spread":
        expected_latest, benchmark_index = _macro6_expected_latest_trading_date(
            benchmark_name=benchmark_name,
            years=years,
            sync_bucket=sync_bucket,
        )
        meta = _macro6_vix_spread_with_fallback(
            years=years,
            benchmark_name=benchmark_name,
            expected_latest_date=expected_latest,
            benchmark_dates=tuple(pd.Timestamp(d).isoformat() for d in benchmark_index),
            sync_bucket=sync_bucket,
        )
        latest_date = meta.get("final_latest_date")
        detail = meta.get("detail", "")
        latest_text = _macro_date_text(latest_date) if latest_date is not None and not pd.isna(latest_date) else "확인 불가"
        if detail:
            latest_text = f"{latest_text} · {detail}"
        return {
            "indicator": indicator,
            "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
            "latest_date": latest_date,
            "note": meta.get("note", _macro3_freshness_note(indicator, latest_date)),
            "latest_text": latest_text,
            "expected_latest_date": meta.get("expected_latest_date"),
            "yahoo_common_latest_date": meta.get("yahoo_common_latest_date"),
            "fred_common_latest_date": meta.get("fred_common_latest_date"),
            "source_status": meta.get("source_status"),
            "lag_trading_days": meta.get("lag_trading_days"),
            "fred_supplement_days": meta.get("fred_supplement_days"),
            "fred_supplement_trading_days": meta.get("fred_supplement_trading_days"),
        }
    latest_date = _get_macro6_signal_latest_date(
        indicator,
        years,
        benchmark_name=benchmark_name,
        sync_bucket=sync_bucket,
    )
    note = _macro3_freshness_note(indicator, latest_date)
    latest_text = _macro_date_text(latest_date)
    expected_latest = None
    lag_trading_days = None
    if indicator == "Credit Stress" and latest_text != "확인 불가":
        latest_text = f"{latest_text} · 주간 업데이트"
    if indicator in {"Index", "VIX", "Bollinger Band"}:
        expected_latest, benchmark_index = _macro6_expected_latest_trading_date(
            benchmark_name=benchmark_name,
            years=years,
            sync_bucket=sync_bucket,
        )
        lag_trading_days = _macro6_lag_trading_days(expected_latest, latest_date, benchmark_index)
        if lag_trading_days is not None and lag_trading_days > 0:
            note = "지연"
            latest_text = f"{latest_text} · Yahoo 데이터 {lag_trading_days}거래일 지연"
    if note == "지연":
        if "지연" not in latest_text:
            latest_text = f"{latest_text} · 지연"
    elif note == "확인 불가":
        latest_text = "확인 불가"
    return {
        "indicator": indicator,
        "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
        "latest_date": latest_date,
        "note": note,
        "latest_text": latest_text,
        "expected_latest_date": expected_latest,
        "lag_trading_days": lag_trading_days,
    }


def _macro6_component_data_status(
    component_cfg: dict,
    years: int,
    benchmark_name: str = "S&P500",
    sync_bucket: str | None = None,
) -> dict:
    rows = []
    for indicator in component_cfg.get("selected_indicators", []):
        row = _macro6_indicator_data_status_row(
            indicator,
            years,
            benchmark_name=benchmark_name,
            sync_bucket=sync_bucket,
        )
        rows.append(row)
    valid_rows = [row for row in rows if row["latest_date"] is not None and not pd.isna(row["latest_date"])]
    bottleneck = min(valid_rows, key=lambda row: pd.Timestamp(row["latest_date"])) if valid_rows else None
    return {"rows": rows, "bottleneck": bottleneck}


def _macro6_preset_display_label(cfg: dict) -> str:
    candidate_key = str(cfg.get("candidate_key") or cfg.get("combo_id") or "")
    if candidate_key in _MACRO6_DISPLAY_LABEL_OVERRIDES:
        return _MACRO6_DISPLAY_LABEL_OVERRIDES[candidate_key]
    group = "조합2" if cfg.get("kind") == "combo2_final8" or cfg.get("components") else "조합1"
    unit = "조합1" if group == "조합2" else "지표"
    role = str(cfg.get("role_tags") or "").strip() or str(cfg.get("label") or "").strip() or "후보"
    if role.startswith("조합") or role.startswith("[조합"):
        role = str(cfg.get("role_tags") or "후보").strip()
    try:
        count = int(cfg.get("combo_m") or len(cfg.get("components") or cfg.get("selected_indicators") or []))
    except Exception:
        count = 0
    try:
        k_value = int(cfg.get("combo_k"))
        l_value = int(cfg.get("combo_l"))
    except Exception:
        k_value = 0
        l_value = 0
    return f"[{group}] {role} ({unit} {count}개/K{k_value}/L{l_value})"


_MACRO_BACKTEST_COLGROUP = (
    "<colgroup>"
    '<col style="width:22%">'
    '<col style="width:10.5%">'
    '<col style="width:10.5%">'
    '<col style="width:9%">'
    '<col style="width:10%">'
    '<col style="width:10%">'
    '<col style="width:9%">'
    '<col style="width:7%">'
    '<col style="width:7%">'
    '<col style="width:5%">'
    "</colgroup>"
)
_MACRO_BACKTEST_TABLE_STYLE = "width:100%;min-width:1180px;table-layout:fixed;border-collapse:collapse;font-size:12px;"
_MACRO_BACKTEST_TABLE_WRAP_OPEN = "<div class='macro-backtest-table-wrap' style='width:100%;overflow-x:auto;'>"
_MACRO_BACKTEST_CELL_LEFT = "padding:7px 8px;color:#EDEDED;font-weight:700;line-height:1.28;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
_MACRO_BACKTEST_CELL_NUM = "padding:7px 8px;color:#D6D6D6;text-align:right;white-space:nowrap;"
_MACRO_BACKTEST_CELL_CURRENT = "padding:7px 8px;color:#D6D6D6;text-align:center;white-space:nowrap;"


def _macro_backtest_header_html(labels: list[tuple[str, str]]) -> str:
    cells = []
    for label, align in labels:
        cells.append(
            f"<th style='text-align:{align};padding:6px 8px;color:#8F8F8F;"
            "border-bottom:1px solid rgba(255,255,255,0.08);white-space:nowrap;'>"
            f"{label}</th>"
        )
    return "<thead><tr>" + "".join(cells) + "</tr></thead>"


def _macro6_state_duration_values(combo_event_df: pd.DataFrame) -> dict:
    if combo_event_df is None or combo_event_df.empty or "combo_risk_state" not in combo_event_df.columns:
        return {"state_start_text": "확인 불가", "duration_text": "확인 불가", "current_state": None}
    ordered = combo_event_df.sort_values("date").reset_index(drop=True)
    latest = ordered.iloc[-1]
    current_state = bool(latest.get("combo_risk_state", False))
    start_idx = len(ordered) - 1
    while start_idx > 0 and bool(ordered.iloc[start_idx - 1].get("combo_risk_state", False)) == current_state:
        start_idx -= 1
    start_text = "계산범위 이전" if start_idx == 0 else _macro_date_text(ordered.iloc[start_idx].get("date"))
    return {
        "state_start_text": start_text,
        "duration_text": str(len(ordered) - start_idx),
        "current_state": current_state,
    }


def _macro_compact_status_html(
    basis_date: str,
    active_count: int,
    component_count: int,
    risk_state: int | bool,
    execution_position: int | bool | None,
    start_event: bool,
    end_event: bool,
    state_start: str,
    duration_text: str,
    start_k: int | None = None,
) -> str:
    risk_on = bool(int(risk_state)) if not isinstance(risk_state, bool) else risk_state
    risk_color = "#FF8C69" if risk_on else "#4BFFB3"
    risk_text = "리스크 사이클 ON" if risk_on else "리스크 사이클 OFF"
    try:
        execution_text = "투자" if int(execution_position) == 1 else "비투자"
    except Exception:
        execution_text = "확인 불가"
    if start_event:
        transition_text = "오늘 Risk-off 시작"
        transition_color = "#FF8C69"
    elif end_event:
        transition_text = "오늘 Risk-off 종료"
        transition_color = "#60A5FA"
    else:
        transition_text = "오늘 전환 없음"
        transition_color = "rgba(255,255,255,0.72)"
    separator = "<span style='color:rgba(255,255,255,0.42);padding:0 8px;'>·</span>"
    return (
        "<div class='macro-compact-status'>"
        "<div class='macro-compact-status-line-primary' "
        "style='display:flex;align-items:center;flex-wrap:wrap;color:#CFCFCF;font-size:12px;line-height:1.42;padding:0 0 2px 0;'>"
        f"<span><b>기준일</b> {basis_date}</span>{separator}"
        f"<span><b>현재 플래그</b> {_macro_on_k_text(int(active_count), int(start_k or component_count or 1))}</span>{separator}"
        f"<span><b>상태</b> <span style='color:{risk_color};font-weight:700;'>{risk_text}</span></span>"
        "</div>"
        "<div class='macro-compact-status-line-secondary' "
        "style='display:flex;align-items:center;flex-wrap:wrap;color:#AFAFAF;font-size:12px;line-height:1.42;padding:0 0 14px 0;'>"
        f"<span><b>현재 상태 시작일</b> <span style='color:{risk_color};font-weight:700;'>{state_start}</span></span>{separator}"
        f"<span><b>지속 거래일</b> <span style='color:{risk_color};font-weight:700;'>{duration_text}</span></span>{separator}"
        f"<span><b>실행</b> {execution_text}</span>{separator}"
        f"<span style='color:{transition_color};font-weight:700;'>{transition_text}</span>"
        "</div></div>"
    )


def _build_macro6_status_panel(
    benchmark_name: str,
    years: int,
    preset_cfg: dict,
    combo_event_df: pd.DataFrame,
    sync_bucket: str | None = None,
):
    if combo_event_df is None or combo_event_df.empty:
        return "", ""
    latest = combo_event_df.sort_values("date").iloc[-1]
    combo_state = bool(latest.get("combo_risk_state", False))
    active_count = int(latest.get("active_count", 0))
    combo_n = int(latest.get("combo_n", len(preset_cfg.get("selected_indicators", []))))
    combo_k = int(latest.get("combo_k", preset_cfg.get("combo_k", max(1, combo_n))))
    basis_date = _macro_date_text(latest.get("date"))
    status_text = "리스크 사이클 ON" if combo_state else "리스크 사이클 OFF"
    status_color = "#FF8C69" if combo_state else "#4BFFB3"
    active_labels = []
    entries = []
    if preset_cfg.get("kind") == "combo2_final8":
        component_cfgs = preset_cfg.get("component_cfgs", {})
        for component_key in preset_cfg.get("components", []):
            key = _macro3_indicator_key(component_key)
            is_on = bool(latest.get(f"{key}_flag", False))
            label = _macro3_component_label(component_key, component_cfgs.get(component_key))
            if is_on:
                active_labels.append(label)
            data_status = _macro6_component_data_status(
                component_cfgs.get(component_key, {}),
                years,
                benchmark_name=benchmark_name,
                sync_bucket=sync_bucket,
            )
            bottleneck = data_status.get("bottleneck")
            if bottleneck:
                latest_text = (
                    f"가장 오래된 사용값 {bottleneck['label']} "
                    f"{bottleneck.get('latest_text') or _macro_date_text(bottleneck['latest_date'])}"
                )
            else:
                latest_text = "확인 불가"
            entries.append({
                "label": label,
                "selected": True,
                "flag": is_on,
                "latest_date": latest_text,
            })
    else:
        selected = set(preset_cfg.get("selected_indicators", []))
        for indicator in _MACRO3_INDICATOR_ORDER:
            key = _macro3_indicator_key(indicator)
            is_on = bool(latest.get(f"{key}_flag", False))
            if is_on:
                active_labels.append(_MACRO3_INDICATOR_LABELS.get(indicator, indicator))
            data_status = _macro6_indicator_data_status_row(
                indicator,
                years,
                benchmark_name=benchmark_name,
                sync_bucket=sync_bucket,
            )
            latest_text = data_status.get("latest_text", "확인 불가")
            entries.append({
                "label": _MACRO3_INDICATOR_LABELS.get(indicator, indicator),
                "selected": indicator in selected,
                "flag": is_on,
                "latest_date": latest_text,
            })
    state_duration = _macro6_state_duration_values(combo_event_df)
    summary_html = _macro_compact_status_html(
        basis_date=basis_date,
        active_count=active_count,
        component_count=combo_n,
        start_k=combo_k,
        risk_state=combo_state,
        execution_position=0 if combo_state else 1,
        start_event=bool(latest.get("combo_start_signal", False)),
        end_event=bool(latest.get("combo_end_signal", False)),
        state_start=state_duration.get("state_start_text", "확인 불가"),
        duration_text=state_duration.get("duration_text", "확인 불가"),
    )
    midpoint = int(np.ceil(len(entries) / 2))
    left_entries = entries[:midpoint]
    right_entries = entries[midpoint:]
    row_count = max(len(left_entries), len(right_entries))

    def _entry_cells(entry):
        if not entry:
            return "<td style='padding:6px 8px;'></td>" * 4
        return (
            f"<td style='padding:5px 8px;color:#D6D6D6;line-height:1.32;'>{entry['label']}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{_macro_status_circle(entry['selected'], color_on='#7C7CF7')}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{_macro_status_circle(entry['flag'], color_on='#FF8C69')}</td>"
            f"<td style='padding:5px 8px;color:#AFAFAF;line-height:1.32;'>{entry['latest_date']}</td>"
        )

    rows_html = []
    for idx in range(row_count):
        left = left_entries[idx] if idx < len(left_entries) else None
        right = right_entries[idx] if idx < len(right_entries) else None
        rows_html.append(f"<tr>{_entry_cells(left)}<td style='width:12px;'></td>{_entry_cells(right)}</tr>")
    table_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        "<th style='width:12px;border-bottom:1px solid rgba(255,255,255,0.08);'></th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신날짜</th>"
        f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )
    return summary_html, table_html


@st.cache_data(show_spinner=False)
def _compute_macro3_preset_current_state_cached(preset_cfg: dict, years: int, sync_bucket: str | None = None):
    benchmark_name = preset_cfg.get("benchmark", "S&P500")
    benchmark = _get_macro_benchmark(benchmark_name)
    spx_s = _yf_close(benchmark["code"], years, sync_bucket=sync_bucket)
    if spx_s is None or spx_s.empty:
        return None
    combo, active_indicators = _compute_macro3_preset_signal_frame(
        spx_s=spx_s,
        benchmark_name=benchmark_name,
        preset_cfg=preset_cfg,
        sync_bucket=sync_bucket,
    )
    if combo.empty:
        return None
    latest = combo.sort_index().iloc[-1]
    return {
        "is_on": bool(latest.get("combo_risk_state", False)),
        "on_count": int(latest.get("active_count", 0)),
        "total_count": len(active_indicators),
        "start_count": int(preset_cfg.get("combo_k", len(active_indicators))),
    }


def _compute_macro3_preset_current_state(preset_cfg: dict, years: int, sync_bucket: str | None = None):
    return _compute_macro3_preset_current_state_cached(preset_cfg=preset_cfg, years=years, sync_bucket=sync_bucket)


def _macro3_group_availability_html(label: str, preset_keys, preset_defs: dict, blocking_map: dict) -> str:
    keys = list(preset_keys)
    total = len(keys)
    blocked = sum(1 for key in keys if key not in preset_defs or blocking_map.get(key))
    available = max(0, total - blocked)
    available_color = "#54F2A3" if blocked == 0 else "rgba(255,255,255,0.92)"
    blocked_color = "#FF8C69" if blocked > 0 else "rgba(255,255,255,0.72)"
    return (
        f"<span style='color:{available_color};font-weight:700;'>{label} 계산 가능 {available} / {total}</span>"
        f"<span style='color:rgba(255,255,255,0.55);'> · </span>"
        f"<span style='color:{blocked_color};font-weight:700;'>계산 불가 {blocked}</span>"
    )


def _build_macro3_backtest_panel(
    preset_key: str,
    preset_defs: dict,
    years: int = 3,
    sync_bucket: str | None = None,
    preset_order: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, str]:
    selected = preset_defs.get(preset_key)
    if not selected:
        return "", ""
    final8_keys = list(preset_defs.keys()) if preset_order is None else [key for key in preset_order if key in preset_defs]
    compare_rows = [
        ("sp500_buyhold", _MACRO_META_BACKTEST_COMPARE["sp500_buyhold"]["label"], _MACRO_META_BACKTEST_COMPARE["sp500_buyhold"]["metrics"], "legacy"),
        ("snp_meta_2", _MACRO_META_BACKTEST_COMPARE["snp_meta_2"]["label"], _MACRO_META_BACKTEST_COMPARE["snp_meta_2"]["metrics"], "legacy"),
    ] + [(key, preset_defs[key]["label"], preset_defs[key]["metrics"], "final8") for key in final8_keys]
    hold_metrics = _MACRO_META_BACKTEST_COMPARE["sp500_buyhold"]["metrics"]
    hold_10y = _macro_metric_float(hold_metrics.get("10Y 자산"))
    hold_20y = _macro_metric_float(hold_metrics.get("20Y 자산"))
    hold_mdd_10y = _macro_metric_float(hold_metrics.get("10Y MDD"))
    hold_mdd_20y = _macro_metric_float(hold_metrics.get("20Y MDD"))

    def _ratio_span(ratio: float, good: bool) -> str:
        color = "#7FE7B1" if good else "#8F8F8F"
        weight = "700" if good else "400"
        return f"<span style='color:{color};font-size:11px;font-weight:{weight};'>({ratio:.2f}x)</span>"

    current_state_map = {}
    for key, _label, _metrics, row_type in compare_rows:
        if row_type == "final8":
            current_state_map[key] = _compute_macro3_preset_current_state(preset_defs[key], years=years, sync_bucket=sync_bucket)
        else:
            current_state_map[key] = None
    rows_html = []
    for key, label, summary, _row_type in compare_rows:
        is_selected = key == preset_key
        bg = "rgba(120,126,231,0.16)" if is_selected else "transparent"
        border = "1px solid rgba(120,126,231,0.34)" if is_selected else "1px solid transparent"
        asset_10y, asset_20y, mdd_10y, mdd_20y = summary["10Y 자산"], summary["20Y 자산"], summary["10Y MDD"], summary["20Y MDD"]
        asset_10y_num = _macro_metric_float(asset_10y)
        asset_20y_num = _macro_metric_float(asset_20y)
        mdd_10y_num = _macro_metric_float(mdd_10y)
        mdd_20y_num = _macro_metric_float(mdd_20y)
        if hold_10y and asset_10y_num is not None and key != "sp500_buyhold":
            asset_10y = f"{asset_10y} {_ratio_span(asset_10y_num / hold_10y, asset_10y_num / hold_10y >= 1.5)}"
        if hold_20y and asset_20y_num is not None and key != "sp500_buyhold":
            asset_20y = f"{asset_20y} {_ratio_span(asset_20y_num / hold_20y, asset_20y_num / hold_20y >= 1.5)}"
        if hold_mdd_10y and mdd_10y_num is not None and key != "sp500_buyhold":
            ratio = abs(mdd_10y_num) / abs(hold_mdd_10y)
            mdd_10y = f"{mdd_10y} {_ratio_span(ratio, ratio <= 0.5)}"
        if hold_mdd_20y and mdd_20y_num is not None and key != "sp500_buyhold":
            ratio = abs(mdd_20y_num) / abs(hold_mdd_20y)
            mdd_20y = f"{mdd_20y} {_ratio_span(ratio, ratio <= 0.5)}"
        current_state = current_state_map.get(key)
        current_state_html = "-" if current_state is None else _macro_flag_ratio_html(
            current_state.get("on_count", 0),
            current_state.get("start_count", current_state.get("total_count", 1)),
            current_state.get("is_on"),
        )
        rows_html.append(
            f"<tr style='background:{bg};border-top:{border};border-bottom:{border};'>"
            f"<td style='padding:7px 8px;color:#EDEDED;font-weight:700;'>{label}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{asset_10y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{asset_20y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{mdd_10y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{mdd_20y}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['20Y Risk-off']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['20Y Cycle']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:right;'>{summary['짧은 Cycle']}</td>"
            f"<td style='padding:7px 8px;color:#D6D6D6;text-align:center;'>{current_state_html}</td></tr>"
        )
    compare_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>후보</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>10Y 자산</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y 자산</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>10Y MDD</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y MDD</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y Risk-off</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>20Y Cycle</th>"
        "<th style='text-align:right;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>짧은 Cycle</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,0.08);'>현재</th>"
        f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )
    return "", compare_html


def _macro6_state_duration_html(combo_event_df: pd.DataFrame) -> str:
    state = _macro6_state_duration_values(combo_event_df)
    if state.get("current_state") is None:
        return ""
    color = "#FF8C69" if bool(state.get("current_state")) else "#4BFFB3"
    return (
        '<div style="display:flex;align-items:center;flex-wrap:wrap;'
        f'padding:0 0 14px 0;color:{color};font-size:12px;line-height:1.42;font-weight:700;">'
        f"<span><b>현재 상태 시작일</b> {state.get('state_start_text')} · <b>지속 거래일</b> {state.get('duration_text')}</span>"
        "</div>"
    )


def _macro6_group_consensus_html(
    label: str,
    preset_keys,
    preset_defs: dict,
    blocking_map: dict,
    years: int,
    sync_bucket: str | None = None,
    snapshot_map: dict | None = None,
) -> str:
    keys = [key for key in list(preset_keys) if key in preset_defs]
    total = len(list(preset_keys))
    blocked_keys = [key for key in list(preset_keys) if key not in preset_defs or blocking_map.get(key)]
    if blocked_keys:
        available = max(0, total - len(blocked_keys))
        return (
            f"<span style='font-weight:700;color:#FFB86B;'>{label} 합의도 확인 필요</span>"
            f"<span style='color:rgba(255,255,255,0.55);'> · 계산 가능 {available}/{total}</span>"
        )
    series_map = {}
    basis_index = None
    benchmark = _get_macro_benchmark("S&P500")
    for key in keys:
        cfg = preset_defs.get(key, {})
        snapshot = (snapshot_map or {}).get(key)
        combo = snapshot.get("combo_frame", pd.DataFrame()) if snapshot else pd.DataFrame()
        if combo.empty:
            return (
                f"<span style='font-weight:700;color:#FFB86B;'>{label} 합의도 확인 필요</span>"
                f"<span style='color:rgba(255,255,255,0.55);'> · {cfg.get('label', key)} 계산 불가</span>"
            )
        state = combo["combo_risk_state"].astype(bool).dropna()
        series_map[key] = state
        basis_index = state.index if basis_index is None else basis_index.intersection(state.index)
    if basis_index is None or len(basis_index) == 0:
        return (
            f"<span style='font-weight:700;color:#FFB86B;'>{label} 합의도 확인 필요</span>"
            f"<span style='color:rgba(255,255,255,0.55);'> · 공통 기준일 없음</span>"
        )
    basis_date = pd.Timestamp(basis_index.max()).normalize()
    risk_off = sum(1 for state in series_map.values() if bool(state.reindex([basis_date]).iloc[0]))
    color = "#FF8C69" if risk_off > 0 else "#4BFFB3"
    return (
        f"<span style='font-weight:700;color:{color};'>{label} Risk-off {risk_off}/{total}</span>"
        f"<span style='color:rgba(255,255,255,0.55);'> · 기준일 {_macro_date_text(basis_date)}</span>"
    )


def _build_macro6_backtest_panel(
    preset_key: str,
    preset_defs: dict,
    preset_order: tuple[str, ...] | list[str],
    years: int = 5,
    sync_bucket: str | None = None,
    snapshot_map: dict | None = None,
) -> str:
    rows_html = []
    hold_metrics = _MACRO_META_BACKTEST_COMPARE["sp500_buyhold"]["metrics"]
    hold_10y = _macro_metric_float(hold_metrics.get("10Y 자산"))
    hold_20y = _macro_metric_float(hold_metrics.get("20Y 자산"))
    hold_mdd_10y = _macro_metric_float(hold_metrics.get("10Y MDD"))
    hold_mdd_20y = _macro_metric_float(hold_metrics.get("20Y MDD"))

    def _ratio_span(ratio: float, good: bool) -> str:
        color = "#7FE7B1" if good else "#8F8F8F"
        weight = "700" if good else "400"
        return f"<span style='color:{color};font-size:11px;font-weight:{weight};'>({ratio:.2f}x)</span>"

    def _format_with_ratios(key: str, metrics: dict) -> dict:
        formatted = dict(metrics)
        asset_10y_num = _macro_metric_float(formatted.get("10Y 자산"))
        asset_20y_num = _macro_metric_float(formatted.get("20Y 자산"))
        mdd_10y_num = _macro_metric_float(formatted.get("10Y MDD"))
        mdd_20y_num = _macro_metric_float(formatted.get("20Y MDD"))
        cagr_20y_num = _macro_metric_float(formatted.get("20Y CAGR"))
        if key != "sp500_buyhold" and hold_10y and asset_10y_num is not None:
            formatted["10Y 자산"] = f"{formatted.get('10Y 자산', '-')} {_ratio_span(asset_10y_num / hold_10y, asset_10y_num / hold_10y >= 1.5)}"
        if key != "sp500_buyhold" and hold_20y and asset_20y_num is not None:
            formatted["20Y 자산"] = f"{formatted.get('20Y 자산', '-')} {_ratio_span(asset_20y_num / hold_20y, asset_20y_num / hold_20y >= 1.5)}"
        if key != "sp500_buyhold" and hold_mdd_10y and mdd_10y_num is not None:
            ratio = abs(mdd_10y_num) / abs(hold_mdd_10y)
            formatted["10Y MDD"] = f"{formatted.get('10Y MDD', '-')} {_ratio_span(ratio, ratio <= 0.5)}"
        if key != "sp500_buyhold" and hold_mdd_20y and mdd_20y_num is not None:
            ratio = abs(mdd_20y_num) / abs(hold_mdd_20y)
            formatted["20Y MDD"] = f"{formatted.get('20Y MDD', '-')} {_ratio_span(ratio, ratio <= 0.5)}"
        if key != "sp500_buyhold" and hold_cagr_20y_num and cagr_20y_num is not None:
            ratio = cagr_20y_num / hold_cagr_20y_num
            formatted["20Y CAGR"] = f"{formatted.get('20Y CAGR', '-')} {_ratio_span(ratio, ratio >= 1.5)}"
        return formatted

    try:
        hold_asset_20y = _macro_metric_float(hold_metrics.get("20Y 자산"))
        hold_cagr_20y = _macro3_metric_percent((hold_asset_20y / 100.0) ** (1.0 / 20.0) - 1.0) if hold_asset_20y else "-"
        hold_cagr_20y_num = _macro_metric_float(hold_cagr_20y)
    except Exception:
        hold_cagr_20y = "-"
        hold_cagr_20y_num = None
    compare_items = [(
        "sp500_buyhold",
        {"label": _MACRO_META_BACKTEST_COMPARE["sp500_buyhold"]["label"], "metrics": {**hold_metrics, "20Y CAGR": hold_cagr_20y}},
    )] + [(key, preset_defs[key]) for key in preset_order if key in preset_defs]

    for key, cfg in compare_items:
        metrics = cfg.get("metrics", {})
        is_selected = key == preset_key
        bg = "rgba(120,126,231,0.16)" if is_selected else "transparent"
        border = "1px solid rgba(120,126,231,0.34)" if is_selected else "1px solid transparent"
        current_state = None
        if key != "sp500_buyhold" and not _macro3_preset_blocking_reasons(cfg):
            current_state = (snapshot_map or {}).get(key)
        current_state_html = "-" if current_state is None else _macro_flag_ratio_html(
            current_state.get("on_count", 0),
            current_state.get("start_count", current_state.get("total_count", 1)),
            current_state.get("is_on"),
        )
        label = _macro6_preset_display_label(cfg) if key != "sp500_buyhold" else cfg.get("label", key)
        display_metrics = _format_with_ratios(key, metrics)
        rows_html.append(
            f"<tr style='background:{bg};border-top:{border};border-bottom:{border};'>"
            f"<td title='{label}' style='{_MACRO_BACKTEST_CELL_LEFT}'>{label}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('10Y 자산', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('20Y 자산', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('20Y CAGR', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('10Y MDD', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('20Y MDD', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('20Y Risk-off', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('20Y Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{display_metrics.get('짧은 Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_CURRENT}'>{current_state_html}</td></tr>"
        )
    if not rows_html:
        return ""
    return (
        _MACRO_BACKTEST_TABLE_WRAP_OPEN
        + f"<table style='{_MACRO_BACKTEST_TABLE_STYLE}'>"
        + _MACRO_BACKTEST_COLGROUP
        + _macro_backtest_header_html([
            ("역할 / 후보", "left"),
            ("10Y 자산", "right"),
            ("20Y 자산", "right"),
            ("20Y CAGR", "right"),
            ("10Y MDD", "right"),
            ("20Y MDD", "right"),
            ("20Y Risk-off", "right"),
            ("20Y Cycle", "right"),
            ("짧은 Cycle", "right"),
            ("현재", "center"),
        ])
        + f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _build_macro3_indicator_chart(
    indicator: str,
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    spx_s: pd.Series,
    show_raw: bool,
    sync_bucket: str | None = None,
):
    cfg = preset_cfg.get("cfgs", {}).get(indicator)
    if not cfg or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return None
    benchmark_index = spx_s.index if spx_s is not None else pd.DatetimeIndex([])
    signal_df = _macro3_get_indicator_signal_frame(
        indicator=indicator,
        cfg=cfg,
        benchmark_index=benchmark_index,
        years=max(years + 2, 5),
        benchmark_name=benchmark_name,
        spx_s=spx_s,
        sync_bucket=sync_bucket,
    )
    if signal_df.empty:
        return None
    benchmark = _get_macro_benchmark(benchmark_name)
    title = _MACRO3_INDICATOR_LABELS.get(indicator, indicator)
    chart_index, x_start, x_end = _macro_detail_chart_window(spx_s)
    if len(chart_index) == 0:
        return None
    fig = go.Figure()
    if indicator == "Bollinger Band":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, max(years + 2, 5))
        if ohlc.empty:
            return None
        signal_df = signal_df.reindex(chart_index)
        price = ohlc["Close"].reindex(chart_index).dropna()
        _add_macro_indicator_risk_background(fig, signal_df, x_start, x_end)
        fig.add_trace(go.Scatter(x=price.index, y=price, name=benchmark["label"], line=dict(color="rgba(182,182,182,0.88)", width=1.55)))
        for col, name, color, dash in [
            ("bb_middle", "BB Middle", "rgba(216,195,106,0.74)", "solid"),
            ("bb_upper", "BB Upper", "rgba(255,140,105,0.68)", "dot"),
            ("bb_lower", "BB Lower", "rgba(120,220,255,0.72)", "dot"),
        ]:
            if col in signal_df.columns:
                fig.add_trace(go.Scatter(
                    x=signal_df.index,
                    y=signal_df[col],
                    name=name,
                    line=dict(color=color, width=1.15, dash=dash),
                ))
        start_y = price.reindex(signal_df.index[signal_df["risk_start_signal"].fillna(False)])
        end_y = price.reindex(signal_df.index[signal_df["risk_end_signal"].fillna(False)])
        if not start_y.empty:
            fig.add_trace(go.Scatter(x=start_y.index, y=start_y, mode="markers", name="리스크 시작", marker=dict(symbol="triangle-down", size=9, color="rgba(210,55,55,0.95)")))
        if not end_y.empty:
            fig.add_trace(go.Scatter(x=end_y.index, y=end_y, mode="markers", name="리스크 종료", marker=dict(symbol="triangle-up", size=9, color="rgba(80,160,255,0.92)")))
        fig.update_layout(**_ml(title, height=300))
        fig.update_xaxes(range=[x_start, x_end], autorange=False)
        return fig

    raw_series = _macro3_get_indicator_raw_series(indicator, max(years + 2, 5), benchmark_name=benchmark_name, spx_s=spx_s, sync_bucket=sync_bucket)
    if raw_series is None or raw_series.empty:
        return None
    display_s = signal_df["value"].dropna() if "value" in signal_df.columns else raw_series.reindex(signal_df.index).dropna()
    signal_df = signal_df.reindex(display_s.index)
    ema_candidates = [col for col in signal_df.columns if col.startswith("ema")]
    ema_col = ema_candidates[0] if ema_candidates else None
    main_s = signal_df[ema_col].dropna() if ema_col else display_s
    main_s = main_s.loc[(main_s.index >= x_start) & (main_s.index <= x_end)]
    signal_visible = signal_df.reindex(chart_index)
    signal_df = signal_visible.reindex(main_s.index)
    _add_macro_indicator_risk_background(fig, signal_visible, x_start, x_end)
    if show_raw and ema_col:
        raw_display = display_s.reindex(main_s.index).dropna()
        if not raw_display.empty:
            fig.add_trace(go.Scatter(
                x=raw_display.index,
                y=raw_display,
                name=f"{indicator} 원본",
                line=dict(color="rgba(182,182,182,0.22)", width=0.85),
                hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{indicator} 원본  %{{y:.2f}}<extra></extra>",
            ))
    fig.add_trace(go.Scatter(
        x=main_s.index,
        y=main_s,
        name=ema_col.upper() if ema_col else indicator,
        line=dict(color="rgba(216,195,106,0.32)", width=1.1),
    ))
    if "risk_start_line" in signal_df.columns:
        fig.add_trace(go.Scatter(
            x=signal_df.index,
            y=signal_df["risk_start_line"],
            name="시작선",
            line=dict(color="rgba(255,140,105,0.55)", width=1.2, dash="dot"),
        ))
    if "risk_end_line" in signal_df.columns:
        fig.add_trace(go.Scatter(
            x=signal_df.index,
            y=signal_df["risk_end_line"],
            name="종료선",
            line=dict(color="rgba(120,220,255,0.60)", width=1.2, dash="dot"),
        ))
    if indicator != "Index":
        spx_visible = spx_s.reindex(chart_index).dropna() if spx_s is not None else pd.Series(dtype=float)
        if not spx_visible.empty:
            fig.add_trace(go.Scatter(
                x=spx_visible.index,
                y=spx_visible,
                name=benchmark["label"],
                line=dict(color="rgba(182,182,182,0.88)", width=1.55),
                showlegend=True,
                hoverinfo="skip",
                yaxis="y2",
            ))
        fig.update_layout(yaxis2=_visible_price_yaxis("y", "right"))
        marker_price = spx_visible
        marker_axis = "y2"
    else:
        marker_price = main_s
        marker_axis = "y"
    _add_price_signal_markers(
        fig,
        signal_visible.rename(columns={"risk_start_signal": "down_start_signal", "risk_end_signal": "down_end_signal"}),
        marker_price,
        yaxis=marker_axis,
        prefix=indicator,
    )
    fig.update_layout(**_ml(title, height=300))
    fig.update_xaxes(range=[x_start, x_end], autorange=False)
    return fig


def _macro_detail_chart_window(spx_s: pd.Series | None) -> tuple[pd.DatetimeIndex, pd.Timestamp | None, pd.Timestamp | None]:
    if spx_s is None or spx_s.empty:
        return pd.DatetimeIndex([]), None, None
    visible = spx_s.dropna().copy()
    if visible.empty:
        return pd.DatetimeIndex([]), None, None
    idx = pd.DatetimeIndex(pd.to_datetime(visible.index)).sort_values().drop_duplicates()
    return idx, pd.Timestamp(idx.min()), pd.Timestamp(idx.max())


def _add_macro_indicator_risk_background(fig: go.Figure, signal_df: pd.DataFrame, x_start, x_end) -> None:
    if signal_df is None or signal_df.empty or x_start is None or x_end is None:
        return
    state_col = "risk_state" if "risk_state" in signal_df.columns else "combo_risk_state" if "combo_risk_state" in signal_df.columns else None
    if state_col is None:
        return
    state = signal_df.copy()
    if "date" in state.columns:
        state["date"] = pd.to_datetime(state["date"])
        state = state.set_index("date")
    state.index = pd.to_datetime(state.index)
    state = state.loc[(state.index >= pd.Timestamp(x_start)) & (state.index <= pd.Timestamp(x_end)), state_col].dropna()
    if state.empty:
        return
    state = state.astype(bool).sort_index()
    start = None
    prev = False
    for dt, is_on in state.items():
        if bool(is_on) and not prev:
            start = dt
        if prev and not bool(is_on) and start is not None:
            fig.add_vrect(x0=start, x1=dt, fillcolor="rgba(255,75,110,0.11)", line_width=0, layer="below")
            start = None
        prev = bool(is_on)
    if prev and start is not None:
        fig.add_vrect(x0=start, x1=pd.Timestamp(x_end), fillcolor="rgba(255,75,110,0.11)", line_width=0, layer="below")


def _build_macro3_component_chart(
    component_key: str,
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    spx_s: pd.Series,
    sync_bucket: str | None = None,
):
    component_cfg = preset_cfg.get("component_cfgs", {}).get(component_key)
    if not component_cfg or spx_s is None or spx_s.empty:
        return None
    _chart_index, x_start, x_end = _macro_detail_chart_window(spx_s)
    warmup_years = max(years + 2, 5)
    benchmark = _get_macro_benchmark(benchmark_name)
    combo_spx = _yf_close(benchmark["code"], warmup_years, sync_bucket=sync_bucket)
    if combo_spx is None or combo_spx.empty:
        combo_spx = spx_s
    combo, active_indicators = _compute_macro3_combo_signal_frame(
        spx_s=combo_spx,
        benchmark_name=benchmark_name,
        selected_indicators=component_cfg.get("selected_indicators", []),
        cfgs=component_cfg.get("cfgs", {}),
        combo_k=int(component_cfg.get("combo_k", 1)),
        combo_l=int(component_cfg.get("combo_l", 0)),
        sync_bucket=sync_bucket,
    )
    if combo.empty:
        return None
    combo = combo.loc[combo.index >= spx_s.dropna().index.min()].copy()
    price = spx_s.reindex(combo.index).dropna()
    combo = combo.reindex(price.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index,
        y=price,
        name=benchmark["label"],
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
    ))
    component_event_df = combo.reset_index()
    component_event_df = component_event_df.rename(columns={component_event_df.columns[0]: "date"})
    _add_macro_combo_risk_cycle_background(fig, component_event_df, price.index)
    start_y = price.reindex(combo.index[combo["combo_start_signal"].fillna(False)])
    end_y = price.reindex(combo.index[combo["combo_end_signal"].fillna(False)])
    if not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, mode="markers", name="component 시작",
            marker=dict(symbol="triangle-down", size=9, color="rgba(210,55,55,0.95)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>component 시작: %{y:,.2f}<extra></extra>",
        ))
    if not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, mode="markers", name="component 종료",
            marker=dict(symbol="triangle-up", size=9, color="rgba(80,160,255,0.92)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>component 종료: %{y:,.2f}<extra></extra>",
        ))
    selected_labels = " + ".join([_MACRO3_INDICATOR_LABELS.get(name, name) for name in active_indicators])
    fig.update_layout(**_ml(_macro3_component_label(component_key, component_cfg), height=260))
    if x_start is not None and x_end is not None:
        fig.update_xaxes(range=[x_start, x_end], autorange=False)
    fig.add_annotation(
        xref="paper", yref="paper", x=0.01, y=0.97, showarrow=False,
        text=f"{int(component_cfg.get('combo_k', 1))}/{len(active_indicators)} · 종료≤{int(component_cfg.get('combo_l', 0))}<br>{selected_labels}",
        font=dict(size=10, color="#C8C8C8", family="Arial, sans-serif"),
        align="left",
        bgcolor="rgba(0,0,0,0.18)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
        borderpad=4,
    )
    return fig


def _build_macro6_indicator_chart(
    indicator: str,
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    spx_s: pd.Series,
    show_raw: bool,
    sync_bucket: str | None = None,
):
    cfg = preset_cfg.get("cfgs", {}).get(indicator)
    if not cfg or not COMBO1_EXPANDED_SIGNALS_AVAILABLE:
        return None
    benchmark_index = spx_s.index if spx_s is not None else pd.DatetimeIndex([])
    signal_df = _macro6_get_indicator_signal_frame(
        indicator=indicator,
        cfg=cfg,
        benchmark_index=benchmark_index,
        years=max(years + 2, 5),
        benchmark_name=benchmark_name,
        spx_s=spx_s,
        sync_bucket=sync_bucket,
    )
    if signal_df.empty:
        return None
    benchmark = _get_macro_benchmark(benchmark_name)
    title = _MACRO3_INDICATOR_LABELS.get(indicator, indicator)
    chart_index, x_start, x_end = _macro_detail_chart_window(spx_s)
    if len(chart_index) == 0:
        return None
    fig = go.Figure()
    if indicator == "Bollinger Band":
        ohlc = _macro3_fetch_benchmark_ohlcv(benchmark_name, max(years + 2, 5))
        if ohlc.empty:
            return None
        signal_df = signal_df.reindex(chart_index)
        price = ohlc["Close"].reindex(chart_index).dropna()
        _add_macro_indicator_risk_background(fig, signal_df, x_start, x_end)
        fig.add_trace(go.Scatter(x=price.index, y=price, name=benchmark["label"], line=dict(color="rgba(182,182,182,0.88)", width=1.55)))
        for col, name, color, dash in [
            ("bb_middle", "BB Middle", "rgba(216,195,106,0.74)", "solid"),
            ("bb_upper", "BB Upper", "rgba(255,140,105,0.68)", "dot"),
            ("bb_lower", "BB Lower", "rgba(120,220,255,0.72)", "dot"),
        ]:
            if col in signal_df.columns:
                fig.add_trace(go.Scatter(
                    x=signal_df.index,
                    y=signal_df[col],
                    name=name,
                    line=dict(color=color, width=1.15, dash=dash),
                ))
        start_y = price.reindex(signal_df.index[signal_df["risk_start_signal"].fillna(False)])
        end_y = price.reindex(signal_df.index[signal_df["risk_end_signal"].fillna(False)])
        if not start_y.empty:
            fig.add_trace(go.Scatter(x=start_y.index, y=start_y, mode="markers", name="리스크 시작", marker=dict(symbol="triangle-down", size=9, color="rgba(210,55,55,0.95)")))
        if not end_y.empty:
            fig.add_trace(go.Scatter(x=end_y.index, y=end_y, mode="markers", name="리스크 종료", marker=dict(symbol="triangle-up", size=9, color="rgba(80,160,255,0.92)")))
        fig.update_layout(**_ml(title, height=300))
        fig.update_xaxes(range=[x_start, x_end], autorange=False)
        return fig

    raw_series = _macro6_get_indicator_raw_series(indicator, max(years + 2, 5), benchmark_name=benchmark_name, spx_s=spx_s, sync_bucket=sync_bucket)
    if raw_series is None or raw_series.empty:
        return None
    display_s = signal_df["value"].dropna() if "value" in signal_df.columns else raw_series.reindex(signal_df.index).dropna()
    signal_df = signal_df.reindex(display_s.index)
    ema_candidates = [col for col in signal_df.columns if col.startswith("ema")]
    ema_col = ema_candidates[0] if ema_candidates else None
    main_s = signal_df[ema_col].dropna() if ema_col else display_s
    main_s = main_s.loc[(main_s.index >= x_start) & (main_s.index <= x_end)]
    signal_visible = signal_df.reindex(chart_index)
    signal_df = signal_visible.reindex(main_s.index)
    _add_macro_indicator_risk_background(fig, signal_visible, x_start, x_end)
    if show_raw and ema_col:
        raw_display = display_s.reindex(main_s.index).dropna()
        if not raw_display.empty:
            fig.add_trace(go.Scatter(
                x=raw_display.index,
                y=raw_display,
                name=f"{indicator} 원본",
                line=dict(color="rgba(182,182,182,0.22)", width=0.85),
                hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{indicator} 원본  %{{y:.2f}}<extra></extra>",
            ))
    fig.add_trace(go.Scatter(
        x=main_s.index,
        y=main_s,
        name=ema_col.upper() if ema_col else indicator,
        line=dict(color="rgba(216,195,106,0.32)", width=1.1),
    ))
    if "risk_start_line" in signal_df.columns:
        fig.add_trace(go.Scatter(
            x=signal_df.index,
            y=signal_df["risk_start_line"],
            name="시작선",
            line=dict(color="rgba(255,140,105,0.55)", width=1.2, dash="dot"),
        ))
    if "risk_end_line" in signal_df.columns:
        fig.add_trace(go.Scatter(
            x=signal_df.index,
            y=signal_df["risk_end_line"],
            name="종료선",
            line=dict(color="rgba(120,220,255,0.60)", width=1.2, dash="dot"),
        ))
    if indicator != "Index":
        spx_visible = spx_s.reindex(chart_index).dropna() if spx_s is not None else pd.Series(dtype=float)
        if not spx_visible.empty:
            fig.add_trace(go.Scatter(
                x=spx_visible.index,
                y=spx_visible,
                name=benchmark["label"],
                line=dict(color="rgba(182,182,182,0.88)", width=1.55),
                showlegend=True,
                hoverinfo="skip",
                yaxis="y2",
            ))
        fig.update_layout(yaxis2=_visible_price_yaxis("y", "right"))
        marker_price = spx_visible
        marker_axis = "y2"
    else:
        marker_price = main_s
        marker_axis = "y"
    _add_price_signal_markers(
        fig,
        signal_visible.rename(columns={"risk_start_signal": "down_start_signal", "risk_end_signal": "down_end_signal"}),
        marker_price,
        yaxis=marker_axis,
        prefix=indicator,
    )
    fig.update_layout(**_ml(title, height=300))
    fig.update_xaxes(range=[x_start, x_end], autorange=False)
    return fig


def _build_macro6_component_chart(
    component_key: str,
    years: int,
    benchmark_name: str,
    preset_cfg: dict,
    spx_s: pd.Series,
    sync_bucket: str | None = None,
):
    component_cfg = preset_cfg.get("component_cfgs", {}).get(component_key)
    if not component_cfg or spx_s is None or spx_s.empty:
        return None
    _chart_index, x_start, x_end = _macro_detail_chart_window(spx_s)
    warmup_years = max(years + 2, 5)
    benchmark = _get_macro_benchmark(benchmark_name)
    combo_spx = _macro3_filter_confirmed_us_daily(_yf_close(benchmark["code"], warmup_years, sync_bucket=sync_bucket))
    if combo_spx is None or combo_spx.empty:
        combo_spx = spx_s
    combo, active_indicators = _compute_macro6_combo_signal_frame(
        spx_s=combo_spx,
        benchmark_name=benchmark_name,
        selected_indicators=component_cfg.get("selected_indicators", []),
        cfgs=component_cfg.get("cfgs", {}),
        combo_k=int(component_cfg.get("combo_k", 1)),
        combo_l=int(component_cfg.get("combo_l", 0)),
        sync_bucket=sync_bucket,
    )
    if combo.empty:
        return None
    combo = combo.loc[combo.index >= spx_s.dropna().index.min()].copy()
    price = spx_s.reindex(combo.index).dropna()
    combo = combo.reindex(price.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index,
        y=price,
        name=benchmark["label"],
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
    ))
    component_event_df = combo.reset_index()
    component_event_df = component_event_df.rename(columns={component_event_df.columns[0]: "date"})
    _add_macro_combo_risk_cycle_background(fig, component_event_df, price.index)
    start_y = price.reindex(combo.index[combo["combo_start_signal"].fillna(False)])
    end_y = price.reindex(combo.index[combo["combo_end_signal"].fillna(False)])
    if not start_y.empty:
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, mode="markers", name="component 시작",
            marker=dict(symbol="triangle-down", size=9, color="rgba(210,55,55,0.95)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>component 시작: %{y:,.2f}<extra></extra>",
        ))
    if not end_y.empty:
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, mode="markers", name="component 종료",
            marker=dict(symbol="triangle-up", size=9, color="rgba(80,160,255,0.92)"),
            hovertemplate="<b>신호발생일 %{x|%Y-%m-%d}</b><br>component 종료: %{y:,.2f}<extra></extra>",
        ))
    selected_labels = " + ".join([_MACRO3_INDICATOR_LABELS.get(name, name) for name in active_indicators])
    fig.update_layout(**_ml(_macro3_component_label(component_key, component_cfg), height=260))
    if x_start is not None and x_end is not None:
        fig.update_xaxes(range=[x_start, x_end], autorange=False)
    fig.add_annotation(
        xref="paper", yref="paper", x=0.01, y=0.97, showarrow=False,
        text=f"{int(component_cfg.get('combo_k', 1))}/{len(active_indicators)} · 종료≤{int(component_cfg.get('combo_l', 0))}<br>{selected_labels}",
        font=dict(size=10, color="#C8C8C8", family="Arial, sans-serif"),
        align="left",
        bgcolor="rgba(0,0,0,0.18)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
        borderpad=4,
    )
    return fig


def _add_macro_combo_risk_cycle_background(fig: go.Figure, event_df: pd.DataFrame, x_index) -> None:
    if event_df is None or event_df.empty or "combo_risk_state" not in event_df.columns:
        return
    dates = pd.to_datetime(x_index)
    if len(dates) == 0:
        return
    state = (
        event_df.assign(date=pd.to_datetime(event_df["date"]))
        .drop_duplicates("date")
        .set_index("date")["combo_risk_state"]
        .reindex(dates)
        .fillna(False)
        .astype(bool)
    )
    start = None
    prev = False
    for dt, is_on in state.items():
        if is_on and not prev:
            start = dt
        if prev and not is_on and start is not None:
            fig.add_vrect(x0=start, x1=dt, fillcolor="rgba(255,75,110,0.11)", line_width=0, layer="below")
            start = None
        prev = bool(is_on)
    if prev and start is not None:
        fig.add_vrect(x0=start, x1=state.index[-1], fillcolor="rgba(255,75,110,0.11)", line_width=0, layer="below")


def make_macro_combo_dynamic_chart(
    years: int = 5,
    spx_s=None,
    benchmark_name: str = 'S&P500',
    selected_codes=None,
    cfgs=None,
    combo_k: int = 3,
    return_debug: bool = False,
    sync_bucket: str | None = None,
):
    _started = time.perf_counter()
    benchmark = _get_macro_benchmark(benchmark_name)
    visible_spx_s = spx_s
    if visible_spx_s is None or visible_spx_s.empty:
        visible_spx_s = _yf_close(benchmark['code'], years, sync_bucket=sync_bucket)
    if visible_spx_s is None or visible_spx_s.empty:
        return (None, pd.DataFrame()) if return_debug else None

    selected_codes = list(selected_codes or ["0", "1", "3", "6"])
    cfgs = cfgs or _get_macro2_dynamic_defaults()
    if not selected_codes:
        return (None, pd.DataFrame()) if return_debug else None

    warmup_years = _macro_combo_warmup_years(years, cfgs, selected_codes)
    combo_spx_s = _yf_close(benchmark['code'], warmup_years, sync_bucket=sync_bucket)
    if combo_spx_s is None or combo_spx_s.empty:
        combo_spx_s = visible_spx_s

    combo, active_codes = _compute_macro_combo_signal_frame(
        spx_s=combo_spx_s,
        benchmark_name=benchmark_name,
        selected_codes=selected_codes,
        cfgs=cfgs,
        combo_k=combo_k,
        sync_bucket=sync_bucket,
    )
    if combo.empty or not active_codes:
        return (None, pd.DataFrame()) if return_debug else None

    visible_spx_s = visible_spx_s.dropna().copy()
    if visible_spx_s.empty:
        return (None, pd.DataFrame()) if return_debug else None
    visible_cutoff = visible_spx_s.index.min()
    combo = combo.loc[combo.index >= visible_cutoff].copy()
    if combo.empty:
        return (None, pd.DataFrame()) if return_debug else None
    spx_aligned = visible_spx_s.reindex(combo.index).dropna()
    combo = combo.reindex(spx_aligned.index).copy()
    flag_cols = [f"{code}_down_flag" for code in active_codes]
    selected_labels = ", ".join(_MACRO2_SIGNAL_LABELS.get(code, code) for code in active_codes)
    combo_event_df = _build_macro_combo_event_df(
        combo=combo,
        active_codes=active_codes,
        benchmark_name=benchmark_name,
        selected_codes=selected_codes,
        cfgs=cfgs,
        combo_k=combo_k,
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark['label'],
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{benchmark['label']} %{{y:,.1f}}<extra></extra>',
    ))
    _add_macro_combo_risk_cycle_background(fig, combo_event_df, spx_aligned.index)

    start_rows = combo_event_df.loc[combo_event_df["combo_start_signal"]].copy()
    end_rows = combo_event_df.loc[combo_event_df["combo_end_signal"]].copy()
    start_y = spx_aligned.reindex(pd.to_datetime(start_rows["date"])) if not start_rows.empty else pd.Series(dtype=float)
    end_y = spx_aligned.reindex(pd.to_datetime(end_rows["date"])) if not end_rows.empty else pd.Series(dtype=float)
    if not start_rows.empty and not start_y.empty:
        start_rows = start_rows.set_index("date").reindex(start_y.index)
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name='__COMBO_START_MARKER__',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(210,55,55,0.95)'),
            legendgroup='__COMBO_START_MARKER__',
            showlegend=False,
            customdata=np.column_stack([
                start_rows["prev_active_count"].astype(int),
                start_rows["active_count"].astype(int),
                start_rows["active_flags"].fillna(""),
                start_rows["inactive_flags"].fillna(""),
                start_rows["flag_state_string"].fillna(""),
            ]),
            hovertemplate=(
                '<b>%{x|%Y-%m-%d}</b><br>'
                'event_type: START<br>'
                'prev_active_count: %{customdata[0]}<br>'
                'active_count: %{customdata[1]}<br>'
                'active_flags: %{customdata[2]}<br>'
                'inactive_flags: %{customdata[3]}<br>'
                'flag_state: %{customdata[4]}<extra></extra>'
            ),
        ))
        fig.add_trace(go.Scatter(
            x=[None], y=[None], name=f'리스크 시작 ({combo_k}/{len(flag_cols)})',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(210,55,55,0.95)'),
            hoverinfo='skip',
            legendgroup='__COMBO_START_MARKER__',
        ))
    if not end_rows.empty and not end_y.empty:
        end_rows = end_rows.set_index("date").reindex(end_y.index)
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name='__COMBO_END_MARKER__',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            legendgroup='__COMBO_END_MARKER__',
            showlegend=False,
            customdata=np.column_stack([
                end_rows["prev_active_count"].astype(int),
                end_rows["active_count"].astype(int),
                end_rows["active_flags"].fillna(""),
                end_rows["inactive_flags"].fillna(""),
                end_rows["flag_state_string"].fillna(""),
            ]),
            hovertemplate=(
                '<b>%{x|%Y-%m-%d}</b><br>'
                'event_type: END<br>'
                'prev_active_count: %{customdata[0]}<br>'
                'active_count: %{customdata[1]}<br>'
                'active_flags: %{customdata[2]}<br>'
                'inactive_flags: %{customdata[3]}<br>'
                'flag_state: %{customdata[4]}<extra></extra>'
            ),
        ))
        fig.add_trace(go.Scatter(
            x=[None], y=[None], name=f'리스크 종료 (<{combo_k}/{len(flag_cols)})',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            hoverinfo='skip',
            legendgroup='__COMBO_END_MARKER__',
        ))
    fig.update_layout(
        **_ml(str(preset_cfg.get("label") or f'⓪ 조합 리스크 사이클 ({benchmark["label"]}, {combo_k}/{len(flag_cols)})'), height=300),
    )
    if len(spx_aligned.index) >= 2:
        fig.update_xaxes(range=[spx_aligned.index.min(), spx_aligned.index.max()])
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
    if return_debug:
        _macro_debug_log(
            "make_macro_combo_dynamic_chart",
            benchmark_name=benchmark_name,
            years=years,
            selected_codes=len(selected_codes),
            combo_k=combo_k,
            elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
        )
        return fig, combo_event_df
    _macro_debug_log(
        "make_macro_combo_dynamic_chart",
        benchmark_name=benchmark_name,
        years=years,
        selected_codes=len(selected_codes),
        combo_k=combo_k,
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return fig


def _build_macro_meta_combo_event_df(
    combo_a_event_df: pd.DataFrame,
    combo_b_event_df: pd.DataFrame,
    combo_a_label: str,
    combo_b_label: str,
    benchmark_name: str,
    exit_mode: str = "AND_EXIT",
    start_persist: int = 1,
    end_persist: int = 1,
    min_hold_days: int = 0,
    cooldown_days: int = 0,
) -> pd.DataFrame:
    if combo_a_event_df is None or combo_a_event_df.empty or combo_b_event_df is None or combo_b_event_df.empty:
        return pd.DataFrame()

    a = combo_a_event_df.copy()
    b = combo_b_event_df.copy()
    a["date"] = pd.to_datetime(a["date"])
    b["date"] = pd.to_datetime(b["date"])
    a = a.sort_values("date").set_index("date")
    b = b.sort_values("date").set_index("date")

    idx = a.index.union(b.index).sort_values()
    out = pd.DataFrame(index=idx)
    out["a_state"] = a["combo_risk_state"].reindex(idx).fillna(False).astype(bool)
    out["b_state"] = b["combo_risk_state"].reindex(idx).fillna(False).astype(bool)
    out["a_start_signal"] = a["combo_start_signal"].reindex(idx).fillna(False).astype(bool)
    out["a_end_signal"] = a["combo_end_signal"].reindex(idx).fillna(False).astype(bool)
    out["b_start_signal"] = b["combo_start_signal"].reindex(idx).fillna(False).astype(bool)
    out["b_end_signal"] = b["combo_end_signal"].reindex(idx).fillna(False).astype(bool)

    flag_cols = sorted(
        set([c for c in a.columns if c.endswith("_flag")]).union([c for c in b.columns if c.endswith("_flag")])
    )
    for col in flag_cols:
        a_flag = a[col].reindex(idx).fillna(False).astype(bool) if col in a.columns else pd.Series(False, index=idx)
        b_flag = b[col].reindex(idx).fillna(False).astype(bool) if col in b.columns else pd.Series(False, index=idx)
        out[col] = (a_flag | b_flag).astype(bool)

    meta_in_cycle = False
    start_streak = 0
    end_streak = 0
    hold_days = 0
    cooldown_remaining = 0
    active_counts = []
    states = []
    starts = []
    ends = []
    for row in out.itertuples():
        a_state = bool(row.a_state)
        b_state = bool(row.b_state)
        start_hit = a_state and b_state
        hold_hit = (a_state or b_state) if exit_mode == "AND_EXIT" else (a_state and b_state)

        start_streak = start_streak + 1 if start_hit else 0
        end_condition = not hold_hit
        end_streak = end_streak + 1 if end_condition else 0
        start_ready = start_streak >= max(1, int(start_persist))
        end_ready = end_streak >= max(1, int(end_persist))

        start_signal = False
        end_signal = False
        if meta_in_cycle:
            hold_days += 1
            if hold_days > max(0, int(min_hold_days)) and end_ready:
                meta_in_cycle = False
                end_signal = True
                hold_days = 0
                cooldown_remaining = max(0, int(cooldown_days))
        else:
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
            elif start_ready:
                meta_in_cycle = True
                start_signal = True
                hold_days = 1

        active_counts.append(int(a_state) + int(b_state))
        states.append(meta_in_cycle)
        starts.append(start_signal)
        ends.append(end_signal)

    out["active_count"] = active_counts
    out["combo_risk_state"] = pd.Series(states, index=idx, dtype=bool)
    out["combo_start_signal"] = pd.Series(starts, index=idx, dtype=bool)
    out["combo_end_signal"] = pd.Series(ends, index=idx, dtype=bool)
    out["prev_active_count"] = out["active_count"].shift(1).fillna(0).astype(int)
    out["combo_state_before"] = out["combo_risk_state"].shift(1).fillna(False).astype(bool)

    def _meta_active_flags(row) -> str:
        names = []
        if bool(row["a_state"]):
            names.append(combo_a_label)
        if bool(row["b_state"]):
            names.append(combo_b_label)
        return ", ".join(names)

    def _meta_inactive_flags(row) -> str:
        names = []
        if not bool(row["a_state"]):
            names.append(combo_a_label)
        if not bool(row["b_state"]):
            names.append(combo_b_label)
        return ", ".join(names)

    def _meta_flag_state_string(row) -> str:
        return f"{int(bool(row['a_state']))}/{int(bool(row['b_state']))}"

    out["active_flags"] = out.apply(_meta_active_flags, axis=1)
    out["inactive_flags"] = out.apply(_meta_inactive_flags, axis=1)
    out["prev_active_flags"] = out["active_flags"].shift(1).fillna("")
    out["prev_inactive_flags"] = out["inactive_flags"].shift(1).fillna("")
    out["flag_state_string"] = out.apply(_meta_flag_state_string, axis=1)
    out["selected_codes"] = "META_A,META_B"
    out["selected_labels"] = f"{combo_a_label} + {combo_b_label}"
    out["benchmark_name"] = benchmark_name
    out["combo_k"] = 2
    out["combo_n"] = 2
    out["initial_state_at_visible_start"] = bool(out["combo_risk_state"].iloc[0]) if not out.empty else False
    out["combo_slug"] = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{benchmark_name}_{combo_a_label}_{combo_b_label}_{exit_mode}").lower()
    out["param_signature"] = (
        f"{combo_a_label} + {combo_b_label} ({exit_mode}, "
        f"SP={int(start_persist)}, EP={int(end_persist)}, MH={int(min_hold_days)}, CD={int(cooldown_days)})"
    )
    out["combo_label"] = f"{combo_a_label} + {combo_b_label}"

    return out.rename_axis("date").reset_index()


def make_macro_meta_combo_dynamic_chart(
    spx_s: pd.Series,
    benchmark_name: str,
    combo_a_event_df: pd.DataFrame,
    combo_b_event_df: pd.DataFrame,
    combo_a_label: str,
    combo_b_label: str,
    exit_mode: str = "AND_EXIT",
    start_persist: int = 1,
    end_persist: int = 1,
    min_hold_days: int = 0,
    cooldown_days: int = 0,
    return_debug: bool = False,
):
    _started = time.perf_counter()
    if spx_s is None or spx_s.empty:
        return (None, pd.DataFrame()) if return_debug else None

    benchmark = _get_macro_benchmark(benchmark_name)
    meta_event_df = _build_macro_meta_combo_event_df(
        combo_a_event_df=combo_a_event_df,
        combo_b_event_df=combo_b_event_df,
        combo_a_label=combo_a_label,
        combo_b_label=combo_b_label,
        benchmark_name=benchmark_name,
        exit_mode=exit_mode,
        start_persist=start_persist,
        end_persist=end_persist,
        min_hold_days=min_hold_days,
        cooldown_days=cooldown_days,
    )
    if meta_event_df.empty:
        return (None, pd.DataFrame()) if return_debug else None

    meta_event_df = meta_event_df.sort_values("date").copy()
    spx_aligned = spx_s.reindex(pd.to_datetime(meta_event_df["date"])).dropna()
    if spx_aligned.empty:
        return (None, pd.DataFrame()) if return_debug else None
    meta_event_df = meta_event_df.set_index("date").reindex(spx_aligned.index).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spx_aligned.index, y=spx_aligned, name=benchmark["label"],
        line=dict(color='rgba(182,182,182,0.88)', width=1.55),
        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{benchmark["label"]} %{{y:,.1f}}<extra></extra>',
    ))
    _add_macro_combo_risk_cycle_background(fig, meta_event_df, spx_aligned.index)

    start_rows = meta_event_df.loc[meta_event_df["combo_start_signal"]].copy()
    end_rows = meta_event_df.loc[meta_event_df["combo_end_signal"]].copy()
    start_y = spx_aligned.reindex(pd.to_datetime(start_rows["date"])) if not start_rows.empty else pd.Series(dtype=float)
    end_y = spx_aligned.reindex(pd.to_datetime(end_rows["date"])) if not end_rows.empty else pd.Series(dtype=float)

    if not start_rows.empty and not start_y.empty:
        start_rows = start_rows.set_index("date").reindex(start_y.index)
        fig.add_trace(go.Scatter(
            x=start_y.index, y=start_y, name='__COMBO_START_MARKER__',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(210,55,55,0.95)'),
            legendgroup='__COMBO_START_MARKER__',
            showlegend=False,
            customdata=np.column_stack([
                start_rows["prev_active_count"].astype(int),
                start_rows["active_count"].astype(int),
                start_rows["active_flags"].fillna(""),
                start_rows["inactive_flags"].fillna(""),
                start_rows["flag_state_string"].fillna(""),
            ]),
            hovertemplate=(
                '<b>%{x|%Y-%m-%d}</b><br>'
                'event_type: START<br>'
                'prev_active_count: %{customdata[0]}<br>'
                'active_count: %{customdata[1]}<br>'
                'active_flags: %{customdata[2]}<br>'
                'inactive_flags: %{customdata[3]}<br>'
                'flag_state: %{customdata[4]}<extra></extra>'
            ),
        ))
        fig.add_trace(go.Scatter(
            x=[None], y=[None], name='리스크 시작 (A&B)',
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='rgba(210,55,55,0.95)'),
            hoverinfo='skip',
            legendgroup='__COMBO_START_MARKER__',
        ))

    if not end_rows.empty and not end_y.empty:
        end_rows = end_rows.set_index("date").reindex(end_y.index)
        fig.add_trace(go.Scatter(
            x=end_y.index, y=end_y, name='__COMBO_END_MARKER__',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            legendgroup='__COMBO_END_MARKER__',
            showlegend=False,
            customdata=np.column_stack([
                end_rows["prev_active_count"].astype(int),
                end_rows["active_count"].astype(int),
                end_rows["active_flags"].fillna(""),
                end_rows["inactive_flags"].fillna(""),
                end_rows["flag_state_string"].fillna(""),
            ]),
            hovertemplate=(
                '<b>%{x|%Y-%m-%d}</b><br>'
                'event_type: END<br>'
                'prev_active_count: %{customdata[0]}<br>'
                'active_count: %{customdata[1]}<br>'
                'active_flags: %{customdata[2]}<br>'
                'inactive_flags: %{customdata[3]}<br>'
                'flag_state: %{customdata[4]}<extra></extra>'
            ),
        ))
        fig.add_trace(go.Scatter(
            x=[None], y=[None], name='리스크 종료 (A,B OFF)',
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='rgba(80,160,255,0.92)'),
            hoverinfo='skip',
            legendgroup='__COMBO_END_MARKER__',
        ))

    fig.update_layout(
        **_ml(f'⓪ 메타 리스크 사이클 ({benchmark["label"]}, Meta)', height=300),
    )
    if len(spx_aligned.index) >= 2:
        fig.update_xaxes(range=[spx_aligned.index.min(), spx_aligned.index.max()])
    fig.add_annotation(
        xref='paper', yref='paper', x=0.01, y=0.98, showarrow=False,
        text=f'<b>메타조합</b>: {combo_a_label} + {combo_b_label}',
        font=dict(size=11, color='#C8C8C8'),
        align='left',
        bgcolor='rgba(0,0,0,0.18)',
        bordercolor='rgba(255,255,255,0.08)',
        borderwidth=1,
        borderpad=4,
    )
    if return_debug:
        _macro_debug_log(
            "make_macro_meta_combo_dynamic_chart",
            benchmark_name=benchmark_name,
            exit_mode=exit_mode,
            start_persist=start_persist,
            end_persist=end_persist,
            min_hold_days=min_hold_days,
            cooldown_days=cooldown_days,
            elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
        )
        return fig, meta_event_df
    _macro_debug_log(
        "make_macro_meta_combo_dynamic_chart",
        benchmark_name=benchmark_name,
        exit_mode=exit_mode,
        start_persist=start_persist,
        end_persist=end_persist,
        min_hold_days=min_hold_days,
        cooldown_days=cooldown_days,
        elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
    )
    return fig


def _make_inverted_spread_chart(
    s: pd.Series,
    title: str,
    trace_name: str,
    spx_s=None,
    benchmark_label='S&P500',
    color='#D8C36A',
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
                               ema_span: int | None = None, sync_bucket: str | None = None):
    """① HY 크레딧 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        hy = _korean_credit_proxy_series(years, 'A', sync_bucket=sync_bucket)
        title = '① 회사채(A-이상)-국고채 상대강도 (반전, 한국 proxy)'
        trace_name = 'A-이상 회사채 프록시'
        suffix = ''
    else:
        hy = _credit_spread_series('BAMLH0A0HYM2', years, sync_bucket=sync_bucket)
        title = '① HY 크레딧 스프레드 (반전, OAS %)'
        trace_name = 'HY 스프레드'
        suffix = '%'
    return _make_inverted_spread_chart(
        hy, title, trace_name,
        spx_s=spx_s, benchmark_label=benchmark['label'], color='#D8C36A', suffix=suffix, show_raw=show_raw,
        downturn_params=downturn_params, dynamic_mode=dynamic_mode, dynamic_window=dynamic_window,
        dynamic_start_quantile=dynamic_start_quantile, dynamic_end_quantile=dynamic_end_quantile, ema_span=ema_span,
    )


def make_macro_ig_spread_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                               dynamic_mode: bool = False, dynamic_window: int = 126,
                               dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                               ema_span: int | None = None, sync_bucket: str | None = None):
    """② IG 크레딧 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        ig = _korean_credit_proxy_series(years, 'AA', sync_bucket=sync_bucket)
        title = '② 회사채(AA-이상)-국고채 상대강도 (반전, 한국 proxy)'
        trace_name = 'AA-이상 회사채 프록시'
        suffix = ''
    else:
        ig = _credit_spread_series('BAMLC0A0CM', years, sync_bucket=sync_bucket)
        title = '② IG 크레딧 스프레드 (반전, OAS %)'
        trace_name = 'IG 스프레드'
        suffix = '%'
    return _make_inverted_spread_chart(
        ig, title, trace_name,
        spx_s=spx_s, benchmark_label=benchmark['label'], color='#D8C36A', suffix=suffix, show_raw=show_raw,
        downturn_params=downturn_params, dynamic_mode=dynamic_mode, dynamic_window=dynamic_window,
        dynamic_start_quantile=dynamic_start_quantile, dynamic_end_quantile=dynamic_end_quantile, ema_span=ema_span,
    )


def make_macro_credit_stress_chart(years: int = 5, spx_s=None, show_raw=True, downturn_params=None, benchmark_name='S&P500',
                                   threshold_mode=False, threshold_value: float = 0.0, ema_span: int | None = None,
                                   dynamic_mode: bool = False, dynamic_window: int = 126,
                                   dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                                   threshold_end_value: float | None = None, sync_bucket: str | None = None):
    """③ 신용 스트레스 지수: HY + NFCI + VIX z-score 합성, 반전 표시."""
    benchmark = _get_macro_benchmark(benchmark_name)
    parts = []
    if benchmark['kind'] == 'kr':
        hy = _korean_credit_proxy_series(years + 1, 'A', sync_bucket=sync_bucket)
        ig = _korean_credit_proxy_series(years + 1, 'AA', sync_bucket=sync_bucket)
        fx = _korean_fx_stress_series(years + 1, sync_bucket=sync_bucket)
        hv20 = _korean_volatility_series(years + 1, benchmark_s=spx_s, window=20, sync_bucket=sync_bucket)
        if not hy.empty: parts.append(_zscore(hy).rename('CorpA'))
        if not ig.empty: parts.append(_zscore(ig).rename('CorpAA'))
        if not fx.empty: parts.append(_zscore(fx).rename('USDKRW'))
        if not hv20.empty: parts.append(_zscore(hv20).rename('HV20'))
        title = '③ 한국 스트레스 지수 (반전, 회사채·환율·변동성)'
    else:
        hy   = _credit_spread_series('BAMLH0A0HYM2', years + 1, sync_bucket=sync_bucket)
        nfci = _fred('NFCI',         years + 1, sync_bucket=sync_bucket)
        vix  = _yf_close('^VIX',     years + 1, sync_bucket=sync_bucket)
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
    if show_raw:
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s.clip(lower=0),
                                 fill='tozeroy', fillcolor='rgba(75,255,179,0.10)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s.clip(upper=0),
                                 fill='tozeroy', fillcolor='rgba(255,75,110,0.10)',
                                 line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=plot_s.index, y=plot_s, name='신용 스트레스 (반전)',
                                 line=dict(color='#D8C36A', width=1.2),
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
                             dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                             sync_bucket: str | None = None):
    """④ VIX 레벨: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        vix = _korean_volatility_series(years, benchmark_s=spx_s, window=20, sync_bucket=sync_bucket)
        title = '④ VIX (한국 proxy: HV20, 반전)'
        trace_name = 'HV20 (반전)'
        line_label = '반전 HV20'
        corr_label = f'반전 HV20 vs {benchmark["label"]}'
    else:
        vix = _yf_close('^VIX', years, sync_bucket=sync_bucket)
        title = '④ VIX (반전)'
        trace_name = 'VIX 레벨 (반전)'
        line_label = '반전 VIX'
        corr_label = f'반전 VIX vs {benchmark["label"]}'
    if vix.empty:
        return None
    plot_s = (-vix).dropna()
    fig = go.Figure()
    if show_raw:
        fig.add_trace(go.Scatter(
            x=plot_s.index, y=plot_s, name=trace_name,
            line=dict(color='#D8C36A', width=1.2),
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
                                dynamic_start_quantile: float = 0.4, dynamic_end_quantile: float = 0.2,
                                sync_bucket: str | None = None):
    """⑤ VIX-VIX3M 스프레드: 반전 표시 + EMA 하락 경고."""
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        spread = _korean_vol_term_spread_series(years, benchmark_s=spx_s, sync_bucket=sync_bucket)
        title = '⑤ VIX 스프레드 (한국 proxy, 반전)'
        trace_name = 'HV20-HV60 스프레드'
    else:
        vix   = _yf_close('^VIX',   years, sync_bucket=sync_bucket)
        vix3m = _yf_close('^VIX3M', years, sync_bucket=sync_bucket)
        if vix.empty or vix3m.empty:
            return None
        spread = (vix - vix3m.reindex(vix.index)).dropna()
        title = '⑤ VIX 스프레드 (반전)'
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
            line=dict(color='#D8C36A', width=1.2),
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
    if len(plot_s.index) >= 2:
        fig.update_xaxes(range=[plot_s.index.min(), plot_s.index.max()])
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


def _get_macro_yield_bundle(years: int, benchmark_name='S&P500', sync_bucket: str | None = None) -> dict:
    benchmark = _get_macro_benchmark(benchmark_name)
    if benchmark['kind'] == 'kr':
        spread, bond_3y, bond_10y = _korean_yield_curve_proxy_bundle(years)
        return {
            "benchmark": benchmark,
            "kind": "kr",
            "spread_10y3m": spread,
            "spread_10y2y": pd.Series(dtype=float),
            "bond_3y": bond_3y,
            "bond_10y": bond_10y,
            "dgs10": pd.Series(dtype=float),
            "dfii10": pd.Series(dtype=float),
            "dgs2": pd.Series(dtype=float),
            "dtb3": pd.Series(dtype=float),
        }

    t3m = _fred('T10Y3M', years, sync_bucket=sync_bucket)
    t2y = _fred('T10Y2Y', years, sync_bucket=sync_bucket)
    dgs10 = _fred('DGS10', years, sync_bucket=sync_bucket)
    dfii10 = _fred('DFII10', years, sync_bucket=sync_bucket)
    dgs2 = _fred('DGS2', years, sync_bucket=sync_bucket)
    dtb3 = _fred('DTB3', years, sync_bucket=sync_bucket)

    if t3m.empty:
        if not dgs10.empty and not dtb3.empty:
            t3m = (dgs10 - dtb3.reindex(dgs10.index).interpolate()).dropna()
    if t2y.empty:
        if not dgs10.empty and not dgs2.empty:
            t2y = (dgs10 - dgs2.reindex(dgs10.index).interpolate()).dropna()
    return {
        "benchmark": benchmark,
        "kind": "us",
        "spread_10y3m": t3m,
        "spread_10y2y": t2y,
        "bond_3y": pd.Series(dtype=float),
        "bond_10y": pd.Series(dtype=float),
        "dgs10": dgs10,
        "dfii10": dfii10,
        "dgs2": dgs2,
        "dtb3": dtb3,
    }


def make_macro_rate_levels_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """⑥ 대표 금리 레벨 차트."""
    bundle = _get_macro_yield_bundle(years, benchmark_name)
    benchmark = bundle["benchmark"]

    if bundle["kind"] == "kr":
        bond_3y = bundle["bond_3y"]
        bond_10y = bundle["bond_10y"]
        if bond_3y.empty and bond_10y.empty:
            return None

        fig = go.Figure()
        if not bond_10y.empty:
            fig.add_trace(go.Scatter(
                x=bond_10y.index, y=bond_10y, name='국고채10년 ETF',
                line=dict(color='rgba(200,200,200,0.72)', width=1.25),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  10년 ETF %{y:.2f}<extra></extra>',
            ))
        if not bond_3y.empty:
            fig.add_trace(go.Scatter(
                x=bond_3y.index, y=bond_3y, name='국고채3년 ETF',
                line=dict(color='rgba(120,220,255,0.72)', width=1.2),
                hovertemplate='<b>%{x|%Y-%m-%d}</b>  3년 ETF %{y:.2f}<extra></extra>',
            ))
        main_s = bond_10y if not bond_10y.empty else bond_3y
        _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
        fig.update_layout(
            **_ml('⑥ 국고채 10년 · 3년 ETF proxy', height=300),
            yaxis2=_visible_price_yaxis('y', 'right'),
        )
        _add_corr_annotation(fig, main_s, spx_s, label=f'vs {benchmark["label"]}')
        return fig

    dgs10 = bundle["dgs10"]
    dfii10 = bundle["dfii10"]
    dgs2 = bundle["dgs2"]
    dtb3 = bundle["dtb3"]
    if dgs10.empty and dfii10.empty and dgs2.empty and dtb3.empty:
        return None

    fig = go.Figure()
    if not dgs10.empty:
        fig.add_trace(go.Scatter(
            x=dgs10.index, y=dgs10, name='10Y 명목',
            line=dict(color='rgba(200,200,200,0.58)', width=0.95),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y 명목 %{y:.2f}%<extra></extra>',
        ))
    if not dfii10.empty:
        fig.add_trace(go.Scatter(
            x=dfii10.index, y=dfii10, name='10Y 실질',
            line=dict(color='rgba(255,180,120,0.62)', width=0.95),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y 실질 %{y:.2f}%<extra></extra>',
        ))
    if not dgs2.empty:
        fig.add_trace(go.Scatter(
            x=dgs2.index, y=dgs2, name='2Y',
            line=dict(color='rgba(120,220,255,0.56)', width=0.9, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  2Y %{y:.2f}%<extra></extra>',
        ))
    if not dtb3.empty:
        fig.add_trace(go.Scatter(
            x=dtb3.index, y=dtb3, name='3M',
            line=dict(color='rgba(120,126,231,0.54)', width=0.9, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  3M %{y:.2f}%<extra></extra>',
        ))

    main_s = dgs10 if not dgs10.empty else dfii10 if not dfii10.empty else dgs2 if not dgs2.empty else dtb3
    _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
    fig.update_layout(
        **_ml('⑥ 10Y 명목·실질 · 2Y · 3M', height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.layout.yaxis.ticksuffix = '%'
    _add_corr_annotation(fig, main_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_yield_spread_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """⑦ 대표 금리 스프레드 차트."""
    bundle = _get_macro_yield_bundle(years, benchmark_name)
    benchmark = bundle["benchmark"]

    if bundle["kind"] == "kr":
        spread = bundle["spread_10y3m"]
        if spread.empty:
            return None
        fig = go.Figure()
        fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
        fig.add_trace(go.Scatter(
            x=spread.index, y=spread, name='3Y-10Y 상대강도',
            line=dict(color='#4BFFB3', width=1.5),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  상대강도 %{y:.2f}<extra></extra>',
        ))
        _add_spx_overlay(fig, spread, spx_s, yaxis='y2', label=benchmark['label'])
        fig.update_layout(
            **_ml('⑦ 국고채 3Y-10Y 상대강도 (ETF proxy)', height=300),
            yaxis2=_visible_price_yaxis('y', 'right'),
        )
        _add_corr_annotation(fig, spread, spx_s, label=f'vs {benchmark["label"]}')
        return fig

    t3m = bundle["spread_10y3m"]
    t2y = bundle["spread_10y2y"]
    dgs10 = bundle["dgs10"]
    dfii10 = bundle["dfii10"]
    breakeven10 = pd.Series(dtype=float)
    if not dgs10.empty and not dfii10.empty:
        breakeven10 = (dgs10 - dfii10.reindex(dgs10.index).interpolate()).dropna()
    if t3m.empty and t2y.empty and breakeven10.empty:
        return None

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.20)', width=1))
    if not t3m.empty:
        fig.add_trace(go.Scatter(
            x=t3m.index, y=t3m, name='10Y-3M 스프레드',
            line=dict(color='rgba(75,255,179,0.62)', width=0.95, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y-3M %{y:.2f}%<extra></extra>',
        ))
    if not t2y.empty:
        fig.add_trace(go.Scatter(
            x=t2y.index, y=t2y, name='10Y-2Y 스프레드',
            line=dict(color='rgba(120,220,255,0.60)', width=0.95, dash='dot'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y-2Y %{y:.2f}%<extra></extra>',
        ))
    if not breakeven10.empty:
        fig.add_trace(go.Scatter(
            x=breakeven10.index, y=breakeven10, name='10Y 명목-실질',
            line=dict(color='rgba(255,180,120,0.66)', width=1.0),
            hovertemplate='<b>%{x|%Y-%m-%d}</b>  10Y 명목-실질 %{y:.2f}%<extra></extra>',
        ))
    main_s = t3m if not t3m.empty else t2y if not t2y.empty else breakeven10
    _add_spx_overlay(fig, main_s, spx_s, yaxis='y2', label=benchmark['label'])
    fig.update_layout(
        **_ml('⑦ 10Y-3M · 10Y-2Y · 10Y 명목-실질', height=300),
        yaxis2=_visible_price_yaxis('y', 'right'),
    )
    fig.layout.yaxis.ticksuffix = '%'
    _add_corr_annotation(fig, main_s, spx_s, label=f'vs {benchmark["label"]}')
    return fig


def make_macro_yield_curve_chart(years: int = 5, spx_s=None, benchmark_name='S&P500'):
    """하위 호환용: 금리 스프레드 차트."""
    return make_macro_yield_spread_chart(years=years, spx_s=spx_s, benchmark_name=benchmark_name)


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
        specs=[[{"secondary_y": True}], [{}]],
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.06,
        subplot_titles=['회사별 / 합산 CAPEX (billion USD)', '합산 CAPEX 변화율 (QoQ / YoY, %)'],
    )

    line_map = {
        'Google / Alphabet': 'rgba(75,255,179,0.58)',
        'Microsoft': 'rgba(122,175,212,0.52)',
        'Meta': 'rgba(255,140,105,0.56)',
        'Amazon': 'rgba(120,220,255,0.58)',
        'Total CAPEX': '#EDEDED',
    }
    company_dash_map = {
        'Google / Alphabet': 'solid',
        'Microsoft': 'dot',
        'Meta': 'dash',
        'Amazon': 'solid',
    }
    for col in [c for c in capex_df.columns if c != 'Total CAPEX']:
        if capex_df[col].dropna().empty:
            continue
        fig.add_trace(go.Scatter(
            x=capex_df.index, y=capex_df[col], name=col, customdata=_quarter_labels,
            line=dict(color=line_map.get(col, 'rgba(136,136,136,0.50)'), width=1.05, dash=company_dash_map.get(col, 'solid')),
            connectgaps=True,
            hovertemplate='<b>%{customdata}</b><br>%{y:.1f} bn USD<extra></extra>',
        ), row=1, col=1, secondary_y=False)

    fig.add_trace(go.Scatter(
        x=total.index, y=total, name='4개사 합산 CAPEX', customdata=_quarter_labels,
        line=dict(color=line_map['Total CAPEX'], width=2.0),
        connectgaps=True,
        hovertemplate='<b>%{customdata}</b><br>합산 %{y:.1f} bn USD<extra></extra>',
    ), row=1, col=1, secondary_y=True)

    fig.add_trace(go.Scatter(
        x=qoq.index, y=qoq, name='합산 QoQ%', customdata=_quarter_labels,
        line=dict(color='rgba(75,255,179,0.78)', width=1.35),
        connectgaps=True,
        hovertemplate='<b>%{customdata}</b><br>QoQ %{y:.1f}%<extra></extra>',
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=yoy.index, y=yoy, name='합산 YoY%', customdata=_quarter_labels,
        line=dict(color='rgba(255,140,105,0.82)', width=1.35),
        connectgaps=True,
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
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False, row=1, col=1, secondary_y=False)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False, row=1, col=1, secondary_y=True)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', tickfont=dict(size=9), zeroline=False, row=2, col=1)
    fig.add_annotation(
        text='Source: Yahoo Finance quarterly cash flow + local CSV fallback',
        x=1.0, y=1.13, xref='paper', yref='paper',
        xanchor='right', yanchor='bottom',
        showarrow=False,
        font=dict(size=9, color='#666'),
    )
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


def _render_macro_combo_common_css():
    st.markdown("""
    <style>
    .macro2-divider {
        border-top: 1px solid rgba(255,255,255,0.08);
        margin: 24px 0;
    }
    .macro2-helper-text {
        font-size: 11.5px;
        line-height: 1.45;
        color: rgba(255,255,255,0.56);
        margin: 2px 0 14px 0;
    }
    .macro2-control-label {
        font-size: 11.5px;
        color: rgba(255,255,255,0.72);
        font-weight: 600;
        line-height: 1.2;
        margin-bottom: 0.7rem;
    }
    .macro2-control-spacer {
        height: 18px;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_dashboard_common_ui_css():
    st.markdown("""
    <style>
    .dash-section-title {
        font-size: 13px;
        font-weight: 700;
        color: rgba(237,237,237,0.92);
        margin: 18px 0 8px 0;
    }
    .dash-muted {
        font-size: 11.5px;
        color: rgba(237,237,237,0.54);
        line-height: 1.45;
    }
    .dash-card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 8px;
        margin: 8px 0 14px 0;
    }
    .dash-card {
        background: #141416;
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 6px;
        padding: 10px 12px;
        min-height: 72px;
    }
    .dash-card-label {
        font-size: 10px;
        letter-spacing: 0.7px;
        text-transform: uppercase;
        color: rgba(237,237,237,0.46);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .dash-card-value {
        margin-top: 4px;
        font-size: 18px;
        font-weight: 700;
        color: #EDEDED;
        font-variant-numeric: tabular-nums;
    }
    .dash-card-note {
        margin-top: 3px;
        font-size: 11px;
        color: rgba(237,237,237,0.52);
        line-height: 1.35;
    }
    .dash-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,0.1);
        margin-right: 5px;
        margin-bottom: 5px;
    }
    .dash-badge-on {
        color: #FFB86C;
        background: rgba(255,184,108,0.12);
        border-color: rgba(255,184,108,0.28);
    }
    .dash-badge-off {
        color: #8EA0B7;
        background: rgba(142,160,183,0.10);
        border-color: rgba(142,160,183,0.22);
    }
    .dash-badge-good {
        color: #4BFFB3;
        background: rgba(75,255,179,0.10);
        border-color: rgba(75,255,179,0.24);
    }
    .dash-divider {
        border-top: 1px solid rgba(255,255,255,0.07);
        margin: 18px 0;
    }
    </style>
    """, unsafe_allow_html=True)


_SCANNER2_ASSET_ROOT = os.path.join(_APP_DIR, "signal_scanner2_assets")
_SCANNER2_PRESET_PATH = os.path.join(_SCANNER2_ASSET_ROOT, "signal_scanner2_final5_presets.json")


def _scanner2_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@st.cache_data(show_spinner=False)
def _load_scanner2_preset_manifest():
    if not os.path.exists(_SCANNER2_PRESET_PATH):
        raise FileNotFoundError(f"신호스캐너2 프리셋 파일이 없습니다: {_SCANNER2_PRESET_PATH}")
    with open(_SCANNER2_PRESET_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for market, spec in manifest.get("markets", {}).items():
        for _name, file_spec in spec.get("source_files", {}).items():
            path = os.path.join(_APP_DIR, file_spec["path"])
            if not os.path.exists(path):
                raise FileNotFoundError(f"{market} asset missing: {path}")
            actual = _scanner2_sha256(path)
            expected = file_spec.get("sha256")
            if expected and actual != expected:
                raise RuntimeError(f"{market} asset hash mismatch: {file_spec['path']}")
    return manifest


@st.cache_data(show_spinner=False)
def _load_scanner2_market_assets(market: str):
    manifest = _load_scanner2_preset_manifest()
    market_spec = manifest["markets"][market]
    source_files = market_spec["source_files"]
    frozen = pd.read_parquet(os.path.join(_APP_DIR, source_files["frozen_ohlcv_parquet"]["path"]))
    candidates = pd.read_csv(os.path.join(_APP_DIR, source_files["candidates_csv"]["path"]))
    daily = pd.read_parquet(os.path.join(_APP_DIR, source_files["daily_signals_parquet"]["path"]))
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    frozen = frozen.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    daily = daily.sort_values(["candidate_id", "date"])
    return frozen, candidates, daily


def _scanner2_state_from_events(start_event: pd.Series, end_event: pd.Series):
    idx = start_event.index.union(end_event.index).sort_values()
    start_event = start_event.reindex(idx).fillna(False).astype(bool)
    end_event = end_event.reindex(idx).fillna(False).astype(bool)
    states = []
    starts = []
    ends = []
    in_risk = False
    for dt in idx:
        start = bool(start_event.loc[dt])
        end = bool(end_event.loc[dt])
        start_signal = False
        end_signal = False
        if not in_risk and start:
            in_risk = True
            start_signal = True
        elif in_risk and end:
            in_risk = False
            end_signal = True
        states.append(in_risk)
        starts.append(start_signal)
        ends.append(end_signal)
    return (
        pd.Series(states, index=idx, dtype=bool),
        pd.Series(starts, index=idx, dtype=bool),
        pd.Series(ends, index=idx, dtype=bool),
    )


def _scanner2_align_signal(signal: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    if signal is None or signal.empty:
        return pd.DataFrame(index=dates, data={
            "risk_state": False,
            "risk_start_signal": False,
            "risk_end_signal": False,
            "valid_signal": False,
        })
    source = signal.copy()
    source.index = pd.DatetimeIndex(source.index).normalize()
    union = source.index.union(dates).sort_values()
    state = source["risk_state"].astype(bool).reindex(union).ffill().fillna(False).reindex(dates).fillna(False)
    prev = state.shift(1, fill_value=False)
    valid_source = source.get("valid_signal", pd.Series(True, index=source.index)).astype(bool)
    valid_dates = source.index[valid_source]
    first_valid = valid_dates.min() if len(valid_dates) else dates.max()
    return pd.DataFrame({
        "risk_state": state.astype(bool),
        "risk_start_signal": (state & ~prev).astype(bool),
        "risk_end_signal": (~state & prev).astype(bool),
        "valid_signal": pd.Series(dates >= first_valid, index=dates, dtype=bool),
    }, index=dates)


def _scanner2_parse_index_param(param_id: str) -> dict:
    m = re.fullmatch(r"idx_ema(\d+)_w(\d+)_sq(\d+)_eq(\d+)", str(param_id))
    if not m:
        raise ValueError(f"Index param_id 파싱 실패: {param_id}")
    return {
        "ema_span": int(m.group(1)),
        "window": int(m.group(2)),
        "start_q": int(m.group(3)),
        "end_q": int(m.group(4)),
    }


def _scanner2_parse_rsi_param(param_id: str) -> dict:
    m = re.fullmatch(r"rsi_p(\d+)_lb(\d+)_q(\d+)_(\d+)", str(param_id))
    if not m:
        raise ValueError(f"RSI param_id 파싱 실패: {param_id}")
    return {
        "period": int(m.group(1)),
        "lookback": int(m.group(2)),
        "lower_q": int(m.group(3)),
        "upper_q": int(m.group(4)),
    }


def _scanner2_parse_bb_param(param_id: str) -> dict:
    m = re.fullmatch(r"bb_w(\d+)_std([0-9]+)p([0-9]+)", str(param_id))
    if not m:
        raise ValueError(f"BB param_id 파싱 실패: {param_id}")
    return {
        "window": int(m.group(1)),
        "std": float(f"{m.group(2)}.{m.group(3)}"),
    }


def _scanner2_parse_atr_param(param_id: str | None) -> dict | None:
    if param_id is None or str(param_id).lower() == "nan" or str(param_id).strip() == "":
        return None
    m = re.fullmatch(r"atr_p(\d+)_lb(\d+)_q(\d+)_(\d+)", str(param_id))
    if not m:
        raise ValueError(f"ATR param_id 파싱 실패: {param_id}")
    return {
        "period": int(m.group(1)),
        "lookback": int(m.group(2)),
        "lower_q": int(m.group(3)),
        "upper_q": int(m.group(4)),
    }


def _scanner2_compute_index_signal(close: pd.Series, param: dict) -> pd.DataFrame:
    out = pd.DataFrame({"close": pd.to_numeric(close, errors="coerce")}).dropna().sort_index()
    span = int(param["ema_span"])
    if span == 1:
        out["ema"] = out["close"]
    else:
        out["ema"] = out["close"].ewm(span=span, adjust=False, min_periods=max(3, span // 2)).mean()
    out = out.dropna().copy()
    min_periods = max(20, int(param["window"]) // 2)
    out["start_line"] = out["ema"].rolling(int(param["window"]), min_periods=min_periods).quantile(float(param["start_q"]) / 100.0).shift(1)
    out["end_line"] = out["ema"].rolling(int(param["window"]), min_periods=min_periods).quantile(float(param["end_q"]) / 100.0).shift(1)
    out = out.dropna().copy()
    prev_ema = out["ema"].shift(1)
    start_event = (prev_ema >= out["start_line"].shift(1)) & (out["ema"] < out["start_line"])
    end_event = (prev_ema <= out["end_line"].shift(1)) & (out["ema"] > out["end_line"])
    state, starts, ends = _scanner2_state_from_events(start_event.fillna(False), end_event.fillna(False))
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = starts.reindex(out.index).astype(bool)
    out["risk_end_signal"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _scanner2_calculate_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(int(period), min_periods=int(period)).mean()
    loss = (-delta.clip(upper=0.0)).rolling(int(period), min_periods=int(period)).mean()
    rs = gain / (loss + 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def _scanner2_compute_rsi_signal(close: pd.Series, param: dict) -> pd.DataFrame:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    rsi = _scanner2_calculate_rsi(close, int(param["period"]))
    min_periods = max(int(param["lookback"]) // 2, 10)
    lower = rsi.rolling(int(param["lookback"]), min_periods=min_periods).quantile(float(param["lower_q"]) / 100.0)
    upper = rsi.rolling(int(param["lookback"]), min_periods=min_periods).quantile(float(param["upper_q"]) / 100.0)
    out = pd.concat([close.rename("close"), rsi.rename("rsi"), lower.rename("lower_line"), upper.rename("upper_line")], axis=1).dropna()
    start_event = out["rsi"] >= out["upper_line"]
    end_event = out["rsi"] <= out["lower_line"]
    state, starts, ends = _scanner2_state_from_events(start_event, end_event)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = starts.reindex(out.index).astype(bool)
    out["risk_end_signal"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _scanner2_compute_bb_signal(ohlc: pd.DataFrame, param: dict) -> pd.DataFrame:
    out = ohlc[["close", "high", "low"]].apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    middle = out["close"].rolling(int(param["window"]), min_periods=int(param["window"])).mean()
    std = out["close"].rolling(int(param["window"]), min_periods=int(param["window"])).std()
    out["bb_middle"] = middle
    out["bb_upper"] = middle + float(param["std"]) * std
    out["bb_lower"] = middle - float(param["std"]) * std
    out = out.dropna().copy()
    buy_flag = out["low"] <= out["bb_lower"]
    sell_flag = out["high"] >= out["bb_upper"]
    start_event = sell_flag.shift(1, fill_value=False) & (out["high"] < out["bb_upper"])
    end_event = buy_flag.shift(1, fill_value=False) & (out["low"] > out["bb_lower"])
    state, starts, ends = _scanner2_state_from_events(start_event, end_event)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = starts.reindex(out.index).astype(bool)
    out["risk_end_signal"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _scanner2_wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / int(period), adjust=False, min_periods=int(period)).mean()


def _scanner2_compute_atr_signal(ohlc: pd.DataFrame, param: dict | None) -> pd.DataFrame:
    if not param:
        return pd.DataFrame(index=ohlc.index, data={
            "natr": np.nan,
            "start_line": np.nan,
            "end_line": np.nan,
            "risk_state": False,
            "risk_start_signal": False,
            "risk_end_signal": False,
            "valid_signal": False,
        })
    out = ohlc[["close", "high", "low"]].apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    atr = _scanner2_wilder_atr(out["high"], out["low"], out["close"], int(param["period"]))
    natr = 100.0 * atr / out["close"]
    min_periods = max(int(param["lookback"]) // 2, 20)
    start_line = natr.rolling(int(param["lookback"]), min_periods=min_periods).quantile(float(param["upper_q"]) / 100.0).shift(1)
    end_line = natr.rolling(int(param["lookback"]), min_periods=min_periods).quantile(float(param["lower_q"]) / 100.0).shift(1)
    out = pd.concat([natr.rename("natr"), start_line.rename("start_line"), end_line.rename("end_line")], axis=1).dropna()
    prev_natr = out["natr"].shift(1)
    start_event = (out["natr"] >= out["start_line"]) & (prev_natr < out["start_line"].shift(1))
    end_event = (out["natr"] <= out["end_line"]) & (prev_natr > out["end_line"].shift(1))
    state, starts, ends = _scanner2_state_from_events(start_event.fillna(False), end_event.fillna(False))
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = starts.reindex(out.index).astype(bool)
    out["risk_end_signal"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _scanner2_hysteresis_combo(active_count: pd.Series, start_k: int, end_l: int) -> pd.DataFrame:
    states = []
    starts = []
    ends = []
    in_risk = False
    for _, count in active_count.items():
        start_signal = False
        end_signal = False
        if not in_risk and int(count) >= int(start_k):
            in_risk = True
            start_signal = True
        elif in_risk and int(count) <= int(end_l):
            in_risk = False
            end_signal = True
        states.append(in_risk)
        starts.append(start_signal)
        ends.append(end_signal)
    return pd.DataFrame({
        "combo_risk_state": states,
        "combo_start_signal": starts,
        "combo_end_signal": ends,
        "active_count": active_count.astype(int),
    }, index=active_count.index)


def _scanner2_backtest(close: pd.Series, risk_state: pd.Series, years: int = 20) -> dict:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if close.empty:
        return {}
    start_date = close.index.max() - pd.DateOffset(years=years)
    close = close.loc[close.index >= start_date]
    state = risk_state.reindex(close.index).fillna(False).astype(bool)
    ret = close.pct_change().fillna(0.0)
    position = (~state).shift(1, fill_value=True).astype(float)
    strat = (1.0 + ret * position).cumprod()
    bh = (1.0 + ret).cumprod()
    elapsed_years = max((close.index.max() - close.index.min()).days / 365.25, 1e-9)

    def _mdd(s):
        return float((s / s.cummax() - 1.0).min())

    return {
        "start_date": close.index.min().strftime("%Y-%m-%d"),
        "end_date": close.index.max().strftime("%Y-%m-%d"),
        "final_asset": float(strat.iloc[-1]),
        "buyhold_final_asset": float(bh.iloc[-1]),
        "cagr": float(strat.iloc[-1] ** (1.0 / elapsed_years) - 1.0),
        "buyhold_cagr": float(bh.iloc[-1] ** (1.0 / elapsed_years) - 1.0),
        "mdd": _mdd(strat),
        "buyhold_mdd": _mdd(bh),
        "risk_off_share": float(state.mean()),
    }


@st.cache_data(show_spinner=False)
def _build_scanner2_candidate_snapshot(market: str, candidate_id: str):
    manifest = _load_scanner2_preset_manifest()
    market_spec = manifest["markets"][market]
    preset = next(p for p in market_spec["presets"] if p["candidate_id"] == candidate_id)
    ohlc, candidates, saved_daily = _load_scanner2_market_assets(market)
    ohlc = ohlc.rename(columns={c: c.lower() for c in ohlc.columns})
    dates = pd.DatetimeIndex(ohlc.index).normalize()
    close = pd.to_numeric(ohlc["close"], errors="coerce").dropna()
    dates = close.index

    index_frame = _scanner2_align_signal(
        _scanner2_compute_index_signal(close, _scanner2_parse_index_param(preset["index_param_id"])),
        dates,
    )
    rsi_frame_raw = _scanner2_compute_rsi_signal(close, _scanner2_parse_rsi_param(preset["rsi_param_id"]))
    rsi_frame = _scanner2_align_signal(rsi_frame_raw, dates)
    bb_frame_raw = _scanner2_compute_bb_signal(ohlc, _scanner2_parse_bb_param(preset["bb_param_id"]))
    bb_frame = _scanner2_align_signal(bb_frame_raw, dates)
    atr_param = _scanner2_parse_atr_param(preset.get("atr_param_id"))
    atr_frame_raw = _scanner2_compute_atr_signal(ohlc, atr_param)
    atr_frame = _scanner2_align_signal(atr_frame_raw, dates)

    component_frames = {
        "EMA": index_frame,
        "RSI": rsi_frame,
        "BB": bb_frame,
    }
    if atr_param:
        component_frames["ATR"] = atr_frame

    active = sum(frame["risk_state"].astype(int).reindex(dates).fillna(0) for frame in component_frames.values())
    combo = _scanner2_hysteresis_combo(active, int(preset["start_k"]), int(preset["end_l"]))
    saved = saved_daily[saved_daily["candidate_id"].astype(str).eq(candidate_id)].copy()
    saved = saved.set_index("date").sort_index()
    saved_state = saved["risk_state"].astype(bool).reindex(combo.index)
    common = saved_state.dropna().index.intersection(combo.index)
    parity_mismatch = int((saved_state.loc[common].astype(bool).to_numpy() != combo.loc[common, "combo_risk_state"].astype(bool).to_numpy()).sum()) if len(common) else None
    combo["saved_risk_state"] = saved_state.reindex(combo.index).astype("boolean")
    backtest20 = _scanner2_backtest(close, combo["combo_risk_state"], years=20)
    backtest10 = _scanner2_backtest(close, combo["combo_risk_state"], years=10)
    return {
        "manifest": manifest,
        "market_spec": market_spec,
        "preset": preset,
        "ohlc": ohlc,
        "close": close,
        "combo": combo,
        "components": component_frames,
        "component_raw": {
            "EMA": _scanner2_compute_index_signal(close, _scanner2_parse_index_param(preset["index_param_id"])),
            "RSI": rsi_frame_raw,
            "BB": bb_frame_raw,
            "ATR": atr_frame_raw,
        },
        "backtest20": backtest20,
        "backtest10": backtest10,
        "parity": {
            "common_rows": int(len(common)),
            "risk_state_mismatch": parity_mismatch,
        },
    }


def _scanner2_fmt_pct(value, digits=1):
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _scanner2_fmt_num(value, digits=2):
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{digits}f}"


def _scanner2_status_badge(label: str, is_on: bool) -> str:
    cls = "dash-badge-on" if is_on else "dash-badge-off"
    return f'<span class="dash-badge {cls}">{label} {"ON" if is_on else "OFF"}</span>'


def _scanner2_add_risk_shapes(fig: go.Figure, state: pd.Series, row=None, col=None):
    state = state.fillna(False).astype(bool)
    if state.empty:
        return
    start = None
    prev = False
    for dt, val in state.items():
        if val and not prev:
            start = dt
        if prev and not val and start is not None:
            fig.add_vrect(x0=start, x1=dt, fillcolor="rgba(255,75,110,0.11)", line_width=0, row=row, col=col)
            start = None
        prev = val
    if prev and start is not None:
        fig.add_vrect(x0=start, x1=state.index[-1], fillcolor="rgba(255,75,110,0.11)", line_width=0, row=row, col=col)


def _scanner2_chart_layout(fig: go.Figure, height: int = 360):
    fig.update_layout(
        height=height,
        margin=dict(l=28, r=22, t=28, b=28),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#D7D7D7", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def _scanner2_make_main_chart(snapshot: dict, years: int) -> go.Figure:
    close = snapshot["close"]
    combo = snapshot["combo"]
    bb_raw = snapshot["component_raw"]["BB"]
    start_date = close.index.max() - pd.DateOffset(years=years)
    idx = close.loc[close.index >= start_date].index
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=close.reindex(idx), name="지수", line=dict(color="#B7B7B7", width=1.7)))
    for col, name, color, dash in [
        ("bb_middle", "BB 중심", "rgba(216,195,106,0.70)", "solid"),
        ("bb_upper", "BB 상단", "rgba(255,140,105,0.70)", "dot"),
        ("bb_lower", "BB 하단", "rgba(120,220,255,0.72)", "dot"),
    ]:
        if col in bb_raw:
            fig.add_trace(go.Scatter(x=idx, y=bb_raw[col].reindex(idx), name=name, line=dict(color=color, width=1.0, dash=dash)))
    state = combo["combo_risk_state"].reindex(idx).fillna(False)
    _scanner2_add_risk_shapes(fig, state)
    starts = combo.index[combo["combo_start_signal"].astype(bool)]
    ends = combo.index[combo["combo_end_signal"].astype(bool)]
    starts = starts.intersection(idx)
    ends = ends.intersection(idx)
    fig.add_trace(go.Scatter(x=starts, y=close.reindex(starts), mode="markers", name="Risk 시작", marker=dict(symbol="triangle-down", size=11, color="#FF4B6E")))
    fig.add_trace(go.Scatter(x=ends, y=close.reindex(ends), mode="markers", name="Risk 종료", marker=dict(symbol="triangle-up", size=11, color="#4F9CFF")))
    return _scanner2_chart_layout(fig, height=390)


def _scanner2_make_component_charts(snapshot: dict, years: int) -> dict[str, go.Figure]:
    close = snapshot["close"]
    start_date = close.index.max() - pd.DateOffset(years=years)
    idx = close.loc[close.index >= start_date].index
    out = {}
    ema = snapshot["component_raw"]["EMA"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=close.reindex(idx), name="지수", line=dict(color="#A7A7A7", width=1.4)))
    fig.add_trace(go.Scatter(x=idx, y=ema.get("ema", pd.Series(index=idx)).reindex(idx), name="EMA", line=dict(color="#F7C948", width=1.4)))
    fig.add_trace(go.Scatter(x=idx, y=ema.get("start_line", pd.Series(index=idx)).reindex(idx), name="시작선", line=dict(color="#FF8C69", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=idx, y=ema.get("end_line", pd.Series(index=idx)).reindex(idx), name="종료선", line=dict(color="#4F9CFF", width=1, dash="dot")))
    out["EMA"] = _scanner2_chart_layout(fig, height=300)

    rsi = snapshot["component_raw"]["RSI"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=rsi.get("rsi", pd.Series(index=idx)).reindex(idx), name="RSI", line=dict(color="#B18CFF", width=1.4)))
    fig.add_trace(go.Scatter(x=idx, y=rsi.get("upper_line", pd.Series(index=idx)).reindex(idx), name="시작선", line=dict(color="#FF8C69", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=idx, y=rsi.get("lower_line", pd.Series(index=idx)).reindex(idx), name="종료선", line=dict(color="#4F9CFF", width=1, dash="dot")))
    fig.update_yaxes(range=[0, 100])
    out["RSI"] = _scanner2_chart_layout(fig, height=280)

    atr = snapshot["component_raw"].get("ATR", pd.DataFrame())
    fig = go.Figure()
    if atr is not None and not atr.empty and "natr" in atr and atr["natr"].notna().any():
        fig.add_trace(go.Scatter(x=idx, y=atr["natr"].reindex(idx), name="NATR", line=dict(color="#5EEAD4", width=1.4)))
        fig.add_trace(go.Scatter(x=idx, y=atr.get("start_line", pd.Series(index=idx)).reindex(idx), name="시작선", line=dict(color="#FF8C69", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=idx, y=atr.get("end_line", pd.Series(index=idx)).reindex(idx), name="종료선", line=dict(color="#4F9CFF", width=1, dash="dot")))
    else:
        fig.add_annotation(text="ATR 미사용 후보", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(color="#777"))
    out["ATR"] = _scanner2_chart_layout(fig, height=280)
    return out


def _render_signal_scanner2_section(container, favorites=None):
    with container:
        _render_dashboard_common_ui_css()
        try:
            manifest = _load_scanner2_preset_manifest()
        except Exception as exc:
            st.error(f"신호스캐너2 자산 로딩 실패: {exc}")
            return

        st.markdown("<div class='dash-muted'>시장별 Stage03F 추천 후보 중 사용자가 확정한 5개 프리셋을 검토용으로 표시합니다. 운영 확정 모델은 아닙니다.</div>", unsafe_allow_html=True)
        market_options = list(manifest["markets"].keys())
        market = st.radio(
            "시장",
            market_options,
            format_func=lambda m: manifest["markets"][m]["label"],
            horizontal=True,
            label_visibility="collapsed",
            key="scanner2_market",
        )
        presets = manifest["markets"][market]["presets"]
        preset = st.selectbox(
            "Final5 조합 프리셋",
            presets,
            format_func=lambda p: f"{p['label']} · {p['index_param_id'].replace('idx_', '')} / {p['rsi_param_id'].replace('rsi_', '')} / {p['bb_param_id'].replace('bb_', '')} / {p.get('atr_param_id') or 'ATR 없음'} · K{p['start_k']}/L{p['end_l']}",
            label_visibility="collapsed",
            key=f"scanner2_preset_{market}",
        )

        with st.spinner("신호스캐너2 프리셋 계산 중..."):
            snapshot = _build_scanner2_candidate_snapshot(market, preset["candidate_id"])

        combo = snapshot["combo"]
        close = snapshot["close"]
        latest_date = combo.index.max()
        latest = combo.loc[latest_date]
        state = combo["combo_risk_state"].astype(bool)
        current_state = bool(latest["combo_risk_state"])
        start_idx = len(state) - 1
        while start_idx > 0 and bool(state.iloc[start_idx - 1]) == current_state:
            start_idx -= 1
        cycle_start = state.index[start_idx]
        duration = int(len(state.iloc[start_idx:]))
        comp_latest = {name: frame.reindex(combo.index).loc[latest_date] for name, frame in snapshot["components"].items()}
        active_components = [name for name, row in comp_latest.items() if bool(row.get("risk_state", False))]
        component_count = len(snapshot["components"])
        active_count = int(latest["active_count"])
        start_met = active_count >= int(preset["start_k"])
        end_met = active_count <= int(preset["end_l"])
        action = "신규 시작 신호" if bool(latest["combo_start_signal"]) else "신규 종료 신호" if bool(latest["combo_end_signal"]) else "신규 시작/종료 신호 없음"

        st.markdown("<div class='dash-section-title'>현재 신호 상태 요약</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='dash-card-grid'>"
            f"<div class='dash-card'><div class='dash-card-label'>기준일</div><div class='dash-card-value'>{latest_date.strftime('%Y-%m-%d')}</div><div class='dash-card-note'>공통 산출물 마지막 거래일</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>시작 조건</div><div class='dash-card-value'>{active_count} / {component_count} ON</div><div class='dash-card-note'>K{preset['start_k']} 이상이면 시작 · {'충족' if start_met else '미충족'}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>종료 조건</div><div class='dash-card-value'>{active_count} / {component_count} ON</div><div class='dash-card-note'>L{preset['end_l']} 이하이면 종료 · {'충족' if end_met else '미충족'}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>상태</div><div class='dash-card-value'>{'리스크 사이클 ON' if current_state else '리스크 사이클 OFF'}</div><div class='dash-card-note'>현재 상태 시작일 {cycle_start.strftime('%Y-%m-%d')} · 지속 거래일 {duration}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>실행 안내</div><div class='dash-card-value' style='font-size:15px'>{action}</div><div class='dash-card-note'>활성 지표: {', '.join(active_components) if active_components else '없음'}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>저장 신호 parity</div><div class='dash-card-value'>{snapshot['parity']['risk_state_mismatch']}</div><div class='dash-card-note'>공통 {snapshot['parity']['common_rows']:,}행 mismatch</div></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='dash-section-title'>지표별 현재 상태</div>", unsafe_allow_html=True)
        badges = []
        for name in ["EMA", "RSI", "BB", "ATR"]:
            if name in comp_latest:
                badges.append(_scanner2_status_badge(name, bool(comp_latest[name].get("risk_state", False))))
            elif name == "ATR":
                badges.append('<span class="dash-badge dash-badge-off">ATR 미사용</span>')
        st.markdown("".join(badges), unsafe_allow_html=True)

        comp_cols = st.columns(4)
        component_notes = {
            "EMA": preset["index_param_id"],
            "RSI": preset["rsi_param_id"],
            "BB": preset["bb_param_id"],
            "ATR": preset.get("atr_param_id") or "ATR 없음",
        }
        for i, name in enumerate(["EMA", "RSI", "BB", "ATR"]):
            with comp_cols[i]:
                row = comp_latest.get(name)
                if row is None:
                    st.metric(name, "미사용")
                    st.caption(component_notes[name])
                else:
                    st.metric(name, "ON" if bool(row.get("risk_state", False)) else "OFF")
                    st.caption(component_notes[name])

        if favorites:
            with st.expander(f"📋 🇰🇷 한국 즐겨찾기 현황 ({len(favorites)}개)", expanded=False):
                fav_df = pd.DataFrame(favorites)
                if not fav_df.empty:
                    st.dataframe(fav_df.rename(columns={"code": "코드", "name": "이름"}), width="stretch", hide_index=True)

        st.markdown("<div class='dash-section-title'>대표 차트: 지수 + BB + 최종 Risk 신호</div>", unsafe_allow_html=True)
        years = st.radio("표시 기간", [3, 5, 10, 20], index=1, horizontal=True, format_func=lambda x: f"{x}년", label_visibility="collapsed", key="scanner2_chart_years")
        st.plotly_chart(_scanner2_make_main_chart(snapshot, years), width="stretch", config={"displayModeBar": False})
        st.caption("BB 선은 선택 후보의 BB 파라미터 기준이고, 음영과 마커는 4지표 K/L 최종 조합 신호 기준입니다.")

        st.markdown("<div class='dash-section-title'>세부 지표 차트</div>", unsafe_allow_html=True)
        charts = _scanner2_make_component_charts(snapshot, years)
        st.plotly_chart(charts["EMA"], width="stretch", config={"displayModeBar": False})
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(charts["RSI"], width="stretch", config={"displayModeBar": False})
        with c2:
            st.plotly_chart(charts["ATR"], width="stretch", config={"displayModeBar": False})

        st.markdown("<div class='dash-section-title'>백테스트 비교 보기</div>", unsafe_allow_html=True)
        tabs = st.tabs([f"{manifest['markets'][m]['label']}" for m in market_options])
        for tab, m in zip(tabs, market_options):
            with tab:
                rows = []
                for p in manifest["markets"][m]["presets"]:
                    metrics = p.get("metrics", {})
                    rows.append({
                        "프리셋": p["label"],
                        "후보 ID": p["candidate_id"],
                        "K/L": f"K{p['start_k']}/L{p['end_l']}",
                        "20Y CAGR": _scanner2_fmt_pct(metrics.get("cagr_20y"), 2),
                        "B&H 20Y CAGR": _scanner2_fmt_pct(metrics.get("buyhold_cagr_20y"), 2),
                        "20Y MDD": _scanner2_fmt_pct(metrics.get("total_mdd_20y"), 1),
                        "B&H MDD": _scanner2_fmt_pct(metrics.get("buyhold_mdd_20y"), 1),
                        "Risk-off": _scanner2_fmt_pct(metrics.get("risk_off_share_20y"), 1),
                        "사이클": int(metrics.get("cycle_count_20y") or 0),
                    })
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        with st.expander("📖 신호 해석 가이드", expanded=False):
            st.markdown("""
            **신호스캐너2 기준**
            - 각 후보는 EMA, RSI, BB, ATR 중 지정된 지표들의 Risk 상태를 먼저 계산합니다.
            - `K`개 이상 지표가 Risk ON이면 최종 리스크 사이클이 시작됩니다.
            - 리스크 사이클 중 ON 지표 수가 `L`개 이하로 내려가면 최종 리스크 사이클이 종료됩니다.
            - 대표 차트의 BB는 선택 후보의 BB 조건이고, 음영은 BB 단독이 아니라 최종 K/L 조합 신호입니다.
            - 현재 후보들은 연구 산출물 기반 검토용 프리셋이며, 사용자 승인 전 운영 확정 모델이 아닙니다.
            """)


def _scanner3_ohlcv_from_batch(code: str, closes: pd.DataFrame, highs: pd.DataFrame, lows: pd.DataFrame, require_high_low: bool = False) -> pd.DataFrame:
    if closes is None or closes.empty or code not in closes.columns:
        return pd.DataFrame()
    has_high = highs is not None and code in highs.columns and not highs[code].dropna().empty
    has_low = lows is not None and code in lows.columns and not lows[code].dropna().empty
    if require_high_low and (not has_high or not has_low):
        return pd.DataFrame()
    out = pd.DataFrame({
        "close": pd.to_numeric(closes[code], errors="coerce"),
        "high": pd.to_numeric(highs[code], errors="coerce") if has_high else pd.to_numeric(closes[code], errors="coerce"),
        "low": pd.to_numeric(lows[code], errors="coerce") if has_low else pd.to_numeric(closes[code], errors="coerce"),
    }).dropna(subset=["close"]).sort_index()
    return _scanner3_prepare_ohlc_index(out)


def _scanner3_is_intraday_interval(interval: str | None) -> bool:
    return str(interval or "") in {"5m", "15m", "30m", "60m"}


def _scanner3_index_has_intraday_time(index) -> bool:
    idx = pd.DatetimeIndex(_strip_tz(index))
    return bool(((idx.hour != 0) | (idx.minute != 0) | (idx.second != 0)).any())


def _scanner3_prepare_ohlc_index(ohlc: pd.DataFrame) -> pd.DataFrame:
    out = ohlc.copy()
    rename_map = {
        col: str(col).strip().lower().replace(" ", "_")
        for col in out.columns
    }
    out = out.rename(columns=rename_map)
    if "adj_close" in out.columns and "close" not in out.columns:
        out["close"] = out["adj_close"]
    idx = pd.DatetimeIndex(_strip_tz(out.index))
    if not _scanner3_index_has_intraday_time(idx):
        idx = idx.normalize()
    out.index = idx
    out = out.sort_index()
    return out.loc[~out.index.duplicated(keep="last")]


def _scanner3_align_signal(signal: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    dates = pd.DatetimeIndex(_strip_tz(dates))
    if not _scanner3_index_has_intraday_time(dates):
        dates = dates.normalize()
    dates = dates.drop_duplicates().sort_values()
    if signal is None or signal.empty:
        return pd.DataFrame(index=dates, data={
            "risk_state": False,
            "risk_start_signal": False,
            "risk_end_signal": False,
            "valid_signal": False,
        })
    source = signal.copy()
    source.index = pd.DatetimeIndex(_strip_tz(source.index))
    if not _scanner3_index_has_intraday_time(dates):
        source.index = source.index.normalize()
    source = source.sort_index().loc[~source.index.duplicated(keep="last")]
    union = source.index.union(dates).sort_values()
    state = source["risk_state"].astype(bool).reindex(union).ffill().fillna(False).reindex(dates).fillna(False)
    prev = state.shift(1, fill_value=False)
    valid_source = source.get("valid_signal", pd.Series(True, index=source.index)).astype(bool)
    valid_dates = source.index[valid_source]
    first_valid = valid_dates.min() if len(valid_dates) else dates.max()
    return pd.DataFrame({
        "risk_state": state.astype(bool),
        "risk_start_signal": (state & ~prev).astype(bool),
        "risk_end_signal": (~state & prev).astype(bool),
        "valid_signal": pd.Series(dates >= first_valid, index=dates, dtype=bool),
    }, index=dates)


def _scanner3_required_bars(preset: dict) -> int:
    try:
        idx_param = _scanner2_parse_index_param(preset["index_param_id"])
        rsi_param = _scanner2_parse_rsi_param(preset["rsi_param_id"])
        bb_param = _scanner2_parse_bb_param(preset["bb_param_id"])
        atr_param = _scanner2_parse_atr_param(preset.get("atr_param_id"))
        needs = [
            int(idx_param["window"]) + int(idx_param["ema_span"]),
            int(rsi_param["period"]) + int(rsi_param["lookback"]),
            int(bb_param["window"]),
        ]
        if atr_param:
            needs.append(int(atr_param["period"]) + int(atr_param["lookback"]))
        return int(max(needs) + 15)
    except Exception:
        return 120


def _scanner3_display_bar_count(period_days: int, chart_mode: str = "일봉", interval: str | None = None) -> int:
    if chart_mode == "분봉":
        bars_per_day = {"5m": 78, "15m": 26, "30m": 13, "60m": 7}
        return max(1, int(period_days) * bars_per_day.get(str(interval or ""), 78))
    if chart_mode == "주봉":
        return max(1, round(int(period_days) / 5))
    if chart_mode == "월봉":
        return max(1, round(int(period_days) / 21))
    return max(1, int(period_days))


def _scanner3_request_start_date(period_days: int, chart_mode: str, interval: str | None, preset: dict) -> str:
    today = datetime.now().date()
    display_bars = _scanner3_display_bar_count(period_days, chart_mode=chart_mode, interval=interval)
    required_bars = _scanner3_required_bars(preset)
    total_bars = display_bars + required_bars + 20
    if chart_mode == "월봉":
        calendar_days = total_bars * 35
    elif chart_mode == "주봉":
        calendar_days = total_bars * 8
    elif chart_mode == "분봉":
        calendar_days = max(int(period_days) + 120, 180)
    else:
        calendar_days = total_bars * 2
    return str(today - timedelta(days=int(calendar_days)))


def _scanner3_compute_from_ohlcv(ohlc: pd.DataFrame, preset: dict) -> dict | None:
    if ohlc is None or ohlc.empty:
        return None
    ohlc = _scanner3_prepare_ohlc_index(ohlc)
    if "close" not in ohlc:
        return None
    for col in ["close", "high", "low"]:
        if col not in ohlc:
            return None
        ohlc[col] = pd.to_numeric(ohlc[col], errors="coerce")
    ohlc = ohlc.dropna(subset=["close", "high", "low"])
    if len(ohlc) < _scanner3_required_bars(preset):
        return None
    close = ohlc["close"].dropna()
    dates = close.index
    rsi_raw = _scanner2_compute_rsi_signal(close, _scanner2_parse_rsi_param(preset["rsi_param_id"]))
    index_frame = _scanner3_align_signal(
        _scanner2_compute_index_signal(close, _scanner2_parse_index_param(preset["index_param_id"])),
        dates,
    )
    rsi_frame = _scanner3_align_signal(rsi_raw, dates)
    bb_raw = _scanner2_compute_bb_signal(ohlc, _scanner2_parse_bb_param(preset["bb_param_id"]))
    bb_frame = _scanner3_align_signal(bb_raw, dates)
    atr_param = _scanner2_parse_atr_param(preset.get("atr_param_id"))
    atr_raw = _scanner2_compute_atr_signal(ohlc, atr_param)
    atr_frame = _scanner3_align_signal(atr_raw, dates)
    components = {"EMA": index_frame, "RSI": rsi_frame, "BB": bb_frame}
    raw = {"EMA": _scanner2_compute_index_signal(close, _scanner2_parse_index_param(preset["index_param_id"])), "RSI": rsi_raw, "BB": bb_raw, "ATR": atr_raw}
    if atr_param:
        components["ATR"] = atr_frame
    active = sum(frame["risk_state"].astype(int).reindex(dates).fillna(0) for frame in components.values())
    combo = _scanner2_hysteresis_combo(active, int(preset["start_k"]), int(preset["end_l"]))
    backtest20 = _scanner2_backtest(close, combo["combo_risk_state"], years=20)
    backtest10 = _scanner2_backtest(close, combo["combo_risk_state"], years=10)
    return {
        "ohlc": ohlc,
        "close": close,
        "combo": combo,
        "components": components,
        "component_raw": raw,
        "backtest20": backtest20,
        "backtest10": backtest10,
    }


def _scanner3_cycle_meta(combo: pd.DataFrame) -> dict:
    if combo is None or combo.empty:
        return {
            "latest_date": None,
            "risk_state": False,
            "active_count": 0,
            "start_signal": False,
            "end_signal": False,
            "cycle_start": None,
            "duration": 0,
        }
    latest_date = combo.index.max()
    latest = combo.loc[latest_date]
    state = combo["combo_risk_state"].fillna(False).astype(bool)
    current_state = bool(latest["combo_risk_state"])
    start_idx = len(state) - 1
    while start_idx > 0 and bool(state.iloc[start_idx - 1]) == current_state:
        start_idx -= 1
    return {
        "latest_date": latest_date,
        "risk_state": current_state,
        "active_count": int(latest["active_count"]),
        "start_signal": bool(latest["combo_start_signal"]),
        "end_signal": bool(latest["combo_end_signal"]),
        "cycle_start": state.index[start_idx],
        "duration": int(len(state.iloc[start_idx:])),
    }


def _scanner3_adapt_to_scanner1_signal_row(code: str, name: str, snap: dict | None, preset: dict) -> dict:
    row = _empty_signal_row(code, name)
    if snap is None:
        return row
    close = snap.get("close", pd.Series(dtype=float)).dropna()
    if len(close) >= 2:
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        row["close"] = last
        row["pct_change"] = (last / prev - 1) * 100 if prev else 0.0
        rsi_display = calculate_rsi(close, 14).dropna()
        if not rsi_display.empty:
            row["rsi"] = float(rsi_display.iloc[-1])
    meta = _scanner3_cycle_meta(snap.get("combo", pd.DataFrame()))
    if meta["latest_date"] is None:
        return row
    start_k = int(preset.get("start_k", 1))
    end_l = int(preset.get("end_l", 0))
    active_count = int(meta.get("active_count", 0))
    risk_state = bool(meta.get("risk_state", False))
    start_signal = bool(meta.get("start_signal", False))
    end_signal = bool(meta.get("end_signal", False))

    row["dyn_buy_signal"] = end_signal
    row["dyn_sell_signal"] = start_signal
    row["dyn_holding"] = (not risk_state) and not start_signal and not end_signal
    row["dyn_buy_flag"] = risk_state and (not end_signal) and active_count <= end_l + 1
    row["dyn_sell_flag"] = (not risk_state) and (not start_signal) and active_count >= max(1, start_k - 1)
    row["scanner3_latest_date"] = meta["latest_date"]
    row["scanner3_active_count"] = active_count
    row["scanner3_component_count"] = len(snap.get("components", {}))
    row["scanner3_cycle_start"] = meta.get("cycle_start")
    row["scanner3_cycle_duration"] = meta.get("duration")
    return row


def _scanner3_price_only_signal_row(code: str, name: str, ohlc: pd.DataFrame | None) -> dict:
    row = _empty_signal_row(code, name)
    if ohlc is None or ohlc.empty:
        return row
    prepared = _scanner3_prepare_ohlc_index(ohlc)
    if "close" not in prepared:
        return row
    close = pd.to_numeric(prepared["close"], errors="coerce").dropna().sort_index()
    if len(close) >= 1:
        row["close"] = float(close.iloc[-1])
    if len(close) >= 2:
        prev = float(close.iloc[-2])
        row["pct_change"] = (float(close.iloc[-1]) / prev - 1.0) * 100 if prev else 0.0
        rsi_display = calculate_rsi(close, 14).dropna()
        if not rsi_display.empty:
            row["rsi"] = float(rsi_display.iloc[-1])
    return row


@st.cache_data(ttl=180, show_spinner=False)
def _scanner3_build_rows(items_tuple, preset: dict, start_str: str, end_str: str, interval: str = "1d"):
    items = [{"code": code, "name": name} for code, name in items_tuple]
    tickers = tuple(item["code"] for item in items)
    if _scanner3_is_intraday_interval(interval):
        closes = _fetch_intraday_batch_guarded(tickers, interval, "분봉", "scanner3_watchlist_batch")
        highs = lows = pd.DataFrame()
        if closes is None:
            closes = pd.DataFrame()
    else:
        closes, highs, lows = fetch_ohlcv_batch(tickers, start_str, end_str, interval=interval)
    rows = []
    for item in items:
        code = item["code"]
        snap = None
        price_ohlc = pd.DataFrame()
        try:
            if _scanner3_is_intraday_interval(interval):
                single, _err = _fetch_intraday_guarded(code, interval, "분봉", "scanner3_watchlist_ohlc")
                if single is not None and not single.empty and {"Open", "High", "Low", "Close"}.issubset(single.columns):
                    price_ohlc = single
                    snap = _scanner3_compute_from_ohlcv(single, preset)
                elif closes is not None and code in closes.columns:
                    price_ohlc = pd.DataFrame({"close": pd.to_numeric(closes[code], errors="coerce")}).dropna()
            else:
                price_ohlc = _scanner3_ohlcv_from_batch(code, closes, highs, lows)
                snap = _scanner3_compute_from_ohlcv(price_ohlc, preset)
        except Exception:
            snap = None
        row = _scanner3_adapt_to_scanner1_signal_row(code, item["name"], snap, preset)
        if snap is None:
            row = _scanner3_price_only_signal_row(code, item["name"], price_ohlc)
        rows.append(row)
    rows.sort(key=_signal_row_sort_key)
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def _scanner3_build_multitimeframe_signal_maps(items_tuple, preset: dict, data_end: str):
    tf_specs = [
        ("일봉", "1d", 63, "일봉"),
        ("주봉", "1wk", 504, "주봉"),
        ("월봉", "1mo", 2520, "월봉"),
    ]
    tf_maps = {}
    for tf_label, tf_interval, tf_days, tf_mode in tf_specs:
        tf_start = _scanner3_request_start_date(tf_days, tf_mode, tf_interval, preset)
        tf_rows = _scanner3_build_rows(items_tuple, preset, tf_start, data_end, tf_interval)
        tf_maps[tf_label] = {row["code"]: row for row in tf_rows}
    return tf_maps


@st.cache_data(ttl=180, show_spinner=False)
def _scanner3_build_ticker_snapshot(code: str, preset: dict, start_str: str, end_str: str, interval: str = "1d"):
    ohlcv, _err = _scanner3_fetch_ticker_ohlcv(code, start_str, end_str, interval)
    if ohlcv is None or ohlcv.empty:
        return None
    lower = ohlcv.rename(columns={c: c.lower() for c in ohlcv.columns})
    return _scanner3_compute_from_ohlcv(lower, preset)


def _scanner3_fetch_ticker_ohlcv(code: str, start_str: str, end_str: str, interval: str = "1d"):
    if _scanner3_is_intraday_interval(interval):
        return _fetch_intraday_guarded(code, interval, "분봉", "scanner3_detail_chart")
    return fetch_ohlcv(code, start_str, end_str, interval=interval), None


def _scanner3_display_index(close: pd.Series, period_days: int, chart_mode: str = "일봉", interval: str | None = None) -> pd.Index:
    close = close.dropna().sort_index()
    if close.empty:
        return close.index
    display_bars = _scanner3_display_bar_count(period_days, chart_mode=chart_mode, interval=interval)
    return close.index[-min(len(close), display_bars):]


def _scanner3_series(raw: pd.DataFrame, column: str, idx: pd.Index) -> pd.Series:
    if raw is None or raw.empty or column not in raw:
        return pd.Series(np.nan, index=idx)
    return pd.to_numeric(raw[column], errors="coerce").reindex(idx)


def _scanner3_make_detail_chart(
    snapshot: dict,
    name: str,
    period_days: int,
    preset: dict,
    chart_mode: str = "일봉",
    interval: str | None = None,
    intraday_session=None,
) -> go.Figure | None:
    if snapshot is None or snapshot.get("close") is None:
        return None
    close = pd.to_numeric(snapshot["close"], errors="coerce").dropna().sort_index()
    if close.empty:
        return None
    idx = _scanner3_display_index(close, period_days, chart_mode=chart_mode, interval=interval)
    if len(idx) < 1:
        return None

    combo = snapshot.get("combo", pd.DataFrame()).reindex(close.index)
    state = combo.get("combo_risk_state", pd.Series(False, index=close.index)).reindex(idx).fillna(False).astype(bool)
    starts = combo.index[combo.get("combo_start_signal", pd.Series(False, index=combo.index)).fillna(False).astype(bool)].intersection(idx)
    ends = combo.index[combo.get("combo_end_signal", pd.Series(False, index=combo.index)).fillna(False).astype(bool)].intersection(idx)
    holding = close.reindex(idx).where(state)

    raw = snapshot.get("component_raw", {})
    bb = raw.get("BB", pd.DataFrame())
    ema = raw.get("EMA", pd.DataFrame())
    rsi = raw.get("RSI", pd.DataFrame())
    atr = raw.get("ATR", pd.DataFrame())

    bb_window = _scanner2_parse_bb_param(preset.get("bb_param_id", "bb_w20_std2p0")).get("window", "BB")
    rsi_param = _scanner2_parse_rsi_param(preset.get("rsi_param_id", "rsi_p14_lb80_q10_90"))
    atr_param = _scanner2_parse_atr_param(preset.get("atr_param_id"))
    atr_title = (
        f"NATR ({atr_param['period']}d, {atr_param['lookback']}d)"
        if atr_param else
        "ATR 미사용 프리셋"
    )

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.52, 0.24, 0.24],
        shared_xaxes=False,
        vertical_spacing=0.08,
        subplot_titles=[
            "",
            f"RSI ({rsi_param['period']}d, {rsi_param['lookback']}d)",
            atr_title,
        ],
    )

    bb_upper = _scanner3_series(bb, "bb_upper", idx)
    bb_lower = _scanner3_series(bb, "bb_lower", idx)
    bb_middle = _scanner3_series(bb, "bb_middle", idx)
    ema_line = _scanner3_series(ema, "ema", idx)

    fig.add_trace(go.Scatter(x=idx, y=bb_upper, line=dict(color="rgba(120,126,231,0.20)", width=1), showlegend=False, hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=bb_lower, line=dict(color="rgba(120,126,231,0.20)", width=1), fill="tonexty", fillcolor="rgba(120,126,231,0.04)", showlegend=False, hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=close.reindex(idx), name=name, line=dict(color="#EDEDED", width=1.5), hovertemplate="가격: %{y:,.0f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=holding, name="★ 리스크 사이클", line=dict(color="#C8C850", width=1.5), connectgaps=False, hoverinfo="skip"), row=1, col=1)
    if ema_line.notna().any():
        fig.add_trace(go.Scatter(x=idx, y=ema_line, name="EMA", line=dict(color="rgba(247,201,72,0.70)", width=1.0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=bb_middle, name=f"BB 중심 ({bb_window})", line=dict(color="rgba(216,195,106,0.70)", width=1.0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=bb_upper, name="BB 상단", line=dict(color="rgba(255,140,105,0.70)", width=1.0, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=bb_lower, name="BB 하단", line=dict(color="rgba(120,220,255,0.72)", width=1.0, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=starts, y=close.reindex(starts), mode="markers", name="Risk 시작", marker=dict(symbol="triangle-down", size=11, color="#FF4B6E")), row=1, col=1)
    fig.add_trace(go.Scatter(x=ends, y=close.reindex(ends), mode="markers", name="Risk 종료", marker=dict(symbol="triangle-up", size=11, color="#4F9CFF")), row=1, col=1)
    _scanner2_add_risk_shapes(fig, state, row=1, col=1)

    rsi_line = _scanner3_series(rsi, "rsi", idx)
    rsi_upper = _scanner3_series(rsi, "upper_line", idx)
    rsi_lower = _scanner3_series(rsi, "lower_line", idx)
    fig.add_trace(go.Scatter(x=idx, y=rsi_upper, line=dict(color="rgba(255,215,0,0.20)", width=1), showlegend=False, hoverinfo="skip"), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=rsi_lower, line=dict(color="rgba(75,255,179,0.20)", width=1), fill="tonexty", fillcolor="rgba(255,255,255,0.02)", showlegend=False, hoverinfo="skip"), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=rsi_line, name="RSI", line=dict(color="#787EE7", width=1.5), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=rsi_upper, name="RSI 시작선", line=dict(color="#FFD700", width=1, dash="dash"), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=rsi_lower, name="RSI 종료선", line=dict(color="#4BFFB3", width=1, dash="dash"), showlegend=False), row=2, col=1)
    if len(starts) > 0:
        fig.add_trace(go.Scatter(x=starts, y=rsi_line.reindex(starts), mode="markers", marker=dict(symbol="triangle-down", color="#FF4B6E", size=8), showlegend=False, hoverinfo="skip"), row=2, col=1)
    if len(ends) > 0:
        fig.add_trace(go.Scatter(x=ends, y=rsi_line.reindex(ends), mode="markers", marker=dict(symbol="triangle-up", color="#4F9CFF", size=8), showlegend=False, hoverinfo="skip"), row=2, col=1)
    fig.add_hline(y=50, line_color="rgba(255,255,255,0.08)", line_width=0.7, line_dash="dot", row=2, col=1)

    natr = _scanner3_series(atr, "natr", idx)
    atr_start = _scanner3_series(atr, "start_line", idx)
    atr_end = _scanner3_series(atr, "end_line", idx)
    if natr.notna().any():
        fig.add_trace(go.Scatter(x=idx, y=natr, name="NATR", line=dict(color="#5EEAD4", width=1.5), showlegend=False), row=3, col=1)
        fig.add_trace(go.Scatter(x=idx, y=atr_start, name="ATR 시작선", line=dict(color="#FFD700", width=1, dash="dash"), showlegend=False), row=3, col=1)
        fig.add_trace(go.Scatter(x=idx, y=atr_end, name="ATR 종료선", line=dict(color="#4BFFB3", width=1, dash="dash"), showlegend=False), row=3, col=1)
        if len(starts) > 0:
            fig.add_trace(go.Scatter(x=starts, y=natr.reindex(starts), mode="markers", marker=dict(symbol="triangle-down", color="#FF4B6E", size=8), showlegend=False, hoverinfo="skip"), row=3, col=1)
        if len(ends) > 0:
            fig.add_trace(go.Scatter(x=ends, y=natr.reindex(ends), mode="markers", marker=dict(symbol="triangle-up", color="#4F9CFF", size=8), showlegend=False, hoverinfo="skip"), row=3, col=1)
    else:
        fig.add_annotation(text="이 프리셋은 ATR을 사용하지 않습니다.", x=0.5, y=0.5, xref="x3 domain", yref="y3 domain", showarrow=False, font=dict(color="#777", size=11))

    fig.update_layout(
        height=900,
        title=dict(text=f"<b>{name}</b>", font=dict(size=14, color="#EDEDED"), x=0, y=0.99, yanchor="top"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=10), bgcolor="rgba(0,0,0,0)", traceorder="normal"),
        **_base_layout(margin=dict(l=10, r=10, t=150, b=10)),
    )
    fig.update_xaxes(**_axis_kw())
    fig.update_yaxes(**_axis_kw())
    fig.update_xaxes(matches="x")
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(tickangle=0, row=1, col=1)
    fig.update_xaxes(tickangle=0, row=3, col=1)
    fig.update_yaxes(range=[0, 100], dtick=20, row=2, col=1)
    if intraday_session is not None:
        close_h, open_h = intraday_session
        _rb = [
            dict(bounds=["sat", "mon"]),
            dict(bounds=[close_h, open_h], pattern="hour"),
        ]
        for _r in [1, 2, 3]:
            fig.update_xaxes(rangebreaks=_rb, row=_r, col=1)
    return fig


def _scanner3_make_price_only_chart(ohlc: pd.DataFrame, name: str, period_days: int, chart_mode: str = "일봉", interval: str | None = None, intraday_session=None) -> go.Figure | None:
    if ohlc is None or ohlc.empty:
        return None
    lower = ohlc.rename(columns={c: c.lower() for c in ohlc.columns})
    if "close" not in lower:
        return None
    prepared = _scanner3_prepare_ohlc_index(lower)
    close = pd.to_numeric(prepared["close"], errors="coerce").dropna().sort_index()
    if len(close) < 3:
        return None
    idx = _scanner3_display_index(close, period_days, chart_mode=chart_mode, interval=interval)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=idx,
        y=close.reindex(idx),
        line=dict(color="#787EE7", width=1.7),
        name=name,
        showlegend=False,
    ))
    fig.update_layout(
        height=320,
        title=dict(text=f"{name} · 가격만 표시", font=dict(size=13, color="#9B9B9B")),
        **_base_layout(),
    )
    fig.update_xaxes(**_axis_kw())
    fig.update_yaxes(**_axis_kw())
    if intraday_session is not None:
        close_h, open_h = intraday_session
        fig.update_xaxes(rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(bounds=[close_h, open_h], pattern="hour"),
        ])
    return fig


def _scanner3_all_final_presets(manifest: dict) -> list[dict]:
    presets = []
    for market_key, market_info in manifest.get("markets", {}).items():
        market_label = market_info.get("label", market_key)
        for preset in market_info.get("presets", []):
            item = dict(preset)
            item["_market_key"] = market_key
            item["_market_label"] = market_label
            presets.append(item)
    return presets


def _scanner3_first_valid_date(snapshot: dict | None) -> pd.Timestamp | None:
    if snapshot is None or snapshot.get("close") is None:
        return None
    close = pd.to_numeric(snapshot["close"], errors="coerce").dropna()
    if close.empty:
        return None
    valid = pd.Series(True, index=close.index)
    for frame in snapshot.get("components", {}).values():
        if frame is None or frame.empty or "valid_signal" not in frame:
            return None
        valid &= frame["valid_signal"].reindex(close.index).fillna(False).astype(bool)
    valid_dates = valid.index[valid]
    return valid_dates.min() if len(valid_dates) else None


def _scanner3_cycle_count_for_window(risk_state: pd.Series) -> int:
    if risk_state is None or risk_state.empty:
        return 0
    state = risk_state.fillna(False).astype(bool)
    starts = state & ~state.shift(1, fill_value=False)
    return int(starts.sum())


def _scanner3_backtest_common_window(close: pd.Series, risk_state: pd.Series, start_date, end_date) -> dict:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if close.empty:
        return {}
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    close = close.loc[(close.index >= start) & (close.index <= end)]
    if len(close) < 3:
        return {}
    state = risk_state.reindex(close.index).fillna(False).astype(bool)
    ret = close.pct_change().fillna(0.0)
    position = (~state).shift(1, fill_value=True).astype(float)
    strat = (1.0 + ret * position).cumprod()
    bh = (1.0 + ret).cumprod()
    elapsed_years = max((close.index.max() - close.index.min()).days / 365.25, 1e-9)

    def _mdd(series):
        return float((series / series.cummax() - 1.0).min())

    return {
        "start_date": close.index.min(),
        "end_date": close.index.max(),
        "years": elapsed_years,
        "cagr": float(strat.iloc[-1] ** (1.0 / elapsed_years) - 1.0),
        "mdd": _mdd(strat),
        "buyhold_cagr": float(bh.iloc[-1] ** (1.0 / elapsed_years) - 1.0),
        "buyhold_mdd": _mdd(bh),
        "risk_off_share": float(state.mean()),
        "cycle_count": _scanner3_cycle_count_for_window(state),
        "risk_state": bool(state.iloc[-1]),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _scanner3_compare_presets_for_ticker(ticker: str, years: int, end_str: str, manifest_hash: str) -> dict:
    manifest = _load_scanner2_preset_manifest()
    presets = _scanner3_all_final_presets(manifest)
    if len(presets) != 15:
        return {"error": f"Final 프리셋 수가 15개가 아닙니다: {len(presets)}개", "rows": []}
    max_required = max(_scanner3_required_bars(preset) for preset in presets)
    end_date = pd.Timestamp(end_str).normalize()
    request_days = int(years * 365.25 + max_required * 3 + 90)
    start_str = str((end_date - pd.Timedelta(days=request_days)).date())
    ohlcv = fetch_ohlcv(ticker, start_str, end_str, interval="1d")
    if ohlcv is None or ohlcv.empty:
        return {"error": "선택 종목의 일봉 데이터를 가져올 수 없습니다.", "rows": []}
    ohlc = _scanner3_prepare_ohlc_index(ohlcv)
    if "close" not in ohlc:
        return {"error": "선택 종목 일봉 데이터에 Close 컬럼이 없습니다.", "rows": []}
    close = pd.to_numeric(ohlc["close"], errors="coerce").dropna().sort_index()
    if len(close) < 30:
        return {"error": f"백테스트 비교에 필요한 데이터가 부족합니다: {len(close)}봉", "rows": []}

    target_start = max(close.index.min(), close.index.max() - pd.DateOffset(years=int(years)))
    target_end = close.index.max()
    snapshots = []
    valid_starts = []
    rows = []
    for preset in presets:
        try:
            snap = _scanner3_compute_from_ohlcv(ohlc, preset)
            first_valid = _scanner3_first_valid_date(snap)
            if snap is None or first_valid is None:
                snapshots.append((preset, None))
                rows.append({"preset": preset, "status": "계산 불가", "reason": "warmup 또는 지표 계산 실패"})
                continue
            snapshots.append((preset, snap))
            valid_starts.append(first_valid)
        except Exception as exc:
            snapshots.append((preset, None))
            rows.append({"preset": preset, "status": "계산 불가", "reason": str(exc)[:80]})

    if not valid_starts:
        return {"error": "15개 프리셋 모두 계산할 수 없습니다.", "rows": []}
    common_start = max([pd.Timestamp(target_start)] + [pd.Timestamp(dt) for dt in valid_starts])
    common_end = pd.Timestamp(target_end)
    if common_start >= common_end:
        return {"error": "공통 평가 구간을 만들 수 없습니다.", "rows": []}

    result_rows = []
    for preset, snap in snapshots:
        base = {
            "market": preset.get("_market_label", preset.get("market", "")),
            "preset_key": preset.get("preset_key"),
            "preset_label": preset.get("label", preset.get("preset_key")),
            "kl": f"K{preset.get('start_k')}/L{preset.get('end_l')}",
            "candidate_id": preset.get("candidate_id"),
            "status": "계산 불가",
            "reason": "",
        }
        if snap is None:
            fail = next((row for row in rows if row.get("preset", {}).get("preset_key") == preset.get("preset_key")), {})
            base["reason"] = fail.get("reason", "계산 실패")
            result_rows.append(base)
            continue
        metrics = _scanner3_backtest_common_window(
            snap["close"],
            snap["combo"]["combo_risk_state"],
            common_start,
            common_end,
        )
        if not metrics:
            base["reason"] = "공통 평가 구간 데이터 부족"
            result_rows.append(base)
            continue
        base.update({
            "status": "OK",
            "start_date": metrics["start_date"].strftime("%Y-%m-%d"),
            "end_date": metrics["end_date"].strftime("%Y-%m-%d"),
            "years": metrics["years"],
            "cagr": metrics["cagr"],
            "mdd": metrics["mdd"],
            "buyhold_cagr": metrics["buyhold_cagr"],
            "buyhold_mdd": metrics["buyhold_mdd"],
            "risk_off_share": metrics["risk_off_share"],
            "cycle_count": metrics["cycle_count"],
            "current_state": "Risk ON" if metrics["risk_state"] else "Risk OFF",
        })
        result_rows.append(base)

    ok_rows = sorted([row for row in result_rows if row.get("status") == "OK"], key=lambda row: row.get("cagr", -999), reverse=True)
    ranks = {row["preset_key"]: i + 1 for i, row in enumerate(ok_rows)}
    for row in result_rows:
        row["rank"] = ranks.get(row.get("preset_key"))
    return {
        "rows": result_rows,
        "common_start": common_start.strftime("%Y-%m-%d"),
        "common_end": common_end.strftime("%Y-%m-%d"),
        "manifest_hash": manifest_hash,
    }


def _scanner3_format_backtest_table(result: dict, current_preset_key: str | None) -> pd.DataFrame:
    rows = []
    for row in sorted(result.get("rows", []), key=lambda r: (r.get("rank") is None, r.get("rank") or 999)):
        if row.get("status") != "OK":
            rows.append({
                "순위": "—",
                "시장": row.get("market", ""),
                "프리셋": row.get("preset_label", row.get("preset_key", "")),
                "K/L": row.get("kl", ""),
                "실제 기간": "계산 불가",
                "데이터 연수": "—",
                "전략 CAGR": "계산 불가",
                "전략 MDD": "—",
                "B&H CAGR": "—",
                "B&H MDD": "—",
                "Risk-off 비중": "—",
                "완료 사이클 수": "—",
                "현재 상태": row.get("reason", "계산 불가"),
                "현재 선택 프리셋 여부": "현재" if row.get("preset_key") == current_preset_key else "",
            })
            continue
        rows.append({
            "순위": int(row.get("rank")),
            "시장": row.get("market", ""),
            "프리셋": row.get("preset_label", row.get("preset_key", "")),
            "K/L": row.get("kl", ""),
            "실제 기간": f"{row.get('start_date')} ~ {row.get('end_date')}",
            "데이터 연수": f"{row.get('years', 0):.1f}년",
            "전략 CAGR": _scanner2_fmt_pct(row.get("cagr"), 2),
            "전략 MDD": _scanner2_fmt_pct(row.get("mdd"), 2),
            "B&H CAGR": _scanner2_fmt_pct(row.get("buyhold_cagr"), 2),
            "B&H MDD": _scanner2_fmt_pct(row.get("buyhold_mdd"), 2),
            "Risk-off 비중": _scanner2_fmt_pct(row.get("risk_off_share"), 1),
            "완료 사이클 수": int(row.get("cycle_count") or 0),
            "현재 상태": row.get("current_state", ""),
            "현재 선택 프리셋 여부": "현재" if row.get("preset_key") == current_preset_key else "",
        })
    return pd.DataFrame(rows)


def _scanner3_rows_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.rename(columns={
        "name": "이름",
        "code": "코드",
        "latest_date": "기준일",
        "risk_state": "상태",
        "active": "ON 수",
        "event": "실행 안내",
        "cycle_start": "상태 시작일",
        "duration": "지속 거래일",
        "components": "지표 상태",
    })


def _scanner3_find_preset(manifest: dict, preset_key: str | None) -> tuple[str, dict]:
    markets = manifest.get("markets", {})
    for market_key, market_info in markets.items():
        for preset in market_info.get("presets", []):
            if preset.get("preset_key") == preset_key:
                return market_key, preset
    first_market = next(iter(markets))
    return first_market, markets[first_market]["presets"][0]


def _scanner3_preset_options(manifest: dict) -> list[tuple[str, str]]:
    options = []
    for market_key, market_info in manifest.get("markets", {}).items():
        label = market_info.get("label", market_key)
        for preset in market_info.get("presets", []):
            atr = preset.get("atr_param_id") or "ATR 없음"
            desc = (
                f"{label} · {preset.get('label', preset.get('preset_key'))} · "
                f"K{preset.get('start_k')}/L{preset.get('end_l')} · "
                f"{preset.get('index_param_id', '').replace('idx_', '')} / "
                f"{preset.get('rsi_param_id', '').replace('rsi_', '')} / "
                f"{preset.get('bb_param_id', '').replace('bb_', '')} / "
                f"{atr.replace('atr_', '')}"
            )
            options.append((preset["preset_key"], desc))
    return options


def _render_signal_scanner3_mode(
    container,
    *,
    favorites,
    chart_mode: str,
    yf_interval: str | None,
    higher_interval: str | None = None,
    period_days: int,
    data_start: str,
    data_end: str,
    auto_refresh: bool,
    refresh_ms: int,
):
    with container:
        if auto_refresh and AUTOREFRESH_AVAILABLE:
            st_autorefresh(interval=refresh_ms, key=f"{chart_mode}_scanner3_autorefresh")
        elif auto_refresh and not AUTOREFRESH_AVAILABLE:
            st.warning("⚠️ 자동 새로고침을 사용하려면 `streamlit-autorefresh` 패키지가 필요합니다.")

        try:
            manifest = _load_scanner2_preset_manifest()
        except Exception as exc:
            st.error(f"신호스캐너3 프리셋 로딩 실패: {exc}")
            return

        preset_key = st.session_state.get("scanner3_sidebar_preset_key")
        _, preset = _scanner3_find_preset(manifest, preset_key)
        interval = yf_interval if chart_mode == "분봉" and yf_interval else (higher_interval or "1d")
        data_start = _scanner3_request_start_date(period_days, chart_mode, interval, preset)
        st.caption(
            "신호스캐너3은 신호스캐너1의 종목 조회 흐름을 그대로 쓰고, "
            "선택한 지수 백테스트 프리셋의 EMA·RSI·BB·ATR·K/L 규칙만 각 종목 가격에 다시 계산합니다."
        )

        if not favorites:
            st.markdown("""
            <div style='background:#111113;border:1px solid rgba(255,255,255,0.06);
                        border-radius:10px;padding:40px;text-align:center;margin:24px 0;'>
                <p style='color:#555;font-size:14px;margin:0;'>
                    왼쪽 사이드바에서 종목을 검색해서 즐겨찾기에 추가해주세요.
                </p>
            </div>""", unsafe_allow_html=True)
            return

        with st.spinner("📡 프리셋 기반 종목 신호 계산..."):
            kr_rows = _scanner3_build_rows(
                tuple((item["code"], item["name"]) for item in favorites),
                preset,
                data_start,
                data_end,
                interval,
            )
            us_rows = _scanner3_build_rows(
                tuple((item["code"], item["name"]) for item in US_WATCHLIST),
                preset,
                data_start,
                data_end,
                interval,
            )
            if ENABLE_SIGNAL_TABLE_TF_BADGES:
                kr_tf_maps = _scanner3_build_multitimeframe_signal_maps(
                    tuple((item["code"], item["name"]) for item in favorites),
                    preset,
                    data_end,
                )
                us_tf_maps = _scanner3_build_multitimeframe_signal_maps(
                    tuple((item["code"], item["name"]) for item in US_WATCHLIST),
                    preset,
                    data_end,
                )
                for row in kr_rows:
                    row["tf_signals"] = {
                        tf_label: kr_tf_maps.get(tf_label, {}).get(row["code"], _empty_signal_row(row["code"], row["name"]))
                        for tf_label in ("일봉", "주봉", "월봉")
                    }
                for row in us_rows:
                    row["tf_signals"] = {
                        tf_label: us_tf_maps.get(tf_label, {}).get(row["code"], _empty_signal_row(row["code"], row["name"]))
                        for tf_label in ("일봉", "주봉", "월봉")
                    }

        n_dyn_buy_flag = sum(1 for r in kr_rows if r.get("dyn_buy_flag") and not r.get("dyn_buy_signal"))
        n_dyn_buy = sum(1 for r in kr_rows if r.get("dyn_buy_signal"))
        n_dyn_hold = sum(1 for r in kr_rows if r.get("dyn_holding"))
        n_dyn_sell_flag = sum(1 for r in kr_rows if r.get("dyn_sell_flag") and not r.get("dyn_sell_signal"))
        n_dyn_sell = sum(1 for r in kr_rows if r.get("dyn_sell_signal"))
        n_us_buy_flag = sum(1 for r in us_rows if r.get("dyn_buy_flag") and not r.get("dyn_buy_signal"))
        n_us_buy = sum(1 for r in us_rows if r.get("dyn_buy_signal"))
        n_us_hold = sum(1 for r in us_rows if r.get("dyn_holding"))
        n_us_sell_flag = sum(1 for r in us_rows if r.get("dyn_sell_flag") and not r.get("dyn_sell_signal"))
        n_us_sell = sum(1 for r in us_rows if r.get("dyn_sell_signal"))

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
            '<div style="margin-bottom:12px">' +
            _mini_row("★", [
                ("매수 플래그", f"{n_dyn_buy_flag}", "#7AAFD4"),
                ("매수 신호", f"{n_dyn_buy}", "#4BFFB3"),
                ("보유 중", f"{n_dyn_hold}", "#C8C850"),
                ("매도 플래그", f"{n_dyn_sell_flag}", "#D47A9F"),
                ("매도 신호", f"{n_dyn_sell}", "#FF4B6E"),
            ], flag='🇰🇷') +
            _mini_row("★", [
                ("매수 플래그", f"{n_us_buy_flag}", "#7AAFD4"),
                ("매수 신호", f"{n_us_buy}", "#4BFFB3"),
                ("보유 중", f"{n_us_hold}", "#C8C850"),
                ("매도 플래그", f"{n_us_sell_flag}", "#D47A9F"),
                ("매도 신호", f"{n_us_sell}", "#FF4B6E"),
            ], flag='🇺🇸') +
            '</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"적용 프리셋: {preset.get('label')} · K{preset.get('start_k')}/L{preset.get('end_l')} · 지수 백테스트 기반 연구 프리셋")

        with st.expander(f"📋 🇰🇷 한국 즐겨찾기 현황 ({len(kr_rows)}개)", expanded=False):
            st.markdown(
                render_signal_table(
                    kr_rows,
                    market='kr',
                    current_chart_mode=chart_mode,
                    current_intra_interval={"5m": "5분", "15m": "15분", "30m": "30분", "60m": "60분"}.get(yf_interval) if chart_mode == "분봉" else None,
                ),
                unsafe_allow_html=True,
            )

        with st.expander(f"📋 🇺🇸 미국 지수/ETF 현황 ({len(us_rows)}개)", expanded=False):
            st.markdown(
                render_signal_table(
                    us_rows,
                    market='us',
                    current_chart_mode=chart_mode,
                    current_intra_interval={"5m": "5분", "15m": "15분", "30m": "30분", "60m": "60분"}.get(yf_interval) if chart_mode == "분봉" else None,
                ),
                unsafe_allow_html=True,
            )

        kr_names = [f["name"] for f in favorites]
        us_names = [t["name"] for t in US_WATCHLIST]
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        col_kr, col_us = st.columns(2)
        if "scanner3_active_market" not in st.session_state:
            st.session_state.scanner3_active_market = "kr" if kr_names else "us"

        with col_kr:
            with st.expander("🇰🇷 한국 즐겨찾기", expanded=True):
                if kr_names:
                    if st.session_state.get("scanner3_kr_name") not in kr_names:
                        st.session_state.scanner3_kr_name = kr_names[0]
                    st.selectbox("한국 종목", kr_names, key="scanner3_kr_name", label_visibility="collapsed")
                    if st.button("한국 선택", key="scanner3_select_kr_main", width="stretch"):
                        st.session_state.scanner3_active_market = "kr"
                else:
                    st.caption("즐겨찾기 종목이 없습니다.")

        with col_us:
            with st.expander("🇺🇸 미국 지수/ETF", expanded=True):
                if st.session_state.get("scanner3_us_name") not in us_names:
                    st.session_state.scanner3_us_name = us_names[0]
                st.selectbox("미국 종목", us_names, key="scanner3_us_name", label_visibility="collapsed")
                if st.button("미국 선택", key="scanner3_select_us_main", width="stretch"):
                    st.session_state.scanner3_active_market = "us"

        if st.session_state.get("scanner3_active_market") == "kr" and kr_names:
            selected_name = st.session_state.get("scanner3_kr_name", kr_names[0])
            selected = next((item for item in favorites if item["name"] == selected_name), favorites[0])
        else:
            selected_name = st.session_state.get("scanner3_us_name", us_names[0])
            selected = next((item for item in US_WATCHLIST if item["name"] == selected_name), US_WATCHLIST[0])

        with st.expander("📊 백테스트 비교 보기", expanded=False):
            bt_years = st.radio(
                "비교 기간",
                [10, 20],
                index=0,
                horizontal=True,
                format_func=lambda y: f"{y}년",
                key=f"scanner3_backtest_years_{selected['code']}",
            )
            st.caption("선택 종목의 일봉 OHLCV에 Final15 프리셋을 각각 다시 적용해 같은 평가 구간으로 비교합니다.")
            if st.button("15개 프리셋 비교 실행", key=f"scanner3_run_backtest_compare_{selected['code']}", width="stretch"):
                started = time.perf_counter()
                try:
                    manifest_hash = _scanner2_sha256(_SCANNER2_PRESET_PATH)
                    result = _scanner3_compare_presets_for_ticker(
                        selected["code"],
                        int(bt_years),
                        data_end,
                        manifest_hash,
                    )
                    elapsed = time.perf_counter() - started
                    if result.get("error"):
                        st.warning(result["error"])
                    else:
                        df_bt = _scanner3_format_backtest_table(result, preset.get("preset_key"))
                        st.dataframe(df_bt, width="stretch", hide_index=True)
                        st.caption(
                            f"공통 평가 구간: {result.get('common_start')} ~ {result.get('common_end')} · "
                            f"계산 시간 {elapsed:.1f}초"
                        )
                        st.caption("과거 성과 비교 결과이며 종목별 운영 확정 모델을 의미하지 않습니다. CAGR뿐 아니라 MDD와 사이클 수를 함께 확인하세요.")
                except Exception as exc:
                    st.warning(f"백테스트 비교 계산 중 오류가 발생했습니다: {exc}")

        with st.spinner(f"📈 {selected['name']} 상세 차트 계산..."):
            detail_ohlcv, detail_err = _scanner3_fetch_ticker_ohlcv(selected["code"], data_start, data_end, interval)
            snapshot = None
            if detail_ohlcv is not None and not detail_ohlcv.empty:
                snapshot = _scanner3_compute_from_ohlcv(
                    detail_ohlcv.rename(columns={c: c.lower() for c in detail_ohlcv.columns}),
                    preset,
                )

        if snapshot is None:
            have = 0
            if detail_ohlcv is not None and not detail_ohlcv.empty and "Close" in detail_ohlcv:
                have = int(detail_ohlcv["Close"].dropna().shape[0])
            need = _scanner3_required_bars(preset)
            st.markdown(
                f'<div style="background:#141416;border:1px solid rgba(255,140,0,0.3);'
                f'border-radius:8px;padding:10px 16px;margin-bottom:10px;font-size:12px;color:#FFB347;">'
                f'⏳ 신호 계산 데이터 부족 — 현재 <b>{have}봉</b> / 필요 <b>{need}봉</b></div>',
                unsafe_allow_html=True,
            )
            if detail_err:
                st.caption(f"데이터 로딩 경고: {detail_err}")
            intraday_session = None
            if chart_mode == "분봉":
                is_korean = selected["code"].endswith((".KS", ".KQ")) or selected["code"] in ("^KS11", "^KQ11")
                intraday_session = (15.5, 9) if is_korean else (16, 9)
            price_fig = _scanner3_make_price_only_chart(
                detail_ohlcv,
                selected["name"],
                period_days,
                chart_mode=chart_mode,
                interval=interval,
                intraday_session=intraday_session,
            )
            if price_fig:
                st.plotly_chart(price_fig, width="stretch", config={"displayModeBar": False}, key=f"scanner3_price_only_{selected['code']}_{preset['preset_key']}_{chart_mode}_{period_days}")
            return

        meta = _scanner3_cycle_meta(snapshot["combo"])
        latest_text = meta["latest_date"].strftime("%Y-%m-%d") if meta["latest_date"] is not None else "—"
        event = "Risk 시작" if meta["start_signal"] else "Risk 종료" if meta["end_signal"] else "신규 시작/종료 신호 없음"
        active = meta["active_count"]
        total = len(snapshot["components"])
        st.markdown(
            f"""
            <div style='background:#111113;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:18px;margin:12px 0 16px;'>
                <div style='font-size:13px;color:#8f8f99;margin-bottom:8px;'>선택 종목 현재 상태</div>
                <div style='font-size:24px;font-weight:800;color:#f4f4f5;'>{selected['name']} · {latest_text}</div>
                <div style='margin-top:8px;color:#d6d6dc;'>현재 플래그 {active} / {total} ON · 상태 {'리스크 사이클 ON' if meta['risk_state'] else '리스크 사이클 OFF'}</div>
                <div style='margin-top:4px;color:#9ca3af;'>실행 안내 {event} · 현재 상태 시작일 {meta['cycle_start'].strftime('%Y-%m-%d') if meta['cycle_start'] is not None else '—'} · 지속 거래일 {meta['duration']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        intraday_session = None
        if chart_mode == "분봉":
            is_korean = selected["code"].endswith((".KS", ".KQ")) or selected["code"] in ("^KS11", "^KQ11")
            intraday_session = (15.5, 9) if is_korean else (16, 9)
        fig = _scanner3_make_detail_chart(
            snapshot,
            selected["name"],
            period_days,
            preset,
            chart_mode=chart_mode,
            interval=interval,
            intraday_session=intraday_session,
        )
        if fig:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"scanner3_detail_{selected['code']}_{preset['preset_key']}_{chart_mode}_{period_days}")
        else:
            st.warning("상세 차트를 그릴 수 있는 데이터가 부족합니다.")


def _render_signal_scanner3_section(container, favorites=None):
    with container:
        _render_dashboard_common_ui_css()
    chart_mode = st.session_state.get("chart_mode", "일봉")
    _intra_interval_map = {"5분": "5m", "15분": "15m", "30분": "30m", "60분": "60m"}
    _higher_interval_map = {"일봉": "1d", "주봉": "1wk", "월봉": "1mo"}
    if chart_mode == "분봉":
        intra_label = st.session_state.get("intra_interval", "15분")
        yf_interval = _intra_interval_map.get(intra_label, "15m")
        higher_interval = None
    else:
        yf_interval = None
        higher_interval = _higher_interval_map.get(chart_mode, "1d")
    _default_period_map = {"분봉": "3일", "일봉": "3개월", "주봉": "2년", "월봉": "10년"}
    period_name = st.session_state.get("sidebar_period", _default_period_map.get(chart_mode, "3개월"))
    period_days = PERIOD_OPTIONS.get(period_name, PERIOD_OPTIONS["3개월"])
    today = datetime.now().date()
    _render_signal_scanner3_mode(
        container,
        favorites=favorites or [],
        chart_mode=chart_mode,
        yf_interval=yf_interval,
        higher_interval=higher_interval,
        period_days=period_days,
        data_start="",
        data_end=str(today + timedelta(days=1)),
        auto_refresh=False,
        refresh_ms=300_000,
    )
    return

    with container:
        _render_dashboard_common_ui_css()
        try:
            manifest = _load_scanner2_preset_manifest()
        except Exception as exc:
            st.error(f"신호스캐너3 프리셋 로딩 실패: {exc}")
            return

        st.markdown(
            "<div class='dash-muted'>지수 백테스트로 선정한 EMA·RSI·BB·ATR K/L 프리셋을 각 종목 가격에 다시 계산해 적용합니다. 종목 단위 운영 확정 모델은 아닙니다.</div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([1, 3])
        with c1:
            preset_group = st.radio(
                "프리셋 그룹",
                list(manifest["markets"].keys()),
                format_func=lambda m: manifest["markets"][m]["label"],
                horizontal=False,
                key="scanner3_group",
            )
        with c2:
            preset = st.selectbox(
                "조합 프리셋",
                manifest["markets"][preset_group]["presets"],
                format_func=lambda p: f"{p['label']} · {p['index_param_id'].replace('idx_', '')} / {p['rsi_param_id'].replace('rsi_', '')} / {p['bb_param_id'].replace('bb_', '')} / {p.get('atr_param_id') or 'ATR 없음'} · K{p['start_k']}/L{p['end_l']}",
                label_visibility="collapsed",
                key=f"scanner3_preset_{preset_group}",
            )

        st.markdown(
            "<div class='dash-card-grid'>"
            f"<div class='dash-card'><div class='dash-card-label'>적용 프리셋</div><div class='dash-card-value' style='font-size:15px'>{preset['label']}</div><div class='dash-card-note'>{preset['candidate_id']}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>조합식</div><div class='dash-card-value' style='font-size:15px'>{preset['indicator_set'].upper()}</div><div class='dash-card-note'>시작 K{preset['start_k']} · 종료 L{preset['end_l']}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>상태</div><div class='dash-card-value' style='font-size:15px'>연구 기반 프리셋</div><div class='dash-card-note'>official_operating_model=False</div></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        today = datetime.now().date()
        data_end = str(today + timedelta(days=1))
        data_start = str(today - timedelta(days=365 * 25 + 30))

        favorites = favorites or []
        kr_items = tuple((item["code"], item["name"]) for item in favorites)
        us_items = tuple((item["code"], item["name"]) for item in US_WATCHLIST)

        with st.spinner("조합 프리셋으로 즐겨찾기 신호 계산 중..."):
            kr_rows = _scanner3_build_rows(kr_items, preset, data_start, data_end) if kr_items else []
            us_rows = _scanner3_build_rows(us_items, preset, data_start, data_end)

        with st.expander(f"📋 🇰🇷 한국 즐겨찾기 현황 ({len(kr_rows)}개)", expanded=False):
            if kr_rows:
                st.dataframe(_scanner3_rows_dataframe(kr_rows), width="stretch", hide_index=True)
            else:
                st.caption("한국 즐겨찾기 종목이 없습니다.")

        with st.expander(f"📋 🇺🇸 미국 지수/ETF 현황 ({len(us_rows)}개)", expanded=False):
            st.dataframe(_scanner3_rows_dataframe(us_rows), width="stretch", hide_index=True)

        st.markdown("<div class='dash-section-title'>종목 선택</div>", unsafe_allow_html=True)
        col_kr, col_us = st.columns(2)
        kr_names = [f["name"] for f in favorites]
        us_names = [t["name"] for t in US_WATCHLIST]
        if "scanner3_active" not in st.session_state:
            st.session_state.scanner3_active = "kr" if kr_names else "us"

        with col_kr:
            with st.expander("🇰🇷 한국 즐겨찾기", expanded=True):
                if kr_names:
                    if st.session_state.get("scanner3_kr_name") not in kr_names:
                        st.session_state.scanner3_kr_name = kr_names[0]
                    st.selectbox("한국종목선택", kr_names, key="scanner3_kr_name", label_visibility="collapsed")
                    if st.button("한국 선택", key="scanner3_select_kr", width="stretch"):
                        st.session_state.scanner3_active = "kr"
                else:
                    st.caption("신호스캐너1 사이드바에서 즐겨찾기를 추가해 주세요.")

        with col_us:
            with st.expander("🇺🇸 미국 지수/ETF", expanded=True):
                if st.session_state.get("scanner3_us_name") not in us_names:
                    st.session_state.scanner3_us_name = us_names[0]
                st.selectbox("미국종목선택", us_names, key="scanner3_us_name", label_visibility="collapsed")
                if st.button("미국 선택", key="scanner3_select_us", width="stretch"):
                    st.session_state.scanner3_active = "us"

        if st.session_state.get("scanner3_active") == "kr" and kr_names:
            selected_name = st.session_state.get("scanner3_kr_name", kr_names[0])
            selected = next((f for f in favorites if f["name"] == selected_name), favorites[0])
        else:
            selected_name = st.session_state.get("scanner3_us_name", us_names[0])
            selected = next((t for t in US_WATCHLIST if t["name"] == selected_name), US_WATCHLIST[0])

        with st.spinner(f"{selected['name']} 상세 신호 계산 중..."):
            snapshot = _scanner3_build_ticker_snapshot(selected["code"], preset, data_start, data_end)

        if snapshot is None:
            st.warning(f"{selected['name']} 데이터를 가져오거나 신호를 계산할 수 없습니다.")
            return

        meta = _scanner3_cycle_meta(snapshot["combo"])
        comp_latest = {
            name: bool(frame.reindex(snapshot["combo"].index).loc[meta["latest_date"]].get("risk_state", False))
            for name, frame in snapshot["components"].items()
        }
        event = "Risk 시작" if meta["start_signal"] else "Risk 종료" if meta["end_signal"] else "신규 시작/종료 신호 없음"
        st.markdown("<div class='dash-section-title'>선택 종목 현재 상태</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='dash-card-grid'>"
            f"<div class='dash-card'><div class='dash-card-label'>종목</div><div class='dash-card-value' style='font-size:15px'>{selected['name']}</div><div class='dash-card-note'>{selected['code']}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>기준일</div><div class='dash-card-value'>{meta['latest_date'].strftime('%Y-%m-%d')}</div><div class='dash-card-note'>Yahoo 일봉 기준</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>현재 ON 수</div><div class='dash-card-value'>{meta['active_count']} / {len(snapshot['components'])}</div><div class='dash-card-note'>시작 K{preset['start_k']} · 종료 L{preset['end_l']}</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>상태</div><div class='dash-card-value'>{'Risk ON' if meta['risk_state'] else 'Risk OFF'}</div><div class='dash-card-note'>상태 시작일 {meta['cycle_start'].strftime('%Y-%m-%d')} · {meta['duration']}거래일</div></div>"
            f"<div class='dash-card'><div class='dash-card-label'>실행 안내</div><div class='dash-card-value' style='font-size:15px'>{event}</div><div class='dash-card-note'>{' · '.join(f'{k}:{'ON' if v else 'OFF'}' for k, v in comp_latest.items())}</div></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("".join(_scanner2_status_badge(name, val) for name, val in comp_latest.items()), unsafe_allow_html=True)
        years = st.radio("상세 차트 기간", [3, 5, 10, 20], index=1, horizontal=True, format_func=lambda x: f"{x}년", key="scanner3_chart_years", label_visibility="collapsed")
        st.markdown("<div class='dash-section-title'>대표 차트: 종목 가격 + BB + 조합 Risk 신호</div>", unsafe_allow_html=True)
        fig = _scanner2_make_main_chart(snapshot, years)
        fig.update_layout(title=dict(text=selected["name"], font=dict(size=13, color="#D7D7D7")))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        st.markdown("<div class='dash-section-title'>지표별 상세 차트</div>", unsafe_allow_html=True)
        charts = _scanner2_make_component_charts(snapshot, years)
        st.plotly_chart(charts["EMA"], width="stretch", config={"displayModeBar": False})
        d1, d2 = st.columns(2)
        with d1:
            st.plotly_chart(charts["RSI"], width="stretch", config={"displayModeBar": False})
        with d2:
            st.plotly_chart(charts["ATR"], width="stretch", config={"displayModeBar": False})

        st.markdown("<div class='dash-section-title'>선택 종목 간단 백테스트</div>", unsafe_allow_html=True)
        bt = snapshot["backtest20"]
        st.dataframe(pd.DataFrame([{
            "기간": f"{bt.get('start_date', '—')} ~ {bt.get('end_date', '—')}",
            "전략 CAGR": _scanner2_fmt_pct(bt.get("cagr"), 2),
            "B&H CAGR": _scanner2_fmt_pct(bt.get("buyhold_cagr"), 2),
            "전략 MDD": _scanner2_fmt_pct(bt.get("mdd"), 1),
            "B&H MDD": _scanner2_fmt_pct(bt.get("buyhold_mdd"), 1),
            "Risk-off 비중": _scanner2_fmt_pct(bt.get("risk_off_share"), 1),
        }]), width="stretch", hide_index=True)

        with st.expander("📖 신호스캐너3 해석 가이드", expanded=False):
            st.markdown("""
            - 신호스캐너3는 지수 백테스트에서 고른 조합 프리셋의 **파라미터와 K/L 규칙**을 각 종목 가격에 다시 적용합니다.
            - 지수의 저장 신호를 종목에 복사하는 방식이 아니므로, 종목마다 신호 날짜와 상태가 다르게 나오는 것이 정상입니다.
            - `Risk ON`은 방어/현금 대기 성격의 구간으로 해석하고, `Risk OFF`는 위험 사이클이 꺼진 상태로 봅니다.
            - 개별 종목 단위로 별도 최적화한 모델은 아니므로, 초기에는 연구 기반 참고 신호로 검토해 주세요.
            """)


# ============================================================
# 메인 앱
# ============================================================
def _macro5_kospi_asset_path(name: str) -> str:
    return os.path.join(_APP_DIR, "kospi_macro5_assets", name)


def _macro5_kospi_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@st.cache_data(show_spinner=False)
def _load_macro5_kospi_frozen_assets():
    manifest_path = _macro5_kospi_asset_path("kospi_final9_dashboard_manifest.json")
    ui_manifest_path = _macro5_kospi_asset_path("kospi_macro5_d1b_ui_manifest.json")
    metrics_path = _macro5_kospi_asset_path("kospi_final9_candidate_metrics.csv")
    signals_path = _macro5_kospi_asset_path("kospi_final9_reference_signals.parquet")
    component_path = _macro5_kospi_asset_path("kospi_final9_component_reference_signals.parquet")
    benchmark_path = _macro5_kospi_asset_path("kospi_final9_benchmark_close.parquet")
    snapshot_path = _macro5_kospi_asset_path("kospi_final9_ui_snapshot_reference.parquet")
    dictionary_path = _macro5_kospi_asset_path("kospi_final9_component_dictionary.json")
    checksums_path = _macro5_kospi_asset_path("checksums.json")

    required = [
        manifest_path,
        ui_manifest_path,
        metrics_path,
        signals_path,
        component_path,
        benchmark_path,
        snapshot_path,
        dictionary_path,
        checksums_path,
    ]
    missing = [os.path.basename(p) for p in required if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"KOSPI Macro5 asset missing: {', '.join(missing)}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(ui_manifest_path, "r", encoding="utf-8") as f:
        ui_manifest = json.load(f)
    with open(dictionary_path, "r", encoding="utf-8") as f:
        component_dictionary = json.load(f)
    with open(checksums_path, "r", encoding="utf-8") as f:
        checksums = json.load(f)

    for filename, meta in checksums.items():
        path = _macro5_kospi_asset_path(filename)
        if os.path.exists(path) and _macro5_kospi_sha256(path) != meta.get("sha256"):
            raise ValueError(f"KOSPI Macro5 checksum mismatch: {filename}")

    metrics = pd.read_csv(metrics_path)
    signals = pd.read_parquet(signals_path)
    components = pd.read_parquet(component_path)
    benchmark = pd.read_parquet(benchmark_path)
    snapshot = pd.read_parquet(snapshot_path)
    for df in (signals, components, benchmark, snapshot):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

    if manifest.get("gate") != "PASS_WITH_RECOMPUTED_COMBO1_REFERENCE_SIGNALS":
        raise ValueError("KOSPI Macro5 D1-A gate is not valid")
    if ui_manifest.get("gate") != "PASS_KOSPI_MACRO5_D1B_UI_ASSET_COVERAGE":
        raise ValueError("KOSPI Macro5 D1-B UI asset gate is not valid")
    if metrics["candidate_id"].nunique() != 9 or signals["candidate_id"].nunique() != 9:
        raise ValueError("KOSPI Macro5 Final9 coverage mismatch")
    if int(signals.duplicated(["candidate_id", "date"]).sum()) != 0:
        raise ValueError("KOSPI Macro5 candidate/date duplicate detected")

    return {
        "manifest": manifest,
        "ui_manifest": ui_manifest,
        "metrics": metrics,
        "signals": signals,
        "components": components,
        "benchmark": benchmark,
        "snapshot": snapshot,
        "component_dictionary": component_dictionary,
        "manifest_sha256": _macro5_kospi_sha256(manifest_path),
        "ui_manifest_sha256": _macro5_kospi_sha256(ui_manifest_path),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _load_macro5_kospi_live_page_data_cached(sync_bucket: str):
    from kospi_macro5_runtime.page_adapter import load_macro5_live_page_data

    return load_macro5_live_page_data()


def _macro5_kospi_suffix(candidate_id: str) -> str:
    return str(candidate_id).split("_")[-1][-8:]


_MACRO5_KOSPI_DISPLAY_LABEL_OVERRIDES = {
    "m6::combo2_m6_k4_l2_2d90a80e824f7336": "[조합2] Main1 강건·안정 균형형 (조합1 6개/K4/L2)",
    "m5::combo2_m5_k2_l1_2bc7e194fdecfd9e": "[조합2] Main2 MDD·Calmar 앵커 (조합1 5개/K2/L1)",
    "combo1_n11_k9_l5_b984a8e53ad69a2d": "[조합1] Main1 강건·균형 코어형 (지표 11개/K9/L5)",
    "combo1_n11_k8_l5_93919287424179bd": "[조합1] Main2 방어·효율 코어형 (지표 11개/K8/L5)",
}
_MACRO5_KOSPI_ORDER_OVERRIDES = {
    "combo1_n11_k9_l5_b984a8e53ad69a2d": 0,
    "combo1_n11_k8_l5_93919287424179bd": 1,
    "m6::combo2_m6_k4_l2_2d90a80e824f7336": 0,
    "m5::combo2_m5_k2_l1_2bc7e194fdecfd9e": 1,
}


def _macro5_kospi_escape(value) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _macro5_kospi_model_type(value) -> str:
    return str(value or "").strip().lower()


def _macro5_kospi_preset_label(row: pd.Series | dict, component_count: int | None = None) -> str:
    candidate_id = str(row.get("candidate_id") or "")
    if candidate_id in _MACRO5_KOSPI_DISPLAY_LABEL_OVERRIDES:
        return _MACRO5_KOSPI_DISPLAY_LABEL_OVERRIDES[candidate_id]
    model_type = _macro5_kospi_model_type(row["model_type"])
    prefix = "조합1" if model_type == "combo1" else "조합2"
    unit = "지표" if model_type == "combo1" else "조합1"
    try:
        slot = int(row.get("slot"))
    except Exception:
        slot = -1
    if (model_type == "combo1" and slot == 1) or (model_type == "combo2" and slot == 5):
        role = "Main"
    else:
        role = str(row.get("role") or "")
    try:
        count = int(component_count if component_count is not None else row.get("m_or_n"))
    except Exception:
        count = 0
    try:
        k_value = int(row.get("K"))
        l_value = int(row.get("L"))
    except Exception:
        k_value = 0
        l_value = 0
    return f"[{prefix}] {role} ({unit} {count}개/K{k_value}/L{l_value})"


def _macro5_kospi_sort_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics is None or metrics.empty:
        return metrics
    out = metrics.copy()
    group_order = (
        out.groupby("model_type")["slot"].min().sort_values().reset_index()
        .assign(_group_order=lambda df: range(len(df)))
        .set_index("model_type")["_group_order"].to_dict()
    )
    out["_group_order"] = out["model_type"].map(group_order).fillna(99).astype(int)
    out["_main_order"] = out["candidate_id"].map(_MACRO5_KOSPI_ORDER_OVERRIDES).fillna(99).astype(int)
    out = out.sort_values(["_group_order", "_main_order", "slot"]).drop(columns=["_group_order", "_main_order"])
    return out.reset_index(drop=True)


def _macro5_kospi_component_display_label(
    value: str,
    candidate_map: dict[str, pd.Series | dict] | None = None,
    component_dict: dict | None = None,
) -> str:
    raw = str(value or "")
    if candidate_map and raw in candidate_map:
        component_count = None
        try:
            component_count = len((component_dict or {}).get(raw, {}).get("component_ids", []))
        except Exception:
            component_count = None
        return _macro5_kospi_preset_label(candidate_map[raw], component_count)
    parsed_combo1 = re.match(r"^combo1_n(?P<n>\d+)_k(?P<k>\d+)_l(?P<l>\d+)_", raw)
    if parsed_combo1:
        return (
            "[조합1] 구성 후보 "
            f"(지표 {int(parsed_combo1.group('n'))}개/K{int(parsed_combo1.group('k'))}/L{int(parsed_combo1.group('l'))})"
        )
    return _macro5_kospi_display_label(raw)


def _macro5_kospi_combo2_main_candidate_id(metrics: pd.DataFrame) -> str:
    if metrics is None or metrics.empty:
        raise ValueError("REVIEW_KOSPI_MACRO5_D1C3B2V_COMBO2_MAIN_NOT_UNIQUE")
    data = metrics.copy()
    data["_model_type_norm"] = data["model_type"].map(_macro5_kospi_model_type)
    main_rows = []
    for _, row in data[data["_model_type_norm"].eq("combo2")].iterrows():
        label = _macro5_kospi_preset_label(row)
        if str(row.get("candidate_id")) in _MACRO5_KOSPI_ORDER_OVERRIDES and _MACRO5_KOSPI_ORDER_OVERRIDES[str(row.get("candidate_id"))] == 0:
            main_rows.append(row)
        elif label.startswith("[조합2] Main "):
            main_rows.append(row)
    if len(main_rows) != 1:
        raise ValueError("REVIEW_KOSPI_MACRO5_D1C3B2V_COMBO2_MAIN_NOT_UNIQUE")
    return str(main_rows[0]["candidate_id"])


def _macro5_kospi_component_family(component_id: str) -> str:
    value = str(component_id or "")
    if "__" in value:
        return value.split("__", 1)[0]
    if " · " in value:
        return value.split(" · ", 1)[0]
    return value


def _macro5_kospi_display_label(value: str) -> str:
    raw = str(value or "")
    family = _macro5_kospi_component_family(raw)
    labels = {
        "global_credit_stress": "신용 스트레스",
        "kospi_bollinger": "KOSPI 볼린저밴드",
        "kospi_hv": "KOSPI 변동성",
        "kospi_hv_n5": "KOSPI 변동성 5",
        "kospi_hv_n10": "KOSPI 변동성 10",
        "kospi_hv_n20": "KOSPI 변동성 20",
        "kospi_hv_n40": "KOSPI 변동성 40",
        "kospi_hv_n80": "KOSPI 변동성 80",
        "kospi_index_level": "KOSPI 지수",
        "kospi_natr": "KOSPI NATR",
        "kospi_natr_n5": "KOSPI NATR 5",
        "kospi_natr_n10": "KOSPI NATR 10",
        "kospi_natr_n20": "KOSPI NATR 20",
        "kospi_natr_n40": "KOSPI NATR 40",
        "kospi_natr_n80": "KOSPI NATR 80",
        "kospi_rsi": "KOSPI RSI",
        "us_10y_2y_spread": "미국 10년-2년 금리차",
        "us_10y_3m_spread": "미국 10년-3개월 금리차",
        "us_10y_real_yield_level": "미국 10년 실질금리",
        "us_10y_slope": "미국 10년 금리기울기",
        "us_hy_oas_level": "미국 HY 프록시",
        "us_ig_oas_level": "미국 IG 프록시",
        "usdkrw_level": "원/달러 환율",
        "vix_level": "VIX",
        "vix_spread": "VIX 스프레드",
    }
    if family in labels:
        if "__" in raw and len(raw.split("__", 2)) > 1:
            suffix = raw.split("__", 2)[1]
        elif " · " in raw and len(raw.split(" · ", 1)) > 1:
            suffix = raw.split(" · ", 1)[1]
        else:
            suffix = ""
        return f"{labels[family]} · {suffix}" if suffix else labels[family]
    if raw.startswith("combo1_"):
        return f"조합1 · {_macro5_kospi_suffix(raw)}"
    return raw


def _macro5_kospi_date_text(value) -> str:
    if value is None or pd.isna(value):
        return "확인 불가"
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _macro5_kospi_source_ids_for_component(component_id: str) -> list[str]:
    family = _macro5_kospi_component_family(component_id)
    mapping = {
        "global_credit_stress": ["us_baa_corp_yield", "us_aaa_corp_yield", "nfci", "vix"],
        "kospi_bollinger": ["kospi_ohlcv"],
        "kospi_hv": ["kospi_ohlcv"],
        "kospi_index_level": ["kospi_ohlcv"],
        "kospi_natr": ["kospi_ohlcv"],
        "kospi_natr_n5": ["kospi_ohlcv"],
        "kospi_natr_n10": ["kospi_ohlcv"],
        "kospi_natr_n20": ["kospi_ohlcv"],
        "kospi_natr_n40": ["kospi_ohlcv"],
        "kospi_natr_n80": ["kospi_ohlcv"],
        "kospi_rsi": ["kospi_ohlcv"],
        "us_10y_2y_spread": ["us_10y_yield", "us_2y_yield"],
        "us_10y_3m_spread": ["us_10y_yield", "us_3m_yield"],
        "us_10y_real_yield_level": ["us_10y_real_yield"],
        "us_10y_slope": ["us_10y_yield"],
        "us_hy_oas_level": ["us_baa_corp_yield", "us_10y_yield"],
        "us_ig_oas_level": ["us_aaa_corp_yield", "us_10y_yield"],
        "usdkrw_level": ["usdkrw"],
        "vix_level": ["vix"],
        "vix_spread": ["vix", "vix3m"],
    }
    return mapping.get(family, [])


def _macro5_kospi_source_latest_text(source_rows: list[dict] | None, component_id: str, fallback_date=None) -> str:
    source_ids = _macro5_kospi_source_ids_for_component(component_id)
    rows = [
        row for row in (source_rows or [])
        if str(row.get("source_id")) in source_ids
    ]
    if not rows:
        return _macro5_kospi_date_text(fallback_date)

    def _row_date(row):
        return pd.to_datetime(row.get("actual_latest_krx_aligned_date") or row.get("actual_latest_available_date") or row.get("actual_latest_observation_date"), errors="coerce")

    valid = [row for row in rows if not pd.isna(_row_date(row))]
    if not valid:
        return _macro5_kospi_date_text(fallback_date)
    bottleneck = min(valid, key=_row_date)
    display_date = _macro5_kospi_date_text(
        bottleneck.get("actual_latest_krx_aligned_date")
        or bottleneck.get("actual_latest_available_date")
        or bottleneck.get("actual_latest_observation_date")
    )
    provider = str(bottleneck.get("provider", "")).upper()
    freshness = str(bottleneck.get("freshness_status", ""))
    lag = bottleneck.get("lag_krx_sessions")
    parts = [display_date]
    if freshness == "NO_NEW_RELEASE_EXPECTED":
        parts.append("주간 업데이트")
    elif provider:
        parts.append(provider)
    try:
        lag_int = int(lag)
        if lag_int > 0 and freshness != "NO_NEW_RELEASE_EXPECTED":
            parts.append(f"{lag_int}거래일 지연")
        elif lag_int == 0 and freshness == "FRESH":
            parts.append("최신")
    except Exception:
        pass
    return " · ".join(parts)


def _macro5_kospi_group_summary_html(candidate_rows: list[dict] | None, metrics: pd.DataFrame) -> str:
    candidate_rows = candidate_rows or []
    by_id = {str(row.get("candidate_id")): row for row in candidate_rows}
    summary = {}
    for label, model_type in [("조합2", "combo2"), ("조합1", "combo1")]:
        group = metrics[metrics["model_type"].map(_macro5_kospi_model_type).eq(model_type)]
        total = int(group["candidate_id"].nunique())
        rows = [by_id.get(str(candidate_id), {}) for candidate_id in group["candidate_id"]]
        calculable = sum(1 for row in rows if bool(row.get("calculable")))
        unavailable = max(0, total - calculable)
        risk_off = sum(1 for row in rows if bool(row.get("calculable")) and int(row.get("raw_risk_state") or 0) == 1)
        basis_dates = [row.get("basis_date") for row in rows if row.get("basis_date")]
        basis = max(basis_dates) if basis_dates else "계산 불가"
        availability_color = "#54F2A3" if unavailable == 0 else "rgba(255,255,255,0.92)"
        unavailable_color = "#FF8C69" if unavailable else "rgba(255,255,255,0.72)"
        risk_color = "#FF8C69" if risk_off else "#4BFFB3"
        summary[label] = {
            "availability": (
                f"<span style='color:{availability_color};font-weight:700;'>{label} 계산 가능 {calculable} / {total}</span>"
                f"<span style='color:rgba(255,255,255,0.55);'> · </span>"
                f"<span style='color:{unavailable_color};font-weight:700;'>계산 불가 {unavailable}</span>"
            ),
            "risk": (
                f"<span style='color:{risk_color};font-weight:700;'>{label} Risk-off {risk_off}/{total}</span>"
                f"<span style='color:rgba(255,255,255,0.55);'> · 기준일 {_macro5_kospi_escape(basis)}</span>"
            ),
        }
    sep = "<span style='color:rgba(255,255,255,0.36);padding:0 10px;'>|</span>"
    return (
        "<div class='macro2-helper-text' style='margin-top:6px;line-height:1.55;'>"
        "<div>"
        + summary.get("조합2", {}).get("availability", "")
        + sep
        + summary.get("조합1", {}).get("availability", "")
        + "</div><div style='margin-top:2px;'>"
        + summary.get("조합2", {}).get("risk", "")
        + sep
        + summary.get("조합1", {}).get("risk", "")
        + "</div></div>"
    )


def _macro5_kospi_active_label_list(
    component_df: pd.DataFrame,
    limit: int = 4,
    candidate_map: dict[str, pd.Series | dict] | None = None,
    component_dict: dict | None = None,
) -> list[str]:
    if component_df is None or component_df.empty:
        return []
    latest = (
        component_df.sort_values("date")
        .drop_duplicates("component_id", keep="last")
        .sort_values("component_order")
    )
    active = latest[latest["component_risk_state"].fillna(0).astype(int).eq(1)]
    labels = []
    for _, row in active.iterrows():
        component_id = str(row.get("component_id") or "")
        label_source = component_id if candidate_map and component_id in candidate_map else row.get("component_label") or component_id
        labels.append(_macro5_kospi_component_display_label(label_source, candidate_map, component_dict))
    if len(labels) > limit:
        return labels[:limit] + [f"외 {len(labels) - limit}개"]
    return labels


def _macro5_kospi_freshness_display(status: str | None, provider: str | None = None, lag=None) -> str:
    raw = str(status or "").upper()
    provider_text = str(provider or "").upper()
    try:
        lag_int = int(lag)
    except Exception:
        lag_int = None
    if raw == "FRESH":
        return "최신" if lag_int in (None, 0) else f"{lag_int}거래일 지연"
    if raw == "NO_NEW_RELEASE_EXPECTED":
        return "주간 업데이트"
    if raw == "FALLBACK":
        return f"{provider_text} 보완" if provider_text else "보완값"
    if raw == "STALE":
        return f"{lag_int}거래일 지연" if lag_int is not None else "지연"
    if not raw:
        return ""
    return "검토 필요"


def _macro5_kospi_current_status_html(
    selected_row: pd.Series,
    live_row: dict | None,
    component_count: int,
    live_ok: bool,
    active_labels: list[str] | None = None,
    state_start_override: str | None = None,
    duration_override: str | None = None,
) -> str:
    if live_ok and live_row:
        basis = _macro5_kospi_escape(live_row.get("basis_date") or "—")
        active_count = int(live_row.get("active_count") or 0)
        raw_state = int(live_row.get("raw_risk_state") or 0)
        t1_position = int(live_row.get("t1_position") or 0)
        start_signal = bool(live_row.get("new_start_signal"))
        end_signal = bool(live_row.get("new_end_signal"))
        if state_start_override is not None:
            state_start = state_start_override
        else:
            state_start = _macro5_kospi_date_text(live_row.get("current_state_start_date"))
        if duration_override is not None:
            duration_text = duration_override
        else:
            duration = live_row.get("current_state_trading_days")
            duration_text = "확인 불가" if pd.isna(duration) else f"{int(duration)}"
    else:
        basis = "계산 불가"
        active_count = 0
        raw_state = 0
        t1_position = None
        start_signal = False
        end_signal = False
        state_start = "확인 불가"
        duration_text = "확인 불가"

    return _macro_compact_status_html(
        basis_date=basis,
        active_count=active_count,
        component_count=component_count,
        start_k=int(selected_row.get("K", component_count or 1)),
        risk_state=raw_state,
        execution_position=t1_position,
        start_event=start_signal,
        end_event=end_signal,
        state_start=state_start,
        duration_text=duration_text,
    )


def _macro5_kospi_current_chip(candidate_id: str, live_row_map: dict[str, dict], start_k: int | None = None) -> str:
    row = live_row_map.get(str(candidate_id), {})
    if not row or not row.get("calculable"):
        return "<span style='color:#FF8C69;font-weight:700;'>계산 불가</span>"
    raw_state = int(row.get("raw_risk_state") or 0)
    color = "#FF8C69" if raw_state == 1 else "#4BFFB3"
    try:
        active_count = int(row.get("active_count"))
        k_value = int(start_k if start_k is not None else row.get("K"))
        label = _macro5_kospi_current_on_k(active_count, k_value)
    except Exception:
        label = "Risk-off" if raw_state == 1 else "Risk-on"
    return f"<span style='color:{color};font-weight:700;'>{label}</span>"


def _macro5_kospi_ratio_span(ratio: float, good: bool) -> str:
    color = "#7FE7B1" if good else "#8F8F8F"
    weight = "700" if good else "400"
    return f"<span style='color:{color};font-size:11px;font-weight:{weight};'>({ratio:.2f}x)</span>"


def _macro5_kospi_window_index(benchmark: pd.DataFrame, start_date, end_date) -> pd.DatetimeIndex:
    if benchmark is None or benchmark.empty or "date" not in benchmark.columns:
        return pd.DatetimeIndex([])
    dates = pd.to_datetime(benchmark["date"])
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    return pd.DatetimeIndex(dates[(dates >= start) & (dates <= end)].sort_values().drop_duplicates())


def _macro5_kospi_max_drawdown(equity: pd.Series) -> float:
    if equity is None or equity.empty:
        return float("nan")
    curve = pd.Series(equity).astype(float)
    return float((curve / curve.cummax() - 1.0).min())


def _macro5_kospi_current_state_span(
    candidate_signal: pd.DataFrame,
    evaluation_start: str | pd.Timestamp = "2008-04-01",
) -> dict:
    if candidate_signal is None or candidate_signal.empty or "raw_risk_state" not in candidate_signal.columns:
        return {"state_start_text": "확인 불가", "duration_text": "확인 불가", "raw_state": None, "row_count": 0}
    ordered = candidate_signal.copy()
    ordered["date"] = pd.to_datetime(ordered["date"])
    start = pd.to_datetime(evaluation_start)
    ordered = ordered[ordered["date"] >= start].sort_values("date").reset_index(drop=True)
    if ordered.empty:
        return {"state_start_text": "확인 불가", "duration_text": "확인 불가", "raw_state": None, "row_count": 0}
    raw = ordered["raw_risk_state"].astype(int)
    current = int(raw.iloc[-1])
    start_idx = len(ordered) - 1
    while start_idx > 0 and int(raw.iloc[start_idx - 1]) == current:
        start_idx -= 1
    state_start_text = "평가기간 이전부터 지속" if start_idx == 0 else _macro5_kospi_date_text(ordered.iloc[start_idx]["date"])
    return {
        "state_start_text": state_start_text,
        "duration_text": str(len(ordered) - start_idx),
        "raw_state": current,
        "row_count": len(ordered),
    }


def _macro5_kospi_cycle_counts(position: pd.Series, short_cycle_days: int = 20) -> tuple[int, int]:
    if position is None or position.empty:
        return 0, 0
    pos = pd.Series(position).astype(int).reset_index(drop=True)
    in_cycle = False
    start_idx = None
    completed = 0
    short = 0
    for idx in range(1, len(pos)):
        prev = int(pos.iloc[idx - 1])
        cur = int(pos.iloc[idx])
        if not in_cycle and prev == 1 and cur == 0:
            in_cycle = True
            start_idx = idx
        elif in_cycle and prev == 0 and cur == 1:
            completed += 1
            duration = idx - (start_idx if start_idx is not None else idx)
            if duration <= short_cycle_days:
                short += 1
            in_cycle = False
            start_idx = None
    return completed, short


def _macro5_kospi_equity_stats(
    benchmark: pd.DataFrame,
    signal_df: pd.DataFrame | None,
    start_date,
    end_date,
    cost_bps: float = 10.0,
    buyhold: bool = False,
) -> dict:
    idx = _macro5_kospi_window_index(benchmark, start_date, end_date)
    if len(idx) == 0:
        return {"asset": float("nan"), "mdd": float("nan"), "cagr": float("nan"), "cycle": 0, "short_cycle": 0}
    bench = benchmark.copy()
    bench["date"] = pd.to_datetime(bench["date"])
    close = bench.sort_values("date").set_index("date")["kospi_close"].astype(float)
    returns = close.pct_change().fillna(0.0).reindex(idx).fillna(0.0)
    if buyhold:
        position = pd.Series(1.0, index=idx)
        cost = pd.Series(0.0, index=idx)
    else:
        if signal_df is None or signal_df.empty:
            return {"asset": float("nan"), "mdd": float("nan"), "cagr": float("nan"), "cycle": 0, "short_cycle": 0}
        sig = signal_df.copy()
        sig["date"] = pd.to_datetime(sig["date"])
        sig = sig.sort_values("date").set_index("date")
        position = sig["t1_position"].astype(float).reindex(idx)
        if position.isna().any():
            return {"asset": float("nan"), "mdd": float("nan"), "cagr": float("nan"), "cycle": 0, "short_cycle": 0}
        cost = position.diff().abs().fillna(0.0) * (float(cost_bps) / 10000.0)
    equity = (1.0 + returns * position - cost).cumprod() * 100.0
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    final_asset = float(equity.iloc[-1])
    cagr = (final_asset / 100.0) ** (1.0 / years) - 1.0
    cycle, short_cycle = _macro5_kospi_cycle_counts(position)
    return {
        "asset": final_asset,
        "mdd": _macro5_kospi_max_drawdown(equity),
        "cagr": float(cagr),
        "cycle": int(cycle),
        "short_cycle": int(short_cycle),
    }


def _macro5_kospi_build_backtest_stats(metrics: pd.DataFrame, signals: pd.DataFrame, benchmark: pd.DataFrame) -> dict:
    bench = benchmark.copy()
    bench["date"] = pd.to_datetime(bench["date"])
    frozen_end = bench["date"].max()
    frozen_start = _macro5_kospi_window_index(bench, pd.Timestamp("2008-04-01"), frozen_end).min()
    ten_year_start = _macro5_kospi_window_index(bench, frozen_end - pd.DateOffset(years=10), frozen_end).min()
    if pd.isna(frozen_start) or pd.isna(ten_year_start):
        return {"candidate": {}, "hold": {}, "window": {}}
    hold_full = _macro5_kospi_equity_stats(bench, None, frozen_start, frozen_end, buyhold=True)
    hold_10y = _macro5_kospi_equity_stats(bench, None, ten_year_start, frozen_end, buyhold=True)
    hold = {
        "10Y 자산": _macro3_metric_asset(hold_10y["asset"]),
        "전체 자산": _macro3_metric_asset(hold_full["asset"]),
        "전체 CAGR": _macro3_metric_percent(hold_full["cagr"]),
        "10Y MDD": _macro3_metric_percent(hold_10y["mdd"]),
        "전체 MDD": _macro3_metric_percent(hold_full["mdd"]),
        "전체 Risk-off": "0.0%",
        "전체 Cycle": "-",
        "짧은 Cycle": "-",
        "_10y_asset_num": hold_10y["asset"],
        "_full_asset_num": hold_full["asset"],
        "_full_cagr_num": hold_full["cagr"],
        "_10y_mdd_num": hold_10y["mdd"],
        "_full_mdd_num": hold_full["mdd"],
    }
    candidate = {}
    for _, row in metrics.iterrows():
        cid = str(row["candidate_id"])
        sig = signals[signals["candidate_id"].astype(str).eq(cid)].copy()
        full = _macro5_kospi_equity_stats(bench, sig, frozen_start, frozen_end)
        ten = _macro5_kospi_equity_stats(bench, sig, ten_year_start, frozen_end)
        candidate[cid] = {
            "10Y 자산": _macro3_metric_asset(ten["asset"]),
            "전체 자산": _macro3_metric_asset(full["asset"]),
            "전체 CAGR": _macro5_kospi_fmt_pct(row.get("cagr"), 1),
            "10Y MDD": _macro3_metric_percent(ten["mdd"]),
            "전체 MDD": _macro5_kospi_fmt_pct(row.get("mdd"), 1),
            "전체 Risk-off": _macro5_kospi_fmt_pct(row.get("risk_off_ratio"), 1),
            "전체 Cycle": str(full["cycle"]),
            "짧은 Cycle": str(full["short_cycle"]),
            "_10y_asset_num": ten["asset"],
            "_full_asset_num": full["asset"],
            "_full_cagr_num": row.get("cagr"),
            "_10y_mdd_num": ten["mdd"],
            "_full_mdd_num": full["mdd"],
        }
    return {
        "candidate": candidate,
        "hold": hold,
        "window": {
            "frozen_start": _macro5_kospi_date_text(frozen_start),
            "frozen_end": _macro5_kospi_date_text(frozen_end),
            "ten_year_start": _macro5_kospi_date_text(ten_year_start),
        },
    }


def _macro5_kospi_with_hold_ratio(value: str, numerator, denominator, kind: str) -> str:
    try:
        num = float(numerator)
        den = float(denominator)
        if den == 0:
            return value
        if kind == "mdd":
            ratio = abs(num) / abs(den)
            return f"{value} {_macro5_kospi_ratio_span(ratio, ratio <= 0.5)}"
        ratio = num / den
        return f"{value} {_macro5_kospi_ratio_span(ratio, ratio >= 1.5)}"
    except Exception:
        return value


def _macro5_kospi_build_backtest_panel(
    metrics: pd.DataFrame,
    live_row_map: dict[str, dict],
    selected_id: str,
    model_type: str,
    backtest_stats: dict | None = None,
) -> str:
    model_type = _macro5_kospi_model_type(model_type)
    rows_html = []
    backtest_stats = backtest_stats or {}
    hold_metrics = backtest_stats.get("hold", {})
    candidate_stats = backtest_stats.get("candidate", {})
    subset = _macro5_kospi_sort_metrics(metrics[metrics["model_type"].map(_macro5_kospi_model_type).eq(model_type)])
    if len(subset):
        rows_html.append(
            "<tr style='background:rgba(255,255,255,0.035);border-top:1px solid rgba(255,255,255,0.12);'>"
            f"<td title='KOSPI 홀드' style='{_MACRO_BACKTEST_CELL_LEFT}'>KOSPI 홀드</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('10Y 자산', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('전체 자산', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('전체 CAGR', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('10Y MDD', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('전체 MDD', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('전체 Risk-off', '0.0%')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('전체 Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{hold_metrics.get('짧은 Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_CURRENT}'>-</td></tr>"
        )
    for _, row in subset.iterrows():
        candidate_id = str(row["candidate_id"])
        is_selected = candidate_id == str(selected_id)
        bg = "rgba(120,126,231,0.16)" if is_selected else "transparent"
        border = "1px solid rgba(120,126,231,0.34)" if is_selected else "1px solid transparent"
        label = _macro5_kospi_escape(_macro5_kospi_preset_label(row))
        stats = candidate_stats.get(candidate_id, {})
        asset_10y = _macro5_kospi_with_hold_ratio(
            stats.get("10Y 자산", "-"),
            stats.get("_10y_asset_num"),
            hold_metrics.get("_10y_asset_num"),
            "asset",
        )
        asset_full = _macro5_kospi_with_hold_ratio(
            stats.get("전체 자산", "-"),
            stats.get("_full_asset_num"),
            hold_metrics.get("_full_asset_num"),
            "asset",
        )
        mdd_10y = _macro5_kospi_with_hold_ratio(
            stats.get("10Y MDD", "-"),
            stats.get("_10y_mdd_num"),
            hold_metrics.get("_10y_mdd_num"),
            "mdd",
        )
        mdd_full = _macro5_kospi_with_hold_ratio(
            stats.get("전체 MDD", "-"),
            stats.get("_full_mdd_num"),
            hold_metrics.get("_full_mdd_num"),
            "mdd",
        )
        cagr_full = _macro5_kospi_with_hold_ratio(
            stats.get("전체 CAGR", "-"),
            stats.get("_full_cagr_num"),
            hold_metrics.get("_full_cagr_num"),
            "cagr",
        )
        rows_html.append(
            f"<tr style='background:{bg};border-top:{border};border-bottom:{border};'>"
            f"<td title='{label}' style='{_MACRO_BACKTEST_CELL_LEFT}'>{label}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{asset_10y}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{asset_full}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{cagr_full}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{mdd_10y}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{mdd_full}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{stats.get('전체 Risk-off', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{stats.get('전체 Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_NUM}'>{stats.get('짧은 Cycle', '-')}</td>"
            f"<td style='{_MACRO_BACKTEST_CELL_CURRENT}'>{_macro5_kospi_current_chip(candidate_id, live_row_map, int(row.get('K', 1)))}</td></tr>"
        )
    if not rows_html:
        return ""
    return (
        _MACRO_BACKTEST_TABLE_WRAP_OPEN
        + f"<table style='{_MACRO_BACKTEST_TABLE_STYLE}'>"
        + _MACRO_BACKTEST_COLGROUP
        + _macro_backtest_header_html([
            ("역할 / 후보", "left"),
            ("10Y 자산", "right"),
            ("전체 자산", "right"),
            ("전체 CAGR", "right"),
            ("10Y MDD", "right"),
            ("전체 MDD", "right"),
            ("전체 Risk-off", "right"),
            ("전체 Cycle", "right"),
            ("짧은 Cycle", "right"),
            ("현재", "center"),
        ])
        + f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _macro5_kospi_build_component_status_panel(
    component_df: pd.DataFrame,
    source_rows: list[dict] | None,
    live_row_map: dict[str, dict],
    selected_model_type: str,
    candidate_map: dict[str, pd.Series | dict] | None = None,
    component_dict: dict | None = None,
) -> str:
    if component_df is None or component_df.empty:
        return ""
    latest_rows = (
        component_df.sort_values("date")
        .drop_duplicates("component_id", keep="last")
        .sort_values("component_order")
        .to_dict("records")
    )
    entries = []
    for row in latest_rows:
        component_id = str(row.get("component_id"))
        try:
            state = int(row.get("component_risk_state") or 0)
        except Exception:
            state = 0
        flag_html = _macro_status_circle(bool(state), color_on="#FF8C69")
        if _macro5_kospi_model_type(selected_model_type) == "combo2":
            child = live_row_map.get(component_id, {})
            latest_text = _macro5_kospi_date_text(child.get("basis_date") or row.get("date"))
            if child and child.get("freshness_status"):
                freshness_text = _macro5_kospi_freshness_display(
                    child.get("freshness_status"),
                    child.get("provider"),
                    child.get("lag_krx_sessions"),
                )
                if freshness_text:
                    latest_text = f"{latest_text} · {freshness_text}"
        else:
            latest_text = _macro5_kospi_source_latest_text(source_rows, component_id, fallback_date=row.get("date"))
        label_source = component_id if candidate_map and component_id in candidate_map else row.get("component_label") or component_id
        entries.append({
            "label": _macro5_kospi_component_display_label(label_source, candidate_map, component_dict),
            "selected": True,
            "flag_html": flag_html,
            "latest_text": latest_text,
        })
    midpoint = int(np.ceil(len(entries) / 2))
    left_entries = entries[:midpoint]
    right_entries = entries[midpoint:]
    row_count = max(len(left_entries), len(right_entries))

    def _entry_cells(entry):
        if not entry:
            return "<td style='padding:6px 8px;'></td>" * 4
        return (
            f"<td style='padding:5px 8px;color:#D6D6D6;line-height:1.32;'>{_macro5_kospi_escape(entry['label'])}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{_macro_status_circle(bool(entry['selected']), color_on='#7C7CF7')}</td>"
            f"<td style='padding:5px 8px;text-align:center;line-height:1.32;'>{entry['flag_html']}</td>"
            f"<td style='padding:5px 8px;color:#AFAFAF;line-height:1.32;'>{_macro5_kospi_escape(entry['latest_text'])}</td>"
        )

    rows_html = []
    for idx in range(row_count):
        left = left_entries[idx] if idx < len(left_entries) else None
        right = right_entries[idx] if idx < len(right_entries) else None
        rows_html.append(f"<tr>{_entry_cells(left)}<td style='width:12px;'></td>{_entry_cells(right)}</tr>")
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신 사용값</th>"
        "<th style='width:12px;border-bottom:1px solid rgba(255,255,255,0.08);'></th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>지표</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>선택</th>"
        "<th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>플래그</th>"
        "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);'>최신 사용값</th>"
        f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )



def _macro5_kospi_view_cut(df: pd.DataFrame, years: int, end_date=None) -> pd.DataFrame:
    if df is None or df.empty or "date" not in df.columns:
        return df
    out = df.sort_values("date").copy()
    end = pd.to_datetime(end_date if end_date is not None else out["date"].max())
    start = end - pd.DateOffset(years=int(years))
    return out[(out["date"] >= start) & (out["date"] <= end)].copy()


def _macro5_kospi_with_events(candidate_signal: pd.DataFrame) -> pd.DataFrame:
    out = candidate_signal.sort_values("date").copy()
    raw = pd.to_numeric(out["raw_risk_state"], errors="coerce").astype("Int64")
    prev = raw.shift(1).fillna(0).astype(int)
    derived_start = ((raw.fillna(0).astype(int) == 1) & (prev == 0)).astype("int8")
    derived_end = ((raw.fillna(0).astype(int) == 0) & (prev == 1)).astype("int8")
    if {"risk_start_signal", "risk_end_signal"}.issubset(out.columns):
        explicit_start = pd.to_numeric(out["risk_start_signal"], errors="coerce")
        explicit_end = pd.to_numeric(out["risk_end_signal"], errors="coerce")
        out["start_event"] = explicit_start.where(explicit_start.notna(), derived_start).fillna(0).astype("int8")
        out["end_event"] = explicit_end.where(explicit_end.notna(), derived_end).fillna(0).astype("int8")
    else:
        out["start_event"] = derived_start
        out["end_event"] = derived_end
    out["combo_risk_state"] = raw.eq(1)
    return out


def _macro5_kospi_with_component_events(component_signal: pd.DataFrame) -> pd.DataFrame:
    out = component_signal.sort_values("date").copy()
    raw = pd.to_numeric(out["component_risk_state"], errors="coerce").astype("Int64")
    prev = raw.shift(1).fillna(0).astype(int)
    derived_start = ((raw.fillna(0).astype(int) == 1) & (prev == 0)).astype("int8")
    derived_end = ((raw.fillna(0).astype(int) == 0) & (prev == 1)).astype("int8")
    if {"component_risk_start_signal", "component_risk_end_signal"}.issubset(out.columns):
        explicit_start = pd.to_numeric(out["component_risk_start_signal"], errors="coerce")
        explicit_end = pd.to_numeric(out["component_risk_end_signal"], errors="coerce")
        out["start_event"] = explicit_start.where(explicit_start.notna(), derived_start).fillna(0).astype("int8")
        out["end_event"] = explicit_end.where(explicit_end.notna(), derived_end).fillna(0).astype("int8")
    else:
        out["start_event"] = derived_start
        out["end_event"] = derived_end
    out["combo_risk_state"] = raw.eq(1)
    return out


_MACRO5_KOSPI_CHART_HEIGHT = 300
_MACRO5_KOSPI_PERIOD_OPTIONS = [2, 3, 5, 7, 10, 15, "all"]
_MACRO5_KOSPI_PERIOD_LABELS = {
    2: "2년",
    3: "3년",
    5: "5년",
    7: "7년",
    10: "10년",
    15: "15년",
    "all": "전체",
}


def _macro5_kospi_period_label(value) -> str:
    return _MACRO5_KOSPI_PERIOD_LABELS.get(value, str(value))


def _macro5_kospi_available_period_options(
    benchmark: pd.DataFrame,
    candidate_signal: pd.DataFrame,
    component_signal: pd.DataFrame,
    basis_date=None,
) -> tuple[list, pd.Timestamp | None]:
    starts = []
    for frame in (benchmark, candidate_signal, component_signal):
        if frame is None or frame.empty or "date" not in frame.columns:
            continue
        dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if not dates.empty:
            starts.append(dates.min().normalize())
    if not starts:
        return [2, 3, 5, "all"], None
    common_start = max(starts)
    basis = pd.to_datetime(basis_date).normalize() if basis_date is not None else None
    if basis is None:
        end_candidates = []
        for frame in (benchmark, candidate_signal):
            if frame is not None and not frame.empty and "date" in frame.columns:
                dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
                if not dates.empty:
                    end_candidates.append(dates.max().normalize())
        basis = min(end_candidates) if end_candidates else common_start
    available_years = max((basis - common_start).days / 365.25, 0.0)
    options = [year for year in [2, 3, 5, 7, 10, 15] if available_years >= float(year)]
    if not options:
        options = [2]
    options.append("all")
    return options, common_start


def _macro5_kospi_chart_window(benchmark: pd.DataFrame, years: int | str, basis_date=None, common_start=None):
    if benchmark is None or benchmark.empty or "date" not in benchmark.columns:
        return pd.DataFrame(), None, None
    bench = benchmark.copy()
    bench["date"] = pd.to_datetime(bench["date"]).dt.normalize()
    bench = bench.drop_duplicates("date", keep="last").sort_values("date")
    basis = pd.to_datetime(basis_date if basis_date is not None else bench["date"].max()).normalize()
    eligible = bench[bench["date"] <= basis].copy()
    if eligible.empty:
        return pd.DataFrame(), None, None
    x_end = eligible["date"].max()
    if str(years).lower() == "all":
        lower = pd.to_datetime(common_start).normalize() if common_start is not None else eligible["date"].min()
    else:
        lower = x_end - pd.DateOffset(years=int(years))
    visible = eligible[eligible["date"] >= lower].copy()
    if visible.empty:
        visible = eligible.tail(1).copy()
    x_start = visible["date"].min()
    return visible, x_start, x_end


def _macro5_kospi_join_on_benchmark(benchmark_window: pd.DataFrame, frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if benchmark_window is None or benchmark_window.empty or frame is None or frame.empty:
        return pd.DataFrame()
    right = frame.copy()
    right["date"] = pd.to_datetime(right["date"]).dt.normalize()
    keep = ["date"] + [col for col in columns if col in right.columns and col != "date"]
    return benchmark_window.merge(right[keep].drop_duplicates("date", keep="last"), on="date", how="left")


@st.cache_data(ttl=3600, show_spinner=False)
def _macro5_kospi_load_core15_metadata_cached() -> pd.DataFrame:
    path = os.path.join(_APP_DIR, "kospi_macro5_assets", "kospi_d1c1_required_core15_metadata.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(ttl=3600, show_spinner=False)
def _macro5_kospi_load_transformed_source_cached() -> pd.DataFrame:
    path = os.path.join(_APP_DIR, "kospi_macro5_assets", "kospi_d1c1a2_availability_adjusted_transformed_source_base.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    out = pd.read_parquet(path)
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


def _macro5_kospi_component_indicator_frame(component_id: str, source_base: pd.DataFrame | None = None) -> pd.DataFrame:
    meta = _macro5_kospi_load_core15_metadata_cached()
    if meta.empty or component_id not in set(meta["candidate_id"].astype(str)):
        return pd.DataFrame()
    row = meta[meta["candidate_id"].astype(str).eq(str(component_id))].iloc[0]
    raw_params = row.get("params_json", "{}")
    try:
        params = json.loads(raw_params) if isinstance(raw_params, str) else dict(raw_params)
    except Exception:
        return pd.DataFrame()
    source = source_base.copy() if isinstance(source_base, pd.DataFrame) and not source_base.empty else _macro5_kospi_load_transformed_source_cached()
    if source.empty or "date" not in source.columns:
        return pd.DataFrame()
    source["date"] = pd.to_datetime(source["date"]).dt.normalize()
    source = source.drop_duplicates("date", keep="last").sort_values("date")
    source_index = pd.DatetimeIndex(source["date"]).normalize()
    kind = str(row.get("kind", ""))
    try:
        from kospi_macro5_runtime.core15 import (
            _hv_series,
            _natr_series,
            _source_series,
            compute_bollinger_signal_frame,
            compute_dynamic_quantile_signal_frame,
            compute_rsi_signal_frame,
            compute_yield_slope_signal_frame,
        )
        if kind == "rsi":
            frame = compute_rsi_signal_frame(
                pd.Series(pd.to_numeric(source["kospi_close"], errors="coerce").to_numpy(), index=source_index),
                int(params["period"]),
                int(params["lookback"]),
                float(params["lower_q"]),
                float(params["upper_q"]),
            )
        elif kind == "bollinger":
            frame = compute_bollinger_signal_frame(
                pd.Series(pd.to_numeric(source["kospi_close"], errors="coerce").to_numpy(), index=source_index),
                pd.Series(pd.to_numeric(source["kospi_high"], errors="coerce").to_numpy(), index=source_index),
                pd.Series(pd.to_numeric(source["kospi_low"], errors="coerce").to_numpy(), index=source_index),
                int(params["window"]),
                float(params["std_multiplier"]),
            )
        elif kind == "yield_slope":
            frame = compute_yield_slope_signal_frame(
                _source_series(source, str(row["source_column"])),
                int(params["slope_window"]),
                int(params["ema_span"]),
                int(params["threshold_window"]),
                float(params["start_q"]),
                float(params["end_q"]),
            )
        else:
            if "natr_n" in params:
                series = _natr_series(source, int(params["natr_n"]))
            elif "hv_n" in params:
                series = _hv_series(source, int(params["hv_n"]))
            else:
                source_column = str(row.get("source_column", ""))
                if not source_column or source_column == "nan" or source_column not in source.columns:
                    return pd.DataFrame()
                series = _source_series(source, source_column)
            frame = compute_dynamic_quantile_signal_frame(
                series,
                int(params["window"]),
                float(params["start_q"]),
                float(params["end_q"]),
                int(params["ema_span"]),
            )
    except Exception:
        return pd.DataFrame()
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.reset_index().rename(columns={"index": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["macro5_chart_kind"] = kind
    return out


def _macro5_kospi_ema_columns(frame: pd.DataFrame) -> list[str]:
    if frame is None:
        return []
    return [
        str(col)
        for col in frame.columns
        if str(col).lower().startswith("ema") and re.fullmatch(r"ema\d+", str(col), flags=re.IGNORECASE)
    ]


def _macro5_kospi_fmt_pct(value, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "—"


def _macro5_kospi_fmt_num(value, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"


def _macro5_kospi_state_label(raw_state: int | bool) -> str:
    try:
        return "Risk-off" if int(raw_state) == 1 else "Risk-on"
    except Exception:
        return "계산 불가"


def _macro5_kospi_t1_label(position: int | bool) -> str:
    try:
        return "투자" if int(position) == 1 else "비투자"
    except Exception:
        return "계산 불가"


def _macro5_kospi_reference_label(reference_type: str) -> str:
    mapping = {
        "PASS_VS_STAGE06A_RAW_BANK": "저장신호 parity 확인",
        "RECOMPUTED_FROM_CORE15_COMPONENTS": "Core15 구성 재계산 reference",
        "PASS_STORED_STAGE07C2_DAILY_SIGNAL": "Stage07C.2 저장 daily signal",
    }
    return mapping.get(str(reference_type), str(reference_type))


def _macro5_kospi_current_on_k(active_count, start_k) -> str:
    return _macro_on_k_text(int(active_count), int(start_k))


def _macro5_kospi_apply_macro4_chart_layout(fig: go.Figure, title: str, height: int, x_start, x_end) -> None:
    fig.update_layout(
        template="plotly_dark",
        height=int(height),
        margin=dict(l=50, r=20, t=38, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text=title, font=dict(size=12, color="#9B9B9B"), x=0, y=0.97),
        font=dict(color="#C9C9C9", size=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=9)),
        hovermode="x unified",
    )
    fig.update_xaxes(range=[x_start, x_end], autorange=False, gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)", title_text=None)


def _macro5_kospi_build_main_chart(candidate_signal: pd.DataFrame, benchmark: pd.DataFrame, label: str, years: int | str, show_raw: bool, basis_date=None, common_start=None) -> go.Figure | None:
    if candidate_signal is None or candidate_signal.empty or benchmark is None or benchmark.empty:
        return None
    signal = _macro5_kospi_with_events(candidate_signal)
    if common_start is None:
        _, common_start = _macro5_kospi_available_period_options(benchmark, signal, pd.DataFrame(), basis_date=basis_date)
    visible_benchmark, x_start, x_end = _macro5_kospi_chart_window(benchmark, years, basis_date=basis_date, common_start=common_start)
    merged = _macro5_kospi_join_on_benchmark(
        visible_benchmark,
        signal,
        ["raw_risk_state", "t1_position", "start_event", "end_event", "combo_risk_state", "valid_signal"],
    )
    if merged.empty:
        return None
    required = ["raw_risk_state", "combo_risk_state"]
    if any(col not in merged.columns for col in required) or merged[required].isna().any().any():
        return None
    if "valid_signal" in merged.columns and merged["valid_signal"].isna().any():
        return None
    fig = go.Figure()
    _add_macro_combo_risk_cycle_background(fig, merged[["date", "combo_risk_state"]], merged["date"])
    fig.add_trace(go.Scatter(
        x=merged["date"],
        y=merged["kospi_close"],
        mode="lines",
        name="KOSPI",
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
        hovertemplate="%{x|%Y-%m-%d}<br>KOSPI %{y:,.2f}<extra></extra>",
    ))
    if show_raw:
        position_y = merged["kospi_close"].where(merged["t1_position"].astype(int) == 1)
        fig.add_trace(go.Scatter(
            x=merged["date"],
            y=position_y,
            mode="lines",
            name="T+1 투자 가능",
            line=dict(color="rgba(204,213,57,0.68)", width=2.0),
            hoverinfo="skip",
        ))
    starts = merged[merged["start_event"].astype(int) == 1]
    ends = merged[merged["end_event"].astype(int) == 1]
    if not starts.empty:
        fig.add_trace(go.Scatter(
            x=starts["date"],
            y=starts["kospi_close"],
            mode="markers",
            name="Risk 시작",
            marker=dict(symbol="triangle-down", color="rgba(210,55,55,0.95)", size=9),
        ))
    if not ends.empty:
        fig.add_trace(go.Scatter(
            x=ends["date"],
            y=ends["kospi_close"],
            mode="markers",
            name="Risk 종료",
            marker=dict(symbol="triangle-up", color="rgba(80,160,255,0.92)", size=9),
        ))
    _macro5_kospi_apply_macro4_chart_layout(fig, label, _MACRO5_KOSPI_CHART_HEIGHT, x_start, x_end)
    return fig


def _macro5_kospi_add_price_markers(fig: go.Figure, merged: pd.DataFrame, yaxis: str = "y2") -> None:
    starts = merged[pd.to_numeric(merged.get("start_event", 0), errors="coerce").fillna(0).astype(int) == 1]
    ends = merged[pd.to_numeric(merged.get("end_event", 0), errors="coerce").fillna(0).astype(int) == 1]
    if not starts.empty:
        fig.add_trace(go.Scatter(
            x=starts["date"],
            y=starts["kospi_close"],
            yaxis=yaxis,
            mode="markers",
            name="Risk 시작",
            marker=dict(symbol="triangle-down", color="rgba(210,55,55,0.95)", size=9),
        ))
    if not ends.empty:
        fig.add_trace(go.Scatter(
            x=ends["date"],
            y=ends["kospi_close"],
            yaxis=yaxis,
            mode="markers",
            name="Risk 종료",
            marker=dict(symbol="triangle-up", color="rgba(80,160,255,0.92)", size=9),
        ))


def _macro5_kospi_build_component_chart(
    component_df: pd.DataFrame,
    benchmark: pd.DataFrame,
    title: str,
    years: int | str,
    *,
    model_type: str = "combo1",
    source_base: pd.DataFrame | None = None,
    show_aux: bool = False,
    basis_date=None,
    common_start=None,
) -> go.Figure | None:
    if component_df is None or component_df.empty:
        return None
    comp = _macro5_kospi_with_component_events(component_df)
    if common_start is None:
        _, common_start = _macro5_kospi_available_period_options(benchmark, pd.DataFrame(), comp, basis_date=basis_date)
    visible_benchmark, x_start, x_end = _macro5_kospi_chart_window(benchmark, years, basis_date=basis_date, common_start=common_start)
    merged = _macro5_kospi_join_on_benchmark(
        visible_benchmark,
        comp,
        [
            "component_risk_state",
            "component_active_count",
            "component_K",
            "component_L",
            "combo_risk_state",
            "start_event",
            "end_event",
            "valid_signal",
            "component_id",
        ],
    )
    if merged.empty:
        return None
    required = ["component_risk_state", "combo_risk_state", "valid_signal"]
    if any(col not in merged.columns for col in required) or merged[required].isna().any().any():
        return None
    fig = go.Figure()
    _add_macro_combo_risk_cycle_background(fig, merged[["date", "combo_risk_state"]], merged["date"])
    component_id = str(component_df["component_id"].dropna().iloc[0]) if "component_id" in component_df and len(component_df["component_id"].dropna()) else ""
    is_combo2_component = str(model_type).lower() == "combo2"
    chart_title = _macro5_kospi_component_display_label(component_id) if is_combo2_component else title

    if is_combo2_component:
        pass
    else:
        indicator = _macro5_kospi_component_indicator_frame(component_id, source_base=source_base)
        if not indicator.empty:
            indicator_visible = _macro5_kospi_join_on_benchmark(visible_benchmark, indicator, list(indicator.columns))
            kind = str(indicator.get("macro5_chart_kind", pd.Series([""])).dropna().iloc[0]) if "macro5_chart_kind" in indicator else ""
            mandatory_trace_count = 0
            ema_cols = _macro5_kospi_ema_columns(indicator_visible)

            if kind == "bollinger":
                if "close" in indicator_visible.columns:
                    fig.add_trace(go.Scatter(
                        x=indicator_visible["date"],
                        y=pd.to_numeric(indicator_visible["close"], errors="coerce"),
                        mode="lines",
                        name="가격",
                        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
                    ))
                    mandatory_trace_count += 1
                for col, name, color, dash in [
                    ("bb_middle", "BB 중심", "rgba(216,195,106,0.74)", "solid"),
                    ("bb_upper", "BB 상단", "rgba(255,140,105,0.68)", "dot"),
                    ("bb_lower", "BB 하단", "rgba(120,220,255,0.72)", "dot"),
                ]:
                    if col in indicator_visible.columns:
                        fig.add_trace(go.Scatter(
                            x=indicator_visible["date"],
                            y=pd.to_numeric(indicator_visible[col], errors="coerce"),
                            mode="lines",
                            name=name,
                            line=dict(color=color, width=1, dash=dash),
                        ))
                        mandatory_trace_count += 1
            elif kind == "rsi":
                if "rsi" in indicator_visible.columns:
                    fig.add_trace(go.Scatter(
                        x=indicator_visible["date"],
                        y=pd.to_numeric(indicator_visible["rsi"], errors="coerce"),
                        mode="lines",
                        name="RSI",
                        line=dict(color="rgba(124,124,247,0.82)", width=1.35),
                    ))
                    mandatory_trace_count += 1
                for col, name, color in [
                    ("dyn_upper", "상단 기준", "rgba(255,140,105,0.55)"),
                    ("dyn_lower", "하단 기준", "rgba(120,220,255,0.60)"),
                ]:
                    if col in indicator_visible.columns:
                        fig.add_trace(go.Scatter(
                            x=indicator_visible["date"],
                            y=pd.to_numeric(indicator_visible[col], errors="coerce"),
                            mode="lines",
                            name=name,
                            line=dict(color=color, width=1.2, dash="dot"),
                        ))
                        mandatory_trace_count += 1
            else:
                for col in ema_cols[:1]:
                    fig.add_trace(go.Scatter(
                        x=indicator_visible["date"],
                        y=pd.to_numeric(indicator_visible[col], errors="coerce"),
                        mode="lines",
                        name=col.upper(),
                        line=dict(color="rgba(216,195,106,0.32)", width=1.1),
                    ))
                    mandatory_trace_count += 1
                for col, name, color in [
                    ("risk_start_line", "시작선", "rgba(255,140,105,0.55)"),
                    ("risk_end_line", "종료선", "rgba(120,220,255,0.60)"),
                ]:
                    if col in indicator_visible.columns:
                        fig.add_trace(go.Scatter(
                            x=indicator_visible["date"],
                            y=pd.to_numeric(indicator_visible[col], errors="coerce"),
                            mode="lines",
                            name=name,
                            line=dict(color=color, width=1.2, dash="dot"),
                        ))
                        mandatory_trace_count += 1

            if mandatory_trace_count == 0:
                return None
            if show_aux:
                raw_col = next((col for col in ["value", "close", "rsi"] if col in indicator_visible.columns), None)
                if raw_col and not (kind == "rsi" and raw_col == "rsi") and not (kind == "bollinger" and raw_col == "close"):
                    fig.add_trace(go.Scatter(
                        x=indicator_visible["date"],
                        y=pd.to_numeric(indicator_visible[raw_col], errors="coerce"),
                        mode="lines",
                        name="원자료",
                        line=dict(color="rgba(182,182,182,0.22)", width=0.85),
                    ))
        else:
            return None

    fig.add_trace(go.Scatter(
        x=merged["date"],
        y=merged["kospi_close"],
        yaxis="y" if is_combo2_component else "y2",
        mode="lines",
        name="KOSPI",
        line=dict(color="rgba(182,182,182,0.88)", width=1.55),
    ))
    _macro5_kospi_add_price_markers(fig, merged, yaxis="y" if is_combo2_component else "y2")
    _macro5_kospi_apply_macro4_chart_layout(fig, chart_title, _MACRO5_KOSPI_CHART_HEIGHT, x_start, x_end)
    if is_combo2_component:
        fig.update_layout(yaxis=dict(title=None, side="right", showgrid=True))
    else:
        fig.update_layout(
            yaxis=dict(title=None, side="left", showgrid=True),
            yaxis2=dict(title=None, overlaying="y", side="right", showgrid=False, zeroline=False),
        )
    return fig


def _handle_kospi_macro5_probe_if_requested():
    try:
        probe_requested = st.query_params.get("macro5_probe") == "1"
    except Exception:
        probe_requested = False
    if not probe_requested:
        return False
    from kospi_macro5_runtime.streamlit_cloud_probe_bridge import handle_kospi_macro5_cloud_probe

    return handle_kospi_macro5_cloud_probe()


def main(page="signal"):
    global rsi_buy_lower_global, rsi_sell_lower_global

    _configure_streamlit_page(page)
    if _handle_kospi_macro5_probe_if_requested():
        return
    st.markdown(DARK_CSS, unsafe_allow_html=True)
    if page == "market_macro":
        st.markdown("""
        <style>
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: none !important;
            width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        </style>
        """, unsafe_allow_html=True)
    elif page in ("signal", "signal2", "signal3", "all"):
        st.markdown("""
        <style>
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 1400px !important;
            width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        </style>
        """, unsafe_allow_html=True)

    # 항상 파일에서 읽음 → 외부 수정·추가 즉시 반영, 삭제도 정확히 유지됨
    st.session_state.favorites = load_favorites()
    favorites = st.session_state.favorites

    _scan_market_param = st.query_params.get("scan_market")
    _scan_code_param = st.query_params.get("scan_code")
    _chart_mode_param = st.query_params.get("chart_mode")
    _intra_interval_param = st.query_params.get("intra_interval")
    _scan_nav_sig = "|".join([
        str(_scan_market_param or ""),
        str(_scan_code_param or ""),
        str(_chart_mode_param or ""),
        str(_intra_interval_param or ""),
    ])
    if _scan_market_param and _scan_code_param and st.session_state.get("_last_scan_nav_sig") != _scan_nav_sig:
        _signal_debug_log(
            "scan_queryparam_apply",
            market=_scan_market_param,
            code=_scan_code_param,
            chart_mode=_chart_mode_param,
            intra_interval=_intra_interval_param,
        )
        if _scan_market_param == "kr":
            _matched_kr = next((f for f in favorites if f['code'] == _scan_code_param), None)
            if _matched_kr is not None:
                st.session_state.scan_active = 'kr'
                st.session_state.scan_kr_name = _matched_kr['name']
                st.session_state.scan_kr_prev_name = _matched_kr['name']
        elif _scan_market_param == "us":
            _matched_us = next((t for t in US_WATCHLIST if t['code'] == _scan_code_param), None)
            if _matched_us is not None:
                st.session_state.scan_active = 'us'
                st.session_state.scan_us_name = _matched_us['name']
                st.session_state.scan_us_prev_name = _matched_us['name']
        if _chart_mode_param in {"일봉", "주봉", "월봉", "분봉"}:
            st.session_state["chart_mode"] = _chart_mode_param
        if _intra_interval_param in {"5분", "15분", "30분", "60분"}:
            st.session_state["intra_interval"] = _intra_interval_param
        st.session_state["_last_scan_nav_sig"] = _scan_nav_sig

    if page in ("market_macro", "macro2", "macro3", "macro6", "signal2", "signal3"):
        st.markdown("""
            <style>
            [data-testid="stSidebar"] { display: none !important; }
            section[data-testid="stSidebar"] { display: none !important; }
            </style>
        """, unsafe_allow_html=True)

    # ─── 사이드바 ─────────────────────────────────────────────
    if page not in ("market_macro", "macro2", "macro3", "macro6", "signal2", "signal3"):
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
        _default_period_map = {
            "분봉": "3일",
            "일봉": "3개월",
            "주봉": "2년",
            "월봉": "10년",
        }
        _default_period = _default_period_map.get(chart_mode, "3개월")
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

        _scanner_mode_for_sidebar = st.session_state.get("signal_scanner_mode", "신호스캐너1")
        if _scanner_mode_for_sidebar == "신호스캐너3":
            st.markdown("**🧩 조합 프리셋**")
            try:
                _preset_manifest = _load_scanner2_preset_manifest()
                _preset_options = _scanner3_preset_options(_preset_manifest)
                _preset_keys = [key for key, _ in _preset_options]
                _preset_labels = dict(_preset_options)
                if st.session_state.get("scanner3_sidebar_preset_key") not in _preset_keys:
                    st.session_state["scanner3_sidebar_preset_key"] = _preset_keys[0]
                st.selectbox(
                    "프리셋",
                    _preset_keys,
                    format_func=lambda key: _preset_labels.get(key, key),
                    key="scanner3_sidebar_preset_key",
                    label_visibility="collapsed",
                    help="지수 백테스트 Final5 프리셋의 EMA·RSI·BB·ATR·K/L 파라미터를 선택 종목 가격에 적용합니다.",
                )
                st.caption("신호스캐너3은 이 프리셋 하나만 신호 규칙으로 사용합니다.")
            except Exception as exc:
                st.warning(f"프리셋 로딩 실패: {exc}")
                st.session_state["scanner3_sidebar_preset_key"] = None
            bb_window = 20
            rsi_lookback = 40
            persist = 2
            phase2_rsi = False
        else:
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
        "signal2": ("TECHNICAL SIGNAL SCANNER 2", "🎯 신호스캐너2"),
        "signal3": ("TECHNICAL SIGNAL SCANNER 3", "🎯 신호스캐너3"),
        "market": ("MARKET INTERNALS", "🌐 시장 내부지표"),
        "macro": ("MACRO INDICATORS", "🌍 매크로 지표"),
        "market_macro": ("MARKET & MACRO DASHBOARD", "🌐 시장/매크로 지표"),
        "macro2": ("MACRO INDICATORS 2", "🧪 매크로 지표 2"),
        "macro3": ("MACRO INDICATORS 3", "🧪 매크로 지표 3"),
        "macro4": ("MACRO INDICATORS 4", "🧪 매크로 지표 4"),
        "macro5": ("MACRO INDICATORS 5", "🧪 매크로 지표 3"),
        "macro6": ("MACRO INDICATORS 6", "🧪 매크로 지표 4"),
        "macro5_kospi": ("KOSPI MACRO INDICATORS", "🇰🇷 매크로 지표 5"),
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
    tab7 = None
    _market_macro_section = None
    if page == "all":
        tab1, tab2, tab3 = st.tabs(["📊 신호 스캐너", "🌐 시장 내부지표", "🌍 매크로 지표"])
    elif page == "signal":
        tab1, tab2, tab3 = st.container(), None, None
    elif page == "signal2":
        tab1, tab2, tab3 = st.container(), None, None
    elif page == "signal3":
        tab1, tab2, tab3 = st.container(), None, None
    elif page == "market":
        tab1, tab2, tab3 = None, st.container(), None
    elif page == "macro":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "market_macro":
        _market_macro_sections = [
            ("macro", "🌍 매크로 지표"),
            ("macro4", "🧪 매크로 지표 2"),
            ("macro5", "🧪 매크로 지표 3"),
            ("macro6", "🧪 매크로 지표 4"),
            ("macro5_kospi", "🇰🇷 매크로 지표 5"),
            ("market", "🌐 시장 내부지표"),
        ]
        if st.session_state.get("market_macro_section") not in {k for k, _ in _market_macro_sections}:
            st.session_state["market_macro_section"] = "macro6"
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
        tab7 = st.container()
        tab1 = None
    elif page == "macro2":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro3":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro4":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro5":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro6":
        tab1, tab2, tab3 = None, None, st.container()
    elif page == "macro5_kospi":
        tab1, tab2, tab3 = None, None, st.container()
    else:
        st.error(f"알 수 없는 페이지입니다: {page}")
        return

    def render_market_internal_indicators_section(container):
        with container:
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

                _score_ts_fig = make_score_timeseries_chart(market_df, market_choice)
                if _score_ts_fig is not None:
                    st.plotly_chart(_score_ts_fig, width="stretch", config={"displayModeBar": False})

                render_market_score_ui(market_df, market_choice)

                def _mkt_card(label, value, delta="", accent="#787EE7"):
                    dlt = (f'<div style="font-size:9px;color:#555;margin-top:1px;">{delta}</div>' if delta else "")
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
                    return f'<div style="display:flex;gap:5px;margin-bottom:5px;">{cards_html}</div>'

                summ_val = float(latest['서머레이션'])
                vix_val = latest['VIX']
                ma20_val = latest['상승비율MA20']
                p200_val = latest['100MA상위']
                p50_val = latest.get('20MA상위')
                adl_chg = float(latest['ADL'] - prev['ADL'])
                vix_lbl = "변동성(HV20)" if market_choice in ("코스피", "코스닥") else "VIX"

                row1 = "".join([
                    _mkt_card("시총가중", f"{latest['시총가중']:.1f}", f"{latest['시총가중']-prev['시총가중']:+.2f}",
                              "#00FF7F" if latest['시총가중'] > prev['시총가중'] else "#FF4B6E"),
                    _mkt_card("균일가중", f"{latest['균일가중']:.1f}", f"{latest['균일가중']-prev['균일가중']:+.2f}",
                              "#FFD700" if latest['균일가중'] > prev['균일가중'] else "#FF4B6E"),
                    _mkt_card("ADL", f"{latest['ADL']:.0f}", f"{adl_chg:+.0f}",
                              "#4BFFB3" if adl_chg >= 0 else "#FF4B6E"),
                    _mkt_card("서머레이션", f"{summ_val:+.0f}", "강세구간" if summ_val > 0 else "약세구간",
                              "#4BFFB3" if summ_val > 0 else "#FF4B6E"),
                    _mkt_card(vix_lbl, f"{vix_val:.1f}" if pd.notna(vix_val) else "—",
                              "공포" if (pd.notna(vix_val) and float(vix_val) > 30)
                              else ("탐욕" if (pd.notna(vix_val) and float(vix_val) < 20) else "중립"), "#FFB347"),
                    _mkt_card("상승비율MA20", f"{ma20_val:.1f}%" if pd.notna(ma20_val) else "—", "",
                              "#4BFFB3" if (pd.notna(ma20_val) and float(ma20_val) > 50) else "#FF4B6E"),
                    _mkt_card("20MA 상위", f"{p50_val:.1f}%" if pd.notna(p50_val) else "—",
                              "강세" if (pd.notna(p50_val) and float(p50_val) > 50) else "약세",
                              "#87CEEB" if (pd.notna(p50_val) and float(p50_val) > 50) else "#FF4B6E"),
                    _mkt_card("100MA 상위", f"{p200_val:.1f}%" if pd.notna(p200_val) else "—",
                              "강세장" if (pd.notna(p200_val) and float(p200_val) > 70)
                              else ("약세장" if (pd.notna(p200_val) and float(p200_val) < 30) else "중립"), "#C8C850"),
                ])
                st.markdown(_mkt_row(row1), unsafe_allow_html=True)

                n_med = int(market_df['전체종목수'].median())
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

                st.plotly_chart(make_market_chart(market_df, market_choice), width="stretch", config={"displayModeBar": False})

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
    <tr><td><b>시총가중 지수</b></td><td>삼성·애플 같은 큰 회사 위주로 시장이 얼마나 올랐나</td><td class="bull">꾸준히 우상향</td><td class="bear">꺾이며 하락</td><td>우리가 흔히 보는 코스피·S&P500 과 같은 개념. 가장 기본 지표</td></tr>
    <tr><td><b>균일가중 지수</b></td><td>큰 회사·작은 회사 모두 똑같이 1표씩 줬을 때의 시장. "골고루 오르나?" 확인용</td><td class="bull">시총가중과 함께 오름</td><td class="bear">시총가중만 오르고 이건 제자리</td><td>둘이 같이 오르면 건강한 장. 시총가중만 오르면 일부 대형주만 끌어올리는 불안한 장</td></tr>
    <tr><td><b>ADL (등락누적선)</b></td><td>매일 오른 종목 수 − 내린 종목 수를 계속 더한 값. 시장이 진짜 건강한지 보여줌</td><td class="bull">계속 우상향</td><td class="bear">지수는 오르는데 ADL은 내려감 (위험 신호!)</td><td><b>가장 중요한 선행지표.</b> 지수보다 ADL이 먼저 꺾이면 조정이 곧 온다는 경고. ADL이 먼저 올라오면 반등 시작 신호</td></tr>
    <tr><td><b>52주 신고가 비율</b></td><td>오늘 1년(52주) 내 최고가를 찍은 종목 수 ÷ 전체 유효 종목 수 × 100. 진짜 상승 모멘텀이 있는지 확인</td><td class="bull">30% 이상 = 강한 상승 모멘텀</td><td class="bear">5% 이하 = 신고가 거의 없음 (약세 신호)</td><td>지수가 오르는데 신고가 비율이 낮으면 소수 대형주만 끌어올리는 불안한 장. 역대 최고가 갱신 구간에서 30%+ 유지되면 진짜 상승장</td></tr>
    <tr><td><b>20일선 상위 비율</b></td><td>20일(약 1달) 평균 가격보다 지금 비싼 종목이 몇 %인지. 단기 추세의 건강도를 빠르게 파악</td><td class="bull">50% 이상 = 단기 강세 흐름</td><td class="bear">50% 이하 = 단기 약세 흐름</td><td>100일선 상위 비율보다 민감하게 반응해서 추세 전환을 더 빨리 알려줌. 50%선을 뚫고 올라오면 단기 반등 확인 신호</td></tr>
    <tr><td><b>맥클렐란 서머레이션</b></td><td>단기·장기 평균 등락 차이를 계속 누적한 값. "지금 강세장인지 약세장인지" 큰 그림</td><td class="bull">0 이상 (강세장 영역)</td><td class="bear">0 이하 (약세장 영역)</td><td>0선 위면 강세장, 아래면 약세장. 0선을 뚫고 올라오면 장세 전환 신호. 0선 위에서 하락 전환하면 조정 경고</td></tr>
    <tr><td><b>VIX / 역사적변동성(HV20)</b></td><td>투자자들이 얼마나 겁먹고 있나. 미국=VIX(옵션 내재변동성), 한국=HV20(지수 20일 실현변동성). 숫자 클수록 불안</td><td class="bull">급등 후 빠르게 내려올 때 → 공포 해소 = 반등 신호</td><td class="bear">낮은 수준에서 갑자기 급등 → 조정 시작 신호</td><td>미국 VIX: 20 이하=안심, 20~30=주의, 30 이상=공포. 한국 HV20: 15 이하=안심, 20 이상=주의, 25 이상=경계. <b>공포 극대일 때가 역발상 매수 타이밍</b>인 경우 많음</td></tr>
    <tr><td><b>상승비율 MA20</b></td><td>오늘 전체 종목 중 오른 종목이 몇 %인지를 20일 평균낸 것</td><td class="bull">60% 이상 유지</td><td class="bear">40% 이하로 내려감</td><td>50% 위면 "대부분 오르는 중", 아래면 "대부분 내리는 중". 하루치 수치는 변동 크니 20일 평균선만 봐도 충분</td></tr>
    <tr><td><b>100일선 상위 비율</b></td><td>100일(약 5개월) 평균 가격보다 지금 비싼 종목이 몇 %인지</td><td class="bull">70% 이상 = 강세장</td><td class="bear">30% 이하 = 약세장 / 20% 이하 = 침체 바닥권</td><td>중장기 건강도 지표. 30% 이하까지 내려간 뒤 반등하면 강력한 바닥 신호로 자주 활용됨</td></tr>
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

                with st.expander("🔬 지표 선행성 분석 (지수 예측력)", expanded=False):
                    st.caption(
                        "corr(지표[오늘], 지수[오늘+N일]) — 값이 높을수록 해당 지표가 N일 후 지수를 예측하는 경향이 있음. "
                        "4년치 데이터를 별도 로딩합니다."
                    )
                    with st.spinner("4년 데이터 로딩 중..."):
                        _ll_df, _ = get_market_internals(market_choice, lookback_days=1008)

                    if _ll_df is not None and not _ll_df.empty:
                        _ll_tbl = compute_lead_lag_table(_ll_df)
                        _ll_tbl = make_arrow_safe(_ll_tbl)
                        if not _ll_tbl.empty:
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

    def render_macro2_experimental_section(container):
        with container:
            st.caption("실험용 확장판입니다. ⓪/①/②/③/④/⑥ 차트 각각에 대해 동적 리스크 시작선/종료선을 개별 설정할 수 있습니다.")
            _macro2_sync_bucket = _macro_sync_bucket(60)

            _c0, _c1, _c2 = st.columns([1.2, 2.8, 1.2])
            with _c0:
                _benchmark_name = st.selectbox("기준지수", options=["S&P500", "Nasdaq", "KOSPI"], index=0, label_visibility='collapsed', key='macro2_benchmark')
            with _c1:
                _yr_opts = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro2_years = st.select_slider("기간", options=list(_yr_opts.keys()), value=3, format_func=lambda x: _yr_opts[x], label_visibility='collapsed', key='macro2_years')
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
                            _start = st.select_slider("리스크 시작 분위수", options=[x / 100 for x in range(0, 101, 5)], value=_cfg["start"], format_func=lambda x: f"{int(x * 100)}%", key=f'macro2_{_code}_start')
                        with _s3:
                            _end = st.select_slider("리스크 종료 분위수", options=[x / 100 for x in range(0, 101, 5)], value=_cfg["end"], format_func=lambda x: f"{int(x * 100)}%", key=f'macro2_{_code}_end')
                        _macro2_cfgs[_code] = {"ema": int(_ema), "window": int(_window), "start": float(_start), "end": float(_end)}

            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg2 = _get_macro_benchmark(_benchmark_name)
                _spx_s2 = _yf_close(_benchmark_cfg2['code'], _macro2_years, sync_bucket=_macro2_sync_bucket)

            _invalid_macro2 = [f"({_code})" for _code, _cfg in _macro2_cfgs.items() if _cfg["start"] <= _cfg["end"]]
            if _invalid_macro2:
                st.warning(f"리스크 시작 분위수는 종료 분위수보다 높아야 합니다: {' '.join(_invalid_macro2)}")
            else:
                with st.spinner("📡 실험용 매크로 데이터 로딩 중..."):
                    _macro2_charts = _build_macro2_dynamic_charts(_macro2_years, _spx_s2, _show_raw_macro2, _benchmark_name, _macro2_cfgs, sync_bucket=_macro2_sync_bucket)
                for _idx, _fig in enumerate(_macro2_charts):
                    if _fig is not None:
                        st.plotly_chart(_fig, width="stretch", config={"displayModeBar": False}, key=f"macro2_chart_{_idx}_{_benchmark_name}_{_macro2_years}_{_macro_dynamic_cfg_signature(_macro2_cfgs, [_code for _code in _MACRO2_SIGNAL_LABELS.keys() if _code in _macro2_cfgs])}")
                    else:
                        st.warning("실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")

    def render_macro3_threshold_section(container):
        with container:
            st.caption("정적 threshold 실험판입니다. ③/④/⑥ 차트에서 각 지표의 EMA가 지정 임계값 아래로 내려가면 시작, 위로 올라오면 종료로 단순화했습니다.")

            _c0, _c1, _c2 = st.columns([1.2, 2.8, 1.2])
            with _c0:
                _benchmark_name3 = st.selectbox("기준지수", options=["S&P500", "Nasdaq", "KOSPI"], index=0, label_visibility='collapsed', key='macro3_benchmark')
            with _c1:
                _yr_opts3 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro3_years = st.select_slider("기간", options=list(_yr_opts3.keys()), value=3, format_func=lambda x: _yr_opts3[x], label_visibility='collapsed', key='macro3_years')
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
                    make_macro_credit_stress_chart(_macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3, threshold_mode=True, threshold_value=float(_thr3_3), threshold_end_value=float(_thr3_end_3), ema_span=int(_ema_span3)),
                    make_macro_options_chart(_macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3, threshold_mode=True, threshold_value=float(_thr4_3), ema_span=int(_ema_span3)),
                    make_macro_vix_spread_chart(_macro3_years, _spx_s3, _show_raw_macro3, _downturn_params3, _benchmark_name3, threshold_mode=True, threshold_value=float(_thr6_3), ema_span=int(_ema_span3)),
                ]

            for _idx, _fig in enumerate(_macro3_charts):
                if _fig is not None:
                    st.plotly_chart(_fig, width="stretch", config={"displayModeBar": False}, key=f"macro3_chart_{_idx}_{_benchmark_name3}_{_macro3_years}")
                else:
                    st.warning("실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")

    def render_macro4_combo_section(container):
        with container:
            _started = time.perf_counter()
            st.markdown(
                '<div class="macro2-helper-text">선택한 지표의 리스크 사이클 상태를 조합해 신호를 표시합니다.</div>',
                unsafe_allow_html=True,
            )
            _macro4_sync_bucket = _macro_sync_bucket(60)
            _render_macro_combo_common_css()
            st.markdown("""
            <style>
            .st-key-macro4_preset div[data-baseweb="select"] > div,
            .st-key-macro4_benchmark div[data-baseweb="select"] > div,
            .st-key-macro4_selected_codes div[data-baseweb="select"] > div,
            .st-key-macro4_years div[data-baseweb="slider"] + div,
            .st-key-macro4_combo_k div[data-baseweb="slider"] + div,
            .st-key-macro4_show_raw label,
            .st-key-macro4_show_raw span,
            .st-key-macro4_show_raw p {
                font-size: 13.5px !important;
                color: rgba(255,255,255,0.92) !important;
            }
            .st-key-macro4_preset div[data-baseweb="select"] > div,
            .st-key-macro4_benchmark div[data-baseweb="select"] > div,
            .st-key-macro4_selected_codes div[data-baseweb="select"] > div {
                min-height: 2.55rem;
                border-color: rgba(95,86,214,0.72) !important;
                background: rgba(52,44,112,0.22) !important;
                box-shadow: none !important;
            }
            .st-key-macro4_selected_codes [data-baseweb="tag"] {
                background: rgba(92,79,214,0.96) !important;
                color: #F6F4FF !important;
            }
            .st-key-macro4_show_raw [data-baseweb="checkbox"] > div {
                border-color: rgba(95,86,214,0.78) !important;
            }
            .st-key-macro4_preset,
            .st-key-macro4_benchmark,
            .st-key-macro4_years,
            .st-key-macro4_show_raw,
            .st-key-macro4_selected_codes,
            .st-key-macro4_combo_k {
                margin-top: 0 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            _macro4_defaults = _get_macro2_dynamic_defaults()
            _macro4_presets = {
                "nasdaq_meta": {
                    "label": "나스닥 전용 메타조합",
                    "benchmark": "Nasdaq",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 10, "window": 252, "start": 0.80, "end": 0.50},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.20, "end": 0.10},
                        "3": {"ema": 20, "window": 252, "start": 0.20, "end": 0.10},
                        "4": {"ema": 10, "window": 63, "start": 0.60, "end": 0.30},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ② IG + ③ 신용스트레스 + ④ VIX",
                            "selected_codes": ["0", "2", "3", "4"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 10, "window": 252, "start": 0.80, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.20, "end": 0.10},
                                "3": {"ema": 20, "window": 252, "start": 0.20, "end": 0.10},
                                "4": {"ema": 10, "window": 63, "start": 0.60, "end": 0.30},
                            },
                        },
                        "combo_b": {
                            "label": "B: ⓪ 지수 + ① HY + ② IG + ③ 신용스트레스 + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "2", "3", "4", "6"],
                            "combo_k": 5,
                            "cfgs": {
                                "0": {"ema": 30, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 20, "window": 126, "start": 0.80, "end": 0.10},
                                "3": {"ema": 30, "window": 63, "start": 0.60, "end": 0.30},
                                "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "nasdaq_meta_stab_1": {
                    "label": "나스닥 전용 메타조합 휩쏘제거 1",
                    "benchmark": "Nasdaq",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 10, "window": 252, "start": 0.80, "end": 0.50},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.20, "end": 0.10},
                        "3": {"ema": 20, "window": 252, "start": 0.20, "end": 0.10},
                        "4": {"ema": 10, "window": 63, "start": 0.60, "end": 0.30},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "start_persist": 1,
                        "end_persist": 1,
                        "min_hold_days": 5,
                        "cooldown_days": 0,
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ② IG + ③ 신용스트레스 + ④ VIX",
                            "selected_codes": ["0", "2", "3", "4"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 10, "window": 252, "start": 0.80, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.20, "end": 0.10},
                                "3": {"ema": 20, "window": 252, "start": 0.20, "end": 0.10},
                                "4": {"ema": 10, "window": 63, "start": 0.60, "end": 0.30},
                            },
                        },
                        "combo_b": {
                            "label": "B: ⓪ 지수 + ① HY + ② IG + ③ 신용스트레스 + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "2", "3", "4", "6"],
                            "combo_k": 5,
                            "cfgs": {
                                "0": {"ema": 30, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 20, "window": 126, "start": 0.80, "end": 0.10},
                                "3": {"ema": 30, "window": 63, "start": 0.60, "end": 0.30},
                                "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "snp_meta_1": {
                    "label": "S&P 전용 메타조합 1",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                        "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                        "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                        "6": {"ema": 20, "window": 126, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ① HY + ② IG + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "2", "4", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                                "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                                "6": {"ema": 20, "window": 126, "start": 0.60, "end": 0.10},
                            },
                        },
                        "combo_b": {
                            "label": "B: ⓪ 지수 + ① HY + ③ 신용스트레스 + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "3", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "snp_meta_2": {
                    "label": "S&P 전용 메타조합 2",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "3": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                        "4": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ③ 신용스트레스 + ④ VIX",
                            "selected_codes": ["0", "3", "4"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "3": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                                "4": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                            },
                        },
                        "combo_b": {
                            "label": "B: ⓪ 지수 + ① HY + ③ 신용스트레스 + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "3", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "snp_meta_stab": {
                    "label": "S&P 전용 메타조합 휩쏘제거",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                        "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                        "4": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "start_persist": 10,
                        "end_persist": 2,
                        "min_hold_days": 0,
                        "cooldown_days": 0,
                        "combo_a": {
                            "label": "A: ① HY + ② IG + ③ 신용스트레스 + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["1", "2", "3", "4", "6"],
                            "combo_k": 4,
                            "cfgs": {
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                                "3": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                                "4": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                                "6": {"ema": 20, "window": 126, "start": 0.60, "end": 0.10},
                            },
                        },
                        "combo_b": {
                            "label": "B: ⓪ 지수 + ① HY + ③ 신용스트레스 + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "3", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "snp_meta_stab_2": {
                    "label": "S&P 전용 메타조합 휩쏘제거 2",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 30, "window": 126, "start": 0.80, "end": 0.70},
                        "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                        "3": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                        "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "start_persist": 1,
                        "end_persist": 2,
                        "min_hold_days": 15,
                        "cooldown_days": 15,
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ① HY + ② IG + ③ 신용스트레스 + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "2", "3", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                                "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                        "combo_b": {
                            "label": "B: ① HY + ③ 신용스트레스 + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["1", "3", "4", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "1": {"ema": 30, "window": 126, "start": 0.80, "end": 0.70},
                                "3": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                                "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                                "6": {"ema": 20, "window": 126, "start": 0.60, "end": 0.10},
                            },
                        },
                    },
                },
                "snp_meta_stab_3": {
                    "label": "S&P 전용 메타조합 휩쏘제거 3",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "2", "3", "4", "6"],
                    "combo_k": 2,
                    "cfgs": {
                        "0": {"ema": 30, "window": 63, "start": 0.60, "end": 0.50},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                        "3": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                        "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                        "6": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                    },
                    "meta": {
                        "exit_mode": "AND_EXIT",
                        "start_persist": 1,
                        "end_persist": 4,
                        "min_hold_days": 10,
                        "cooldown_days": 15,
                        "combo_a": {
                            "label": "A: ⓪ 지수 + ① HY + ② IG + ③ 신용스트레스 + ⑥ VIX 스프레드",
                            "selected_codes": ["0", "1", "2", "3", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "0": {"ema": 30, "window": 63, "start": 0.60, "end": 0.50},
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "2": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                                "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                            },
                        },
                        "combo_b": {
                            "label": "B: ① HY + ③ 신용스트레스 + ④ VIX + ⑥ VIX 스프레드",
                            "selected_codes": ["1", "3", "4", "6"],
                            "combo_k": 3,
                            "cfgs": {
                                "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                                "3": {"ema": 10, "window": 252, "start": 0.40, "end": 0.30},
                                "4": {"ema": 10, "window": 63, "start": 0.20, "end": 0.10},
                                "6": {"ema": 30, "window": 63, "start": 0.80, "end": 0.10},
                            },
                        },
                    },
                },
                "nasdaq": {
                    "label": "나스닥 전용 조합",
                    "benchmark": "Nasdaq",
                    "selected_codes": ["0", "2", "3", "4"],
                    "combo_k": 3,
                    "cfgs": {
                        "0": {"ema": 10, "window": 252, "start": 0.80, "end": 0.50},
                        "2": {"ema": 30, "window": 63, "start": 0.20, "end": 0.10},
                        "3": {"ema": 20, "window": 252, "start": 0.20, "end": 0.10},
                        "4": {"ema": 10, "window": 63, "start": 0.60, "end": 0.30},
                    },
                },
                "snp": {
                    "label": "S&P 전용 조합",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "3", "6"],
                    "combo_k": 3,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                },
                "common": {
                    "label": "미국 주식 공통 조합",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "3", "6"],
                    "combo_k": 3,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                },
                "custom": {
                    "label": "직접 설정",
                    "benchmark": "S&P500",
                    "selected_codes": ["0", "1", "3", "6"],
                    "combo_k": 3,
                    "cfgs": {
                        "0": {"ema": 20, "window": 252, "start": 0.80, "end": 0.70},
                        "1": {"ema": 20, "window": 126, "start": 0.60, "end": 0.50},
                        "3": {"ema": 10, "window": 126, "start": 0.20, "end": 0.10},
                        "6": {"ema": 30, "window": 63, "start": 0.60, "end": 0.10},
                    },
                },
            }
            _macro4_preset_order = [
                "common",
                "nasdaq",
                "nasdaq_meta",
                "nasdaq_meta_stab_1",
                "snp",
                "snp_meta_1",
                "snp_meta_2",
                "snp_meta_stab",
                "snp_meta_stab_2",
                "snp_meta_stab_3",
                "custom",
            ]
            _macro4_preset_options = [k for k in _macro4_preset_order if k in _macro4_presets]
            _macro4_preset_options.extend([k for k in _macro4_presets.keys() if k not in _macro4_preset_options])
            if "macro4_preset" not in st.session_state:
                st.session_state["macro4_preset"] = "snp"

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l39, _l40, _l41, _l42 = st.columns([1.6, 1.2, 2.4, 1.0], vertical_alignment="bottom")
            with _l39:
                st.markdown('<div class="macro2-control-label">조합 프리셋</div>', unsafe_allow_html=True)
            with _l40:
                st.markdown('<div class="macro2-control-label">기준지수</div>', unsafe_allow_html=True)
            with _l41:
                st.markdown('<div class="macro2-control-label">기간</div>', unsafe_allow_html=True)
            with _l42:
                st.markdown('<div class="macro2-control-label">원본선 표시</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m39, _m40, _m41, _m42 = st.columns([1.6, 1.2, 2.4, 1.0], vertical_alignment="bottom")
            with _m39:
                _macro4_preset = st.selectbox(
                    "조합 프리셋",
                    options=_macro4_preset_options,
                    index=_macro4_preset_options.index(st.session_state.get("macro4_preset", "snp")),
                    format_func=lambda x: _macro4_presets[x]["label"],
                    key="macro4_preset",
                    label_visibility="collapsed",
                )
            if st.session_state.get("macro4_preset_applied") != _macro4_preset:
                _preset_cfg = _macro4_presets[_macro4_preset]
                st.session_state["macro4_benchmark"] = _preset_cfg["benchmark"]
                st.session_state["macro4_selected_codes"] = _preset_cfg["selected_codes"]
                st.session_state["macro4_combo_k"] = _preset_cfg["combo_k"]
                for _code, _cfg in _preset_cfg["cfgs"].items():
                    st.session_state[f'macro4_{_code}_ema'] = _cfg["ema"]
                    st.session_state[f'macro4_{_code}_window'] = _cfg["window"]
                    st.session_state[f'macro4_{_code}_start'] = _cfg["start"]
                    st.session_state[f'macro4_{_code}_end'] = _cfg["end"]
                st.session_state["macro4_preset_applied"] = _macro4_preset

            _macro4_preset_cfg = _macro4_presets[_macro4_preset]
            _macro4_is_meta = bool(_macro4_preset_cfg.get("meta"))
            _macro4_selected_default = list(_macro4_preset_cfg["selected_codes"])
            with _m40:
                _benchmark_name4 = st.selectbox("기준지수", options=["S&P500", "Nasdaq"], index=0, label_visibility='collapsed', key='macro4_benchmark', disabled=_macro4_is_meta)
            with _m41:
                _yr_opts4 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro4_years = st.select_slider("기간", options=list(_yr_opts4.keys()), value=3, format_func=lambda x: _yr_opts4[x], label_visibility='collapsed', key='macro4_years')
            with _m42:
                st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
                _show_raw_macro4 = st.checkbox("원본선 표시", value=False, key='macro4_show_raw', label_visibility='collapsed')

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l43, _l44 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _l43:
                st.markdown('<div class="macro2-control-label">조합 지표</div>', unsafe_allow_html=True)
            with _l44:
                st.markdown('<div class="macro2-control-label">리스크 기준</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m43, _m44 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _m43:
                _selected_codes4 = st.multiselect("조합 지표", options=list(_MACRO2_SIGNAL_LABELS.keys()), default=_macro4_selected_default, format_func=lambda x: _MACRO2_SIGNAL_LABELS.get(x, x), key='macro4_selected_codes', label_visibility='collapsed', disabled=_macro4_is_meta)
            with _m44:
                _default_k4 = min(_macro4_preset_cfg["combo_k"], max(1, len(_selected_codes4)))
                _combo_k4 = st.slider("리스크 기준", min_value=1, max_value=max(1, len(_selected_codes4)), value=_default_k4, format="%d개 이상 ON", key='macro4_combo_k', label_visibility='collapsed', disabled=_macro4_is_meta)

            _macro4_cfgs = {}
            if _macro4_is_meta:
                _macro4_cfgs = {k: dict(v) for k, v in _macro4_defaults.items()}
                for _code, _cfg in _macro4_preset_cfg["cfgs"].items():
                    _macro4_cfgs[_code] = dict(_cfg)
                st.caption("메타조합 프리셋은 백테스트 선정값으로 고정되어 있습니다. 아래에는 메타 차트와 하위 조합 A/B 차트를 함께 표시합니다.")
            else:
                with st.expander("▸ 고급 설정: 지표별 EMA / Window / Start / End", expanded=False):
                    for _code, _cfg in _macro4_defaults.items():
                        with st.expander(_cfg["label"], expanded=(_code in _selected_codes4)):
                            _s0, _s1, _s2, _s3 = st.columns(4)
                            with _s0:
                                _ema = st.selectbox("EMA", [10, 20, 30], index=[10, 20, 30].index(_cfg["ema"]), key=f'macro4_{_code}_ema')
                            with _s1:
                                _window = st.selectbox("Rolling Window", [63, 126, 252, 504], index=[63, 126, 252, 504].index(_cfg["window"]), key=f'macro4_{_code}_window')
                            with _s2:
                                _start = st.select_slider("리스크 시작 분위수", options=[x / 100 for x in range(0, 101, 5)], value=_cfg["start"], format_func=lambda x: f"{int(x * 100)}%", key=f'macro4_{_code}_start')
                            with _s3:
                                _end = st.select_slider("리스크 종료 분위수", options=[x / 100 for x in range(0, 101, 5)], value=_cfg["end"], format_func=lambda x: f"{int(x * 100)}%", key=f'macro4_{_code}_end')
                            _macro4_cfgs[_code] = {"ema": int(_ema), "window": int(_window), "start": float(_start), "end": float(_end)}

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg4 = _get_macro_benchmark(_benchmark_name4)
                _spx_s4 = _yf_close(_benchmark_cfg4['code'], _macro4_years, sync_bucket=_macro4_sync_bucket)

            _invalid_macro4 = [f"({_code})" for _code, _cfg in _macro4_cfgs.items() if _cfg["start"] <= _cfg["end"]]
            if _invalid_macro4:
                st.warning(f"리스크 시작 분위수는 종료 분위수보다 높아야 합니다: {' '.join(_invalid_macro4)}")
            elif not _selected_codes4:
                st.warning("조합에 사용할 지표를 최소 1개 이상 선택해 주세요.")
            else:
                with st.spinner("📡 조합 매크로 데이터 로딩 중..."):
                    _macro4_meta_combo_fig = None
                    _macro4_combo_a_fig = None
                    _macro4_combo_b_fig = None
                    if _macro4_is_meta:
                        _meta_cfg = _macro4_preset_cfg["meta"]
                        _combo_a_cfg = _meta_cfg["combo_a"]
                        _combo_b_cfg = _meta_cfg["combo_b"]
                        _macro4_combo_a_fig, _macro4_combo_a_event_df = make_macro_combo_dynamic_chart(
                            years=_macro4_years,
                            spx_s=_spx_s4,
                            benchmark_name=_benchmark_name4,
                            selected_codes=_combo_a_cfg["selected_codes"],
                            cfgs=_combo_a_cfg["cfgs"],
                            combo_k=_combo_a_cfg["combo_k"],
                            sync_bucket=_macro4_sync_bucket,
                            return_debug=True,
                        )
                        _macro4_combo_b_fig, _macro4_combo_b_event_df = make_macro_combo_dynamic_chart(
                            years=_macro4_years,
                            spx_s=_spx_s4,
                            benchmark_name=_benchmark_name4,
                            selected_codes=_combo_b_cfg["selected_codes"],
                            cfgs=_combo_b_cfg["cfgs"],
                            combo_k=_combo_b_cfg["combo_k"],
                            sync_bucket=_macro4_sync_bucket,
                            return_debug=True,
                        )
                        _macro4_combo_fig, _macro4_combo_event_df = make_macro_meta_combo_dynamic_chart(
                            spx_s=_spx_s4,
                            benchmark_name=_benchmark_name4,
                            combo_a_event_df=_macro4_combo_a_event_df,
                            combo_b_event_df=_macro4_combo_b_event_df,
                            combo_a_label=_combo_a_cfg["label"],
                            combo_b_label=_combo_b_cfg["label"],
                            exit_mode=_meta_cfg.get("exit_mode", "AND_EXIT"),
                            start_persist=int(_meta_cfg.get("start_persist", 1)),
                            end_persist=int(_meta_cfg.get("end_persist", 1)),
                            min_hold_days=int(_meta_cfg.get("min_hold_days", 0)),
                            cooldown_days=int(_meta_cfg.get("cooldown_days", 0)),
                            return_debug=True,
                        )
                    else:
                        _macro4_combo_fig, _macro4_combo_event_df = make_macro_combo_dynamic_chart(
                            years=_macro4_years,
                            spx_s=_spx_s4,
                            benchmark_name=_benchmark_name4,
                            selected_codes=_selected_codes4,
                            cfgs=_macro4_cfgs,
                            combo_k=_combo_k4,
                            sync_bucket=_macro4_sync_bucket,
                            return_debug=True,
                        )
                    _macro4_charts = _build_macro2_dynamic_charts(_macro4_years, _spx_s4, _show_raw_macro4, _benchmark_name4, _macro4_cfgs, sync_bucket=_macro4_sync_bucket)

                if _macro4_combo_fig is not None:
                    if _macro4_is_meta:
                        _macro4_status_html, _macro4_status_table_html = _build_macro_meta_combo_status_panel(
                            benchmark_name=_benchmark_name4,
                            years=_macro4_years,
                            spx_s=_spx_s4,
                            meta_event_df=_macro4_combo_event_df,
                            combo_a_event_df=_macro4_combo_a_event_df,
                            combo_b_event_df=_macro4_combo_b_event_df,
                            combo_a_cfg=_combo_a_cfg,
                            combo_b_cfg=_combo_b_cfg,
                            sync_bucket=_macro4_sync_bucket,
                        )
                    else:
                        _macro4_status_html, _macro4_status_table_html = _build_macro_combo_status_panel(
                            benchmark_name=_benchmark_name4,
                            years=_macro4_years,
                            spx_s=_spx_s4,
                            selected_codes=_selected_codes4,
                            combo_event_df=_macro4_combo_event_df,
                            sync_bucket=_macro4_sync_bucket,
                        )
                    if _macro4_status_html:
                        st.markdown(_macro4_status_html, unsafe_allow_html=True)
                    _macro4_bt_summary_html, _macro4_bt_compare_html = _build_macro_meta_backtest_panel(
                        _macro4_preset,
                        preset_defs=_macro4_presets,
                        years=_macro4_years,
                        sync_bucket=_macro4_sync_bucket,
                    )
                    if _macro4_bt_summary_html:
                        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
                        st.markdown(_macro4_bt_summary_html, unsafe_allow_html=True)
                    if _macro4_bt_compare_html:
                        with st.expander("백테스트 비교 보기", expanded=False):
                            st.markdown(_macro4_bt_compare_html, unsafe_allow_html=True)
                    if _macro4_status_table_html:
                        st.markdown('<div style="height:18px;"></div>', unsafe_allow_html=True)
                        with st.expander("지표별 상태 보기", expanded=False):
                            st.markdown(_macro4_status_table_html, unsafe_allow_html=True)
                            _macro4_whipsaw_caption_map = {
                                "nasdaq_meta_stab_1": "휩쏘제거 파라미터: 시작 1거래일 연속 ON, 종료 1거래일 연속 AND_EXIT, 최소보유 5일, 쿨다운 0일",
                                "snp_meta_stab": "휩쏘제거 파라미터: 시작 10거래일 연속 ON, 종료 2거래일 연속 AND_EXIT, 최소보유 0일, 쿨다운 0일",
                                "snp_meta_stab_2": "휩쏘제거 파라미터: 시작 1거래일 연속 ON, 종료 2거래일 연속 AND_EXIT, 최소보유 15일, 쿨다운 15일",
                                "snp_meta_stab_3": "휩쏘제거 파라미터: 시작 1거래일 연속 ON, 종료 4거래일 연속 AND_EXIT, 최소보유 10일, 쿨다운 15일",
                            }
                            _macro4_whipsaw_caption = _macro4_whipsaw_caption_map.get(_macro4_preset)
                            if _macro4_whipsaw_caption:
                                st.caption(_macro4_whipsaw_caption)
                    st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
                    st.plotly_chart(_macro4_combo_fig, width="stretch", config={"displayModeBar": False}, key=f"macro4_combo_{_macro4_preset}_{_benchmark_name4}_{_macro4_years}_{'_'.join(_selected_codes4)}_{_combo_k4}_{_macro_dynamic_cfg_signature(_macro4_cfgs, _selected_codes4)}")
                    if _macro4_is_meta:
                        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
                        with st.expander("조합 1-A 차트", expanded=True):
                            if _macro4_combo_a_fig is not None:
                                st.plotly_chart(
                                    _macro4_combo_a_fig,
                                    width="stretch",
                                    config={"displayModeBar": False},
                                    key=f"macro4_combo_a_{_benchmark_name4}_{_macro4_years}",
                                )
                        with st.expander("조합 1-B 차트", expanded=True):
                            if _macro4_combo_b_fig is not None:
                                st.plotly_chart(
                                    _macro4_combo_b_fig,
                                    width="stretch",
                                    config={"displayModeBar": False},
                                    key=f"macro4_combo_b_{_benchmark_name4}_{_macro4_years}",
                                )
                else:
                    st.warning("조합 리스크 차트 데이터 로딩 실패 — 조합 지표/기간을 확인해 주세요.")

                _macro4_chart_codes = ["0", "1", "2", "3", "4", "6"]
                for _idx, (_code, _fig) in enumerate(zip(_macro4_chart_codes, _macro4_charts)):
                    _label = _MACRO2_SIGNAL_LABELS.get(_code, _code)
                    with st.expander(_label, expanded=((_code in _selected_codes4) and not _macro4_is_meta)):
                        if _fig is not None:
                            st.plotly_chart(
                                _fig,
                                width="stretch",
                                config={"displayModeBar": False},
                                key=f"macro4_chart_{_idx}_{_code}_{_benchmark_name4}_{_macro4_years}_{_macro_dynamic_cfg_signature(_macro4_cfgs, [_code for _code in _MACRO2_SIGNAL_LABELS.keys() if _code in _macro4_cfgs])}"
                            )
                        else:
                            st.warning("개별 실험 차트 데이터 로딩 실패 — 잠시 후 다시 시도해 주세요.")
                _macro_debug_log(
                    "render_macro4_combo_section",
                    preset_key=_macro4_preset,
                    benchmark_name=_benchmark_name4,
                    years=_macro4_years,
                    selected_codes=len(_selected_codes4),
                    is_meta=_macro4_is_meta,
                    elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
                )

    def render_macro5_kospi_section(container):
        with container:
            _started = time.perf_counter()
            st.markdown(
                '<div class="macro2-helper-text">KOSPI 후보를 최신 데이터로 판단하고 공식 백테스트 결과와 비교합니다.</div>',
                unsafe_allow_html=True,
            )
            _render_macro_combo_common_css()
            st.markdown("""
            <style>
            .st-key-macro5_kospi_preset div[data-baseweb="select"] > div,
            .st-key-macro5_kospi_benchmark div[data-baseweb="select"] > div,
            .st-key-macro5_kospi_selected_codes div[data-baseweb="select"] > div,
            .st-key-macro5_kospi_years div[data-baseweb="slider"] + div,
            .st-key-macro5_kospi_show_raw label,
            .st-key-macro5_kospi_show_raw span,
            .st-key-macro5_kospi_show_raw p {
                font-size: 13.5px !important;
                color: rgba(255,255,255,0.92) !important;
            }
            .st-key-macro5_kospi_preset div[data-baseweb="select"] > div,
            .st-key-macro5_kospi_benchmark div[data-baseweb="select"] > div,
            .st-key-macro5_kospi_selected_codes div[data-baseweb="select"] > div {
                min-height: 2.55rem;
                border-color: rgba(95,86,214,0.72) !important;
                background: rgba(52,44,112,0.22) !important;
                box-shadow: none !important;
            }
            .st-key-macro5_kospi_selected_codes [data-baseweb="tag"] {
                background: rgba(92,79,214,0.96) !important;
                color: #F6F4FF !important;
                min-height: 24px !important;
                height: 24px !important;
                padding: 2px 8px !important;
                border-radius: 6px !important;
                line-height: 1.2 !important;
                gap: 4px !important;
                align-items: center !important;
            }
            .st-key-macro5_kospi_selected_codes [data-baseweb="tag"] span {
                font-size: 11.5px !important;
                line-height: 1.2 !important;
            }
            .st-key-macro5_kospi_selected_codes [data-baseweb="tag"] svg {
                width: 12px !important;
                height: 12px !important;
            }
            .st-key-macro5_kospi_show_raw [data-baseweb="checkbox"] > div {
                border-color: rgba(95,86,214,0.78) !important;
            }
            .st-key-macro5_kospi_preset,
            .st-key-macro5_kospi_benchmark,
            .st-key-macro5_kospi_years,
            .st-key-macro5_kospi_show_raw,
            .st-key-macro5_kospi_selected_codes {
                margin-top: 0 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            try:
                _assets5k = _load_macro5_kospi_frozen_assets()
            except Exception as _exc:
                st.error(f"KOSPI Macro5 Frozen 자산을 불러오지 못했습니다: {_exc}")
                return

            _metrics5k = _macro5_kospi_sort_metrics(_assets5k["metrics"])
            _signals5k = _assets5k["signals"]
            _components5k = _assets5k["components"]
            _benchmark5k = _assets5k["benchmark"]
            _snapshot5k = _assets5k["snapshot"]
            _manifest5k = _assets5k["manifest"]
            _ui_manifest5k = _assets5k["ui_manifest"]
            _component_dict5k = _assets5k["component_dictionary"]
            try:
                _default_preset5k = _macro5_kospi_combo2_main_candidate_id(_metrics5k)
            except ValueError as _exc:
                st.error(str(_exc))
                return
            _metrics5k["_model_type_norm"] = _metrics5k["model_type"].map(_macro5_kospi_model_type)
            _combo2_order5k = _metrics5k[_metrics5k["_model_type_norm"].eq("combo2")]["candidate_id"].tolist()
            _combo1_order5k = _metrics5k[_metrics5k["_model_type_norm"].eq("combo1")]["candidate_id"].tolist()
            _backtest_stats5k = _macro5_kospi_build_backtest_stats(_metrics5k, _signals5k, _benchmark5k)
            _separator5k = "__macro5_kospi_combo1_separator__"
            _preset_order5k = _combo2_order5k + _combo1_order5k
            _candidate_map5k = {row["candidate_id"]: row for _, row in _metrics5k.iterrows()}
            _live5k = None
            _live_error5k = ""
            _live_sync_bucket5k = _macro_sync_bucket(60)
            try:
                _live5k = _load_macro5_kospi_live_page_data_cached(_live_sync_bucket5k)
            except Exception as _exc:
                _live_error5k = str(_exc)
            _live_row_map5k = {}
            if isinstance(_live5k, dict):
                _live_row_map5k = {str(row.get("candidate_id")): row for row in _live5k.get("candidate_rows", [])}
            if st.session_state.get("macro5_kospi_preset") == _separator5k:
                st.session_state["macro5_kospi_preset"] = _combo1_order5k[0] if _combo1_order5k else _default_preset5k
            if st.session_state.get("macro5_kospi_preset") not in _preset_order5k:
                st.session_state["macro5_kospi_preset"] = _default_preset5k

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                _macro5_kospi_group_summary_html(
                    _live5k.get("candidate_rows", []) if isinstance(_live5k, dict) else [],
                    _metrics5k,
                ),
                unsafe_allow_html=True,
            )

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l51, _l52, _l53, _l54 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            with _l51:
                st.markdown('<div class="macro2-control-label">조합 프리셋</div>', unsafe_allow_html=True)
            with _l52:
                st.markdown('<div class="macro2-control-label">기준지수</div>', unsafe_allow_html=True)
            with _l53:
                st.markdown('<div class="macro2-control-label">기간</div>', unsafe_allow_html=True)
            with _l54:
                st.markdown('<div class="macro2-control-label">보조선 표시</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m51, _m52, _m53, _m54 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            _preset_options5k = _combo2_order5k + [_separator5k] + _combo1_order5k
            _current_preset5k = st.session_state["macro5_kospi_preset"]
            if _current_preset5k not in _preset_options5k:
                _current_preset5k = _default_preset5k
            with _m51:
                _macro5_kospi_preset = st.selectbox(
                    "조합 프리셋",
                    options=_preset_options5k,
                    index=_preset_options5k.index(_current_preset5k),
                    format_func=lambda x: (
                        "──────── 조합1 ────────"
                        if x == _separator5k
                        else _macro5_kospi_preset_label(
                            _candidate_map5k[x],
                            len(_component_dict5k.get(x, {}).get("component_ids", [])),
                        )
                    ),
                    key="macro5_kospi_preset",
                    label_visibility="collapsed",
                )
            if _macro5_kospi_preset == _separator5k:
                _macro5_kospi_preset = _combo1_order5k[0] if _combo1_order5k else _default_preset5k
            _selected_row5k = _candidate_map5k[_macro5_kospi_preset]
            _selected_components5k = _component_dict5k[_macro5_kospi_preset]["component_ids"]
            if list(st.session_state.get("macro5_kospi_selected_codes", [])) != list(_selected_components5k):
                st.session_state["macro5_kospi_selected_codes"] = list(_selected_components5k)
            _period_candidate_signal5k = _signals5k[_signals5k["candidate_id"] == _macro5_kospi_preset].copy()
            _period_component_signal5k = _components5k[_components5k["parent_candidate_id"] == _macro5_kospi_preset].copy()
            _period_live_row5k = _live_row_map5k.get(_macro5_kospi_preset, {})
            _period_basis_date5k = (
                _period_live_row5k.get("basis_date")
                if isinstance(_period_live_row5k, dict) and _period_live_row5k.get("basis_date")
                else (
                    pd.to_datetime(_period_candidate_signal5k["date"]).max()
                    if not _period_candidate_signal5k.empty
                    else pd.to_datetime(_benchmark5k["date"]).max()
                )
            )
            _period_options5k, _period_common_start5k = _macro5_kospi_available_period_options(
                _benchmark5k,
                _period_candidate_signal5k,
                _period_component_signal5k,
                basis_date=_period_basis_date5k,
            )
            _current_period5k = st.session_state.get("macro5_kospi_years", 5)
            if _current_period5k == 20 or str(_current_period5k) == "20" or _current_period5k not in _period_options5k:
                _current_period5k = "all" if "all" in _period_options5k else _period_options5k[-1]
                st.session_state["macro5_kospi_years"] = _current_period5k
            with _m52:
                st.selectbox("기준지수", options=["KOSPI"], index=0, key="macro5_kospi_benchmark", label_visibility="collapsed", disabled=True)
            with _m53:
                _macro5_kospi_years = st.select_slider(
                    "기간",
                    options=_period_options5k,
                    value=_current_period5k,
                    format_func=_macro5_kospi_period_label,
                    key="macro5_kospi_years",
                    label_visibility="collapsed",
                )
            with _m54:
                st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
                _show_raw_macro5_kospi = st.checkbox("보조선 표시", value=False, key="macro5_kospi_show_raw", label_visibility="collapsed")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l55, _l56 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _l55:
                st.markdown('<div class="macro2-control-label">조합 지표</div>', unsafe_allow_html=True)
            with _l56:
                st.markdown('<div class="macro2-control-label">리스크 기준</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m55, _m56 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _m55:
                st.multiselect(
                    "조합 지표",
                    options=_selected_components5k,
                    default=_selected_components5k,
                    format_func=lambda x: _macro5_kospi_component_display_label(x, _candidate_map5k, _component_dict5k),
                    key="macro5_kospi_selected_codes",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with _m56:
                st.markdown(
                    (
                        "<div style='padding-top:8px;font-size:11.5px;line-height:1.42;color:rgba(255,255,255,0.84);'>"
                        f"시작 {int(_selected_row5k['K'])}개 이상 ON<br>"
                        f"종료 {int(_selected_row5k['L'])}개 이하 ON"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _candidate_signal5k = _signals5k[_signals5k["candidate_id"] == _macro5_kospi_preset].copy()
            _candidate_signal5k = _macro5_kospi_with_events(_candidate_signal5k)
            _state_span5k = _macro5_kospi_current_state_span(
                _candidate_signal5k,
                _backtest_stats5k.get("window", {}).get("frozen_start", "2008-04-01"),
            )
            _latest_signal5k = _candidate_signal5k.sort_values("date").iloc[-1]
            _latest_date5k = pd.to_datetime(_latest_signal5k["date"])
            _candidate_components5k = _components5k[_components5k["parent_candidate_id"] == _macro5_kospi_preset].copy()
            _latest_components5k = _candidate_components5k[_candidate_components5k["date"] == _latest_date5k]
            _active_count5k = int(_latest_components5k["component_risk_state"].fillna(0).astype(int).sum()) if len(_latest_components5k) else 0
            _last_transition_rows5k = _candidate_signal5k[_candidate_signal5k["raw_risk_state"].ne(_candidate_signal5k["raw_risk_state"].shift(1))]
            _last_transition_date5k = pd.to_datetime(_last_transition_rows5k.iloc[-1]["date"]) if len(_last_transition_rows5k) else _latest_date5k
            _duration5k = int((_candidate_signal5k["date"] >= _last_transition_date5k).sum())
            _reference_label5k = _macro5_kospi_reference_label(_selected_row5k["source_signal_parity"])
            _live_history_ready5k = bool(
                isinstance(_live5k, dict)
                and isinstance(_live5k.get("candidate_signal_history"), pd.DataFrame)
                and isinstance(_live5k.get("component_signal_history"), pd.DataFrame)
                and isinstance(_live5k.get("benchmark_close_history"), pd.DataFrame)
                and not _live5k["candidate_signal_history"].empty
                and not _live5k["component_signal_history"].empty
                and not _live5k["benchmark_close_history"].empty
            )
            _live_selected5k = _live_row_map5k.get(_macro5_kospi_preset)
            _live_selected_ok5k = bool(_live_selected5k and _live_selected5k.get("calculable") and _live_history_ready5k)
            if _live_selected_ok5k:
                _live_candidate_history5k = _live5k["candidate_signal_history"][
                    _live5k["candidate_signal_history"]["candidate_id"] == _macro5_kospi_preset
                ].copy()
                if not _live_candidate_history5k.empty:
                    _state_span5k = _macro5_kospi_current_state_span(
                        _live_candidate_history5k,
                        _backtest_stats5k.get("window", {}).get("frozen_start", "2008-04-01"),
                    )
            _current_component_status5k = _latest_components5k
            if _live_history_ready5k:
                _current_component_status5k = _live5k["component_signal_history"][
                    _live5k["component_signal_history"]["parent_candidate_id"] == _macro5_kospi_preset
                ].copy()
            st.markdown(
                _macro5_kospi_current_status_html(
                    _selected_row5k,
                    _live_selected5k,
                    len(_selected_components5k),
                    _live_selected_ok5k,
                    _macro5_kospi_active_label_list(_current_component_status5k, candidate_map=_candidate_map5k, component_dict=_component_dict5k),
                    _state_span5k.get("state_start_text"),
                    _state_span5k.get("duration_text"),
                ),
                unsafe_allow_html=True,
            )
            if not _live_selected_ok5k:
                st.warning(f"Live 상태를 계산할 수 없습니다: {(_live_error5k or 'Live history unavailable')[:180]}")

            _bt_metrics5k = [
                ("CAGR", _macro5_kospi_fmt_pct(_selected_row5k["cagr"])),
                ("MDD", _macro5_kospi_fmt_pct(_selected_row5k["mdd"])),
                ("Calmar", _macro5_kospi_fmt_num(_selected_row5k["calmar"])),
                ("Risk-off", _macro5_kospi_fmt_pct(_selected_row5k["risk_off_ratio"])),
                ("연 전환", _macro5_kospi_fmt_num(_selected_row5k["annual_turnover"])),
                ("n/m", int(_selected_row5k["m_or_n"])),
            ]

            _combo2_bt5k = _macro5_kospi_build_backtest_panel(_metrics5k, _live_row_map5k, _macro5_kospi_preset, "combo2", _backtest_stats5k)
            _combo1_bt5k = _macro5_kospi_build_backtest_panel(_metrics5k, _live_row_map5k, _macro5_kospi_preset, "combo1", _backtest_stats5k)
            if _combo2_bt5k:
                with st.expander("백테스트 비교 보기 · 조합2", expanded=False):
                    st.markdown(_combo2_bt5k, unsafe_allow_html=True)
            if _combo1_bt5k:
                with st.expander("백테스트 비교 보기 · 조합1", expanded=False):
                    st.markdown(_combo1_bt5k, unsafe_allow_html=True)

            _status5k = _snapshot5k.copy()
            _status5k["date"] = "계산 불가"
            _status5k["raw_risk_state"] = pd.NA
            _status5k["t1_position"] = pd.NA
            _status5k["active_count"] = pd.NA
            _status5k["last_transition_date"] = "계산 불가"
            _status5k["current_state_trading_days"] = pd.NA
            _status5k["valid"] = False
            _status5k["freshness_qualified"] = False
            _status5k["freshness_status"] = "계산 불가"
            for _row_idx5k, _row5k in _status5k.iterrows():
                _live_row5k = _live_row_map5k.get(str(_row5k.get("candidate_id")))
                if not _live_row5k or not _live_row5k.get("calculable"):
                    continue
                _status5k.loc[_row_idx5k, "date"] = _live_row5k.get("basis_date")
                _status5k.loc[_row_idx5k, "raw_risk_state"] = _live_row5k.get("raw_risk_state")
                _status5k.loc[_row_idx5k, "t1_position"] = _live_row5k.get("t1_position")
                _status5k.loc[_row_idx5k, "active_count"] = _live_row5k.get("active_count")
                _status5k.loc[_row_idx5k, "last_transition_date"] = _live_row5k.get("current_state_start_date")
                _status5k.loc[_row_idx5k, "current_state_trading_days"] = _live_row5k.get("current_state_trading_days")
                _status5k.loc[_row_idx5k, "valid"] = True
                _status5k.loc[_row_idx5k, "freshness_qualified"] = bool(_live_row5k.get("freshness_qualified"))
                _status5k.loc[_row_idx5k, "freshness_status"] = _live_row5k.get("freshness_status")
            with st.expander("지표별 상태 보기", expanded=False):
                _selected_component_status5k = _components5k[_components5k["parent_candidate_id"] == _macro5_kospi_preset].copy()
                if _live_history_ready5k:
                    _selected_component_status5k = _live5k["component_signal_history"][
                        _live5k["component_signal_history"]["parent_candidate_id"] == _macro5_kospi_preset
                    ].copy()
                _component_status_html5k = _macro5_kospi_build_component_status_panel(
                    _selected_component_status5k,
                    _live5k.get("source_rows", []) if isinstance(_live5k, dict) else [],
                    _live_row_map5k,
                    str(_selected_row5k["model_type"]),
                    _candidate_map5k,
                    _component_dict5k,
                )
                if _component_status_html5k:
                    st.markdown(_component_status_html5k, unsafe_allow_html=True)
                else:
                    st.caption("선택 후보 구성요소 상태를 표시할 수 없습니다.")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            if _live_history_ready5k:
                _signals5k = _live5k["candidate_signal_history"].copy()
                _components5k = _live5k["component_signal_history"].copy()
                _benchmark5k = _live5k["benchmark_close_history"].copy()
                for _history5k in (_signals5k, _components5k, _benchmark5k):
                    if "date" in _history5k.columns:
                        _history5k["date"] = pd.to_datetime(_history5k["date"])
                _candidate_signal5k = _signals5k[_signals5k["candidate_id"] == _macro5_kospi_preset].copy()
                _candidate_signal5k = _macro5_kospi_with_events(_candidate_signal5k)
                _candidate_components5k = _components5k[_components5k["parent_candidate_id"] == _macro5_kospi_preset].copy()
            else:
                _candidate_signal5k = pd.DataFrame()
                _candidate_components5k = pd.DataFrame()
                _benchmark5k = pd.DataFrame()
            _chart_basis_date5k = (
                _live_selected5k.get("basis_date")
                if isinstance(_live_selected5k, dict) and _live_selected5k.get("basis_date")
                else _latest_date5k
            )
            _chart_source_base5k = (
                _live5k.get("transformed_source_history")
                if isinstance(_live5k, dict) and isinstance(_live5k.get("transformed_source_history"), pd.DataFrame)
                else _macro5_kospi_load_transformed_source_cached()
            )
            _chart_label5k = _macro5_kospi_preset_label(_selected_row5k, len(_selected_components5k))
            _main_fig5k = _macro5_kospi_build_main_chart(
                _candidate_signal5k,
                _benchmark5k,
                _chart_label5k,
                _macro5_kospi_years,
                _show_raw_macro5_kospi,
                basis_date=_chart_basis_date5k,
                common_start=_period_common_start5k,
            )
            if _main_fig5k is not None:
                st.plotly_chart(
                    _main_fig5k,
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"macro5_kospi_main_chart_{_macro5_kospi_preset}_{_macro5_kospi_years}_{int(_show_raw_macro5_kospi)}",
                )
            else:
                st.warning("최신 대표 차트를 표시할 수 없습니다.")

            for _idx5k, (_component_id5k, _component_df5k) in enumerate(_candidate_components5k.groupby("component_id", sort=False), start=1):
                if str(_component_id5k) in _candidate_map5k:
                    _component_label5k = _macro5_kospi_component_display_label(str(_component_id5k), _candidate_map5k, _component_dict5k)
                else:
                    _component_label5k = _component_df5k["component_label"].dropna().iloc[0] if "component_label" in _component_df5k and len(_component_df5k["component_label"].dropna()) else _macro5_kospi_suffix(_component_id5k)
                with st.expander(f"{_idx5k}. {_component_label5k}", expanded=True):
                    _component_fig5k = _macro5_kospi_build_component_chart(
                        _component_df5k,
                        _benchmark5k,
                        str(_component_label5k),
                        _macro5_kospi_years,
                        model_type=str(_selected_row5k["model_type"]),
                        source_base=_chart_source_base5k,
                        show_aux=bool(_show_raw_macro5_kospi),
                        basis_date=_chart_basis_date5k,
                        common_start=_period_common_start5k,
                    )
                    if _component_fig5k is not None:
                        st.plotly_chart(
                            _component_fig5k,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro5_kospi_component_chart_{_macro5_kospi_preset}_{_idx5k}_{_macro5_kospi_years}",
                        )
                    else:
                        st.warning("component state 차트 데이터가 없습니다.")

            with st.expander("고급 설정 · 모델 및 데이터 정보", expanded=False):
                st.write(f"candidate_id: `{_macro5_kospi_preset}`")
                st.write(f"slot: `{int(_selected_row5k['slot'])}`")
                st.write(f"suffix: `{_selected_row5k['suffix']}`")
                st.write(f"reference source: `{_reference_label5k}`")
                st.write(f"signal hash: `{_selected_row5k['reference_signal_hash']}`")
                st.write(f"D1-A manifest: `{_assets5k['manifest_sha256']}`")
                st.write(f"D1-B UI manifest: `{_assets5k['ui_manifest_sha256']}`")
                st.write("공식 Frozen 백테스트: `2008-04-01 ~ 2026-07-28 · T+1 · 10bp · 현금수익 미적용`")
                for _label5k, _value5k in _bt_metrics5k:
                    st.write(f"{_label5k}: `{_value5k}`")
                st.write("Final9 다수결 신호는 생성하지 않습니다.")

            _macro_debug_log(
                "render_macro5_kospi_section",
                candidate_id=_macro5_kospi_preset,
                years=_macro5_kospi_years,
                component_count=len(_selected_components5k),
                frozen_end=_latest_date5k.strftime("%Y-%m-%d"),
                live_connected=bool(_live_selected_ok5k),
                d1a_gate=_manifest5k.get("gate"),
                d1b_gate=_ui_manifest5k.get("gate"),
                elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
            )


    def render_macro5_final8_section(container):
        with container:
            _started = time.perf_counter()
            st.markdown(
                '<div class="macro2-helper-text">S&P 최종 후보를 최신 Yahoo/FRED 데이터와 백테스트 availability 정책으로 재계산해 비교합니다.</div>',
                unsafe_allow_html=True,
            )
            _macro5_sync_bucket = _macro_sync_bucket(60)
            _render_macro_combo_common_css()
            st.markdown("""
            <style>
            .st-key-macro5_preset div[data-baseweb="select"] > div,
            .st-key-macro5_benchmark div[data-baseweb="select"] > div,
            .st-key-macro5_selected_codes div[data-baseweb="select"] > div,
            .st-key-macro5_years div[data-baseweb="slider"] + div,
            .st-key-macro5_show_raw label,
            .st-key-macro5_show_raw span,
            .st-key-macro5_show_raw p {
                font-size: 12px !important;
                line-height: 1.35 !important;
                color: rgba(255,255,255,0.92) !important;
            }
            .st-key-macro5_preset div[data-baseweb="select"] > div,
            .st-key-macro5_benchmark div[data-baseweb="select"] > div,
            .st-key-macro5_selected_codes div[data-baseweb="select"] > div {
                min-height: 2.35rem;
                border-color: rgba(95,86,214,0.72) !important;
                background: rgba(52,44,112,0.22) !important;
                box-shadow: none !important;
                line-height: 1.32 !important;
            }
            .st-key-macro5_selected_codes [data-baseweb="tag"] {
                background: rgba(92,79,214,0.96) !important;
                color: #F6F4FF !important;
                font-size: 11px !important;
                line-height: 1.25 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            _macro5_presets = _load_macro3_final8_presets()
            if not _macro5_presets:
                st.warning("Final8 프리셋 파일을 찾지 못했습니다.")
                return
            _macro5_blocking = {key: _macro3_preset_blocking_reasons(value) for key, value in _macro5_presets.items()}
            _macro5_group_status_sa = _macro3_group_availability_html(
                "S·A급",
                _MACRO3_BACKTEST_GROUP_SA,
                _macro5_presets,
                _macro5_blocking,
            )
            _macro5_group_status_bcd = _macro3_group_availability_html(
                "B·C·D급",
                _MACRO3_BACKTEST_GROUP_BCD,
                _macro5_presets,
                _macro5_blocking,
            )
            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="macro2-helper-text">
                    {_macro5_group_status_sa}
                    <span style="color:rgba(255,255,255,0.36);padding:0 8px;">|</span>
                    {_macro5_group_status_bcd}
                </div>
                """,
                unsafe_allow_html=True,
            )

            _macro5_preset_order = list(_macro5_presets.keys())
            if st.session_state.get("macro5_preset") not in _macro5_preset_order:
                st.session_state["macro5_preset"] = _macro5_preset_order[0]

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l51, _l52, _l53, _l54 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            with _l51:
                st.markdown('<div class="macro2-control-label">조합 프리셋</div>', unsafe_allow_html=True)
            with _l52:
                st.markdown('<div class="macro2-control-label">기준지수</div>', unsafe_allow_html=True)
            with _l53:
                st.markdown('<div class="macro2-control-label">기간</div>', unsafe_allow_html=True)
            with _l54:
                st.markdown('<div class="macro2-control-label">보조선 표시</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m51, _m52, _m53, _m54 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            with _m51:
                _macro5_preset = st.selectbox(
                    "조합 프리셋",
                    options=_macro5_preset_order,
                    index=_macro5_preset_order.index(st.session_state["macro5_preset"]),
                    format_func=lambda x: _macro5_presets[x]["label"],
                    key="macro5_preset",
                    label_visibility="collapsed",
                )
            _macro5_preset_cfg = _macro5_presets[_macro5_preset]
            _macro5_is_combo2 = _macro5_preset_cfg.get("kind") == "combo2_final8" or bool(_macro5_preset_cfg.get("components"))
            with _m52:
                st.selectbox(
                    "기준지수",
                    options=["S&P500"],
                    index=0,
                    key="macro5_benchmark",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with _m53:
                _yr_opts5 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro5_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts5.keys()),
                    value=5,
                    format_func=lambda x: _yr_opts5[x],
                    key="macro5_years",
                    label_visibility="collapsed",
                )
            with _m54:
                st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
                _show_raw_macro5 = st.checkbox("보조선 표시", value=False, key="macro5_show_raw", label_visibility="collapsed")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l55, _l56 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _l55:
                st.markdown('<div class="macro2-control-label">조합 지표</div>', unsafe_allow_html=True)
            with _l56:
                st.markdown('<div class="macro2-control-label">리스크 기준</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m55, _m56 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _m55:
                _macro5_options = _macro5_preset_cfg.get("components", []) if _macro5_is_combo2 else _MACRO3_INDICATOR_ORDER
                _macro5_default = _macro5_preset_cfg.get("components", []) if _macro5_is_combo2 else _macro5_preset_cfg["selected_indicators"]
                if list(st.session_state.get("macro5_selected_codes", [])) != list(_macro5_default):
                    st.session_state["macro5_selected_codes"] = list(_macro5_default)
                st.multiselect(
                    "조합 지표",
                    options=_macro5_options,
                    default=_macro5_default,
                    format_func=lambda x: _macro3_component_label(x, _macro5_preset_cfg.get("component_cfgs", {}).get(x)) if _macro5_is_combo2 else _MACRO3_INDICATOR_LABELS.get(x, x),
                    key="macro5_selected_codes",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with _m56:
                st.markdown(
                    (
                        "<div style='padding-top:8px;font-size:11.5px;line-height:1.42;color:rgba(255,255,255,0.84);'>"
                        f"시작 {int(_macro5_preset_cfg.get('combo_k', 1))}개 이상 ON<br>"
                        f"종료 {int(_macro5_preset_cfg.get('combo_l', 0))}개 이하 ON"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

            _macro5_selected_blocking = _macro5_blocking.get(_macro5_preset, [])
            if _macro5_selected_blocking:
                st.warning("선택한 후보는 계산 불가 상태입니다.")
                with st.expander("계산 불가 사유", expanded=True):
                    for _reason in _macro5_selected_blocking:
                        st.write(f"- {_reason}")
                return

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _spx_s5 = _macro3_filter_confirmed_us_daily(_yf_close("^GSPC", _macro5_years, sync_bucket=_macro5_sync_bucket))
            if _spx_s5 is None or _spx_s5.empty:
                st.warning("기준 지수 데이터를 불러오지 못했습니다.")
                return

            with st.spinner("📡 Final8 후보 데이터 로딩 중..."):
                _macro5_combo_fig, _macro5_combo_event_df = make_macro3_combo_dynamic_chart(
                    years=_macro5_years,
                    benchmark_name="S&P500",
                    preset_cfg=_macro5_preset_cfg,
                    return_debug=True,
                    sync_bucket=_macro5_sync_bucket,
                )
                if _macro5_is_combo2:
                    _macro5_indicator_charts = {
                        _component: _build_macro3_component_chart(
                            component_key=_component,
                            years=_macro5_years,
                            benchmark_name="S&P500",
                            preset_cfg=_macro5_preset_cfg,
                            spx_s=_spx_s5,
                            sync_bucket=_macro5_sync_bucket,
                        )
                        for _component in _macro5_preset_cfg.get("components", [])
                    }
                else:
                    _macro5_indicator_charts = {
                        _indicator: _build_macro3_indicator_chart(
                            indicator=_indicator,
                            years=_macro5_years,
                            benchmark_name="S&P500",
                            preset_cfg=_macro5_preset_cfg,
                            spx_s=_spx_s5,
                            show_raw=_show_raw_macro5,
                            sync_bucket=_macro5_sync_bucket,
                        )
                        for _indicator in _MACRO3_INDICATOR_ORDER
                    }

            if _macro5_combo_fig is None:
                st.warning("선택한 Final8 후보 차트를 만들지 못했습니다. 데이터 지연 또는 필수 지표 누락 여부를 확인해 주세요.")
                return

            _macro5_status_html, _macro5_status_table_html = _build_macro3_status_panel(
                benchmark_name="S&P500",
                years=_macro5_years,
                preset_cfg=_macro5_preset_cfg,
                combo_event_df=_macro5_combo_event_df,
                sync_bucket=_macro5_sync_bucket,
            )
            if _macro5_status_html:
                st.markdown(_macro5_status_html, unsafe_allow_html=True)

            _, _macro5_bt_compare_sa_html = _build_macro3_backtest_panel(
                _macro5_preset,
                preset_defs=_macro5_presets,
                years=_macro5_years,
                sync_bucket=_macro5_sync_bucket,
                preset_order=_MACRO3_BACKTEST_GROUP_SA,
            )
            _, _macro5_bt_compare_bcd_html = _build_macro3_backtest_panel(
                _macro5_preset,
                preset_defs=_macro5_presets,
                years=_macro5_years,
                sync_bucket=_macro5_sync_bucket,
                preset_order=_MACRO3_BACKTEST_GROUP_BCD,
            )
            if _macro5_bt_compare_sa_html:
                with st.expander("백테스트 비교 보기 S·A급", expanded=False):
                    st.markdown(_macro5_bt_compare_sa_html, unsafe_allow_html=True)
            if _macro5_bt_compare_bcd_html:
                with st.expander("백테스트 비교 보기 B·C·D급", expanded=False):
                    st.markdown(_macro5_bt_compare_bcd_html, unsafe_allow_html=True)

            if _macro5_status_table_html:
                with st.expander("지표별 상태 보기", expanded=False):
                    st.markdown(_macro5_status_table_html, unsafe_allow_html=True)
                    if _macro5_preset_cfg.get("selection_reason"):
                        st.caption(f"선정 이유: {_macro5_preset_cfg['selection_reason']}")
                    if _macro5_preset_cfg.get("dashboard_review_focus"):
                        st.caption(f"대시보드 확인 포인트: {_macro5_preset_cfg['dashboard_review_focus']}")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            st.plotly_chart(
                _macro5_combo_fig,
                width="stretch",
                config={"displayModeBar": False},
                key=f"macro5_combo_{_macro5_preset}_{_macro5_years}",
            )
            _macro5_detail_items = _macro5_preset_cfg.get("components", []) if _macro5_is_combo2 else _MACRO3_INDICATOR_ORDER
            for _indicator in _macro5_detail_items:
                _fig = _macro5_indicator_charts.get(_indicator)
                _expanded = True if _macro5_is_combo2 else _indicator in _macro5_preset_cfg["selected_indicators"]
                _label = _macro3_component_label(_indicator, _macro5_preset_cfg.get("component_cfgs", {}).get(_indicator)) if _macro5_is_combo2 else _MACRO3_INDICATOR_LABELS.get(_indicator, _indicator)
                with st.expander(_label, expanded=_expanded):
                    if _fig is not None:
                        st.plotly_chart(
                            _fig,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro5_chart_{_macro5_preset}_{_macro5_years}_{_macro3_indicator_key(_indicator)}",
                        )
                    else:
                        st.caption("이 후보에서는 사용되지 않거나 차트 데이터가 없습니다.")

            _macro_debug_log(
                "render_macro5_final8_section",
                preset_key=_macro5_preset,
                years=_macro5_years,
                elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
            )

    def render_macro6_proxy_final_section(container):
        with container:
            _started = time.perf_counter()
            st.markdown(
                '<div class="macro2-helper-text">Proxy-only 신용지표 기준 사용자 선택 완료·운영 미승인 후보를 최신 Yahoo/FRED 데이터와 백테스트 availability 정책으로 재계산해 비교합니다.</div>',
                unsafe_allow_html=True,
            )
            _macro6_sync_bucket = _macro_sync_bucket(60)
            _render_macro_combo_common_css()
            st.markdown("""
            <style>
            .st-key-macro6_preset div[data-baseweb="select"] > div,
            .st-key-macro6_benchmark div[data-baseweb="select"] > div,
            .st-key-macro6_selected_codes div[data-baseweb="select"] > div,
            .st-key-macro6_years div[data-baseweb="slider"] + div,
            .st-key-macro6_show_raw label,
            .st-key-macro6_show_raw span,
            .st-key-macro6_show_raw p {
                font-size: 12px !important;
                line-height: 1.35 !important;
                color: rgba(255,255,255,0.92) !important;
            }
            .st-key-macro6_preset div[data-baseweb="select"] > div,
            .st-key-macro6_benchmark div[data-baseweb="select"] > div,
            .st-key-macro6_selected_codes div[data-baseweb="select"] > div {
                min-height: 2.35rem;
                border-color: rgba(95,86,214,0.72) !important;
                background: rgba(52,44,112,0.22) !important;
                box-shadow: none !important;
                line-height: 1.32 !important;
            }
            .st-key-macro6_selected_codes [data-baseweb="tag"] {
                background: rgba(92,79,214,0.96) !important;
                color: #F6F4FF !important;
                font-size: 11px !important;
                line-height: 1.25 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            _macro6_presets = _load_macro6_proxy_final_presets()
            if not _macro6_presets:
                st.warning("Proxy-only 후보 프리셋을 불러오지 못했습니다.")
                return
            _macro6_blocking = {key: _macro3_preset_blocking_reasons(value) for key, value in _macro6_presets.items()}
            _macro6_snapshot_map = {}
            _macro6_runtime_blocking = {key: [] for key in _macro6_presets}
            with st.spinner("📡 Proxy-only 운영 스냅샷 계산 중..."):
                for _key, _cfg in _macro6_presets.items():
                    if _macro6_blocking.get(_key):
                        continue
                    _snapshot = _compute_macro6_operating_snapshot(_cfg, sync_bucket=_macro6_sync_bucket)
                    if _snapshot is None:
                        _macro6_runtime_blocking[_key].append("Proxy-only 현재 신호 계산 경로에서 결과를 만들지 못했습니다.")
                    else:
                        _macro6_snapshot_map[_key] = _snapshot
            _macro6_blocking = {
                key: list(dict.fromkeys(_macro6_blocking.get(key, []) + _macro6_runtime_blocking.get(key, [])))
                for key in _macro6_presets
            }
            _macro6_group_status_combo2 = _macro3_group_availability_html(
                "조합2",
                _MACRO6_COMBO2_ORDER,
                _macro6_presets,
                _macro6_blocking,
            )
            _macro6_group_status_combo1 = _macro3_group_availability_html(
                "조합1",
                _MACRO6_COMBO1_ORDER,
                _macro6_presets,
                _macro6_blocking,
            )
            _macro6_consensus_combo2 = _macro6_group_consensus_html(
                "조합2",
                _MACRO6_COMBO2_ORDER,
                _macro6_presets,
                _macro6_blocking,
                years=5,
                sync_bucket=_macro6_sync_bucket,
                snapshot_map=_macro6_snapshot_map,
            )
            _macro6_consensus_combo1 = _macro6_group_consensus_html(
                "조합1",
                _MACRO6_COMBO1_ORDER,
                _macro6_presets,
                _macro6_blocking,
                years=5,
                sync_bucket=_macro6_sync_bucket,
                snapshot_map=_macro6_snapshot_map,
            )
            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="macro2-helper-text" style="margin-top:6px;line-height:1.55;">
                    <div>
                        {_macro6_group_status_combo2}
                        <span style="color:rgba(255,255,255,0.36);padding:0 10px;">|</span>
                        {_macro6_group_status_combo1}
                    </div>
                    <div style="margin-top:2px;">
                        {_macro6_consensus_combo2}
                        <span style="color:rgba(255,255,255,0.36);padding:0 10px;">|</span>
                        {_macro6_consensus_combo1}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            _macro6_separator_key = "macro6_group_separator"
            _macro6_preset_order = list(_MACRO6_COMBO2_ORDER) + [_macro6_separator_key] + list(_MACRO6_COMBO1_ORDER)
            _macro6_preset_order = [key for key in _macro6_preset_order if key in _macro6_presets]
            _macro6_preset_options = list(_MACRO6_COMBO2_ORDER) + [_macro6_separator_key] + list(_MACRO6_COMBO1_ORDER)
            if not _macro6_preset_order:
                st.warning("표시 가능한 Proxy-only 후보가 없습니다.")
                return
            if st.session_state.get("macro6_preset") not in _macro6_preset_order:
                st.session_state["macro6_preset"] = _macro6_preset_order[0]
            if st.session_state.get("macro6_preset_picker") == _macro6_separator_key:
                st.session_state["macro6_preset_picker"] = _MACRO6_COMBO1_ORDER[0]
            _macro6_current_preset = st.session_state.get("macro6_preset_picker", st.session_state["macro6_preset"])
            if _macro6_current_preset not in _macro6_preset_options:
                _macro6_current_preset = st.session_state["macro6_preset"]

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l61, _l62, _l63, _l64 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            with _l61:
                st.markdown('<div class="macro2-control-label">조합 프리셋</div>', unsafe_allow_html=True)
            with _l62:
                st.markdown('<div class="macro2-control-label">기준지수</div>', unsafe_allow_html=True)
            with _l63:
                st.markdown('<div class="macro2-control-label">기간</div>', unsafe_allow_html=True)
            with _l64:
                st.markdown('<div class="macro2-control-label">보조선 표시</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m61, _m62, _m63, _m64 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
            with _m61:
                _macro6_preset = st.selectbox(
                    "조합 프리셋",
                    options=_macro6_preset_options,
                    index=_macro6_preset_options.index(_macro6_current_preset),
                    format_func=lambda x: "──────── 조합1 ────────" if x == _macro6_separator_key else _macro6_presets[x]["label"],
                    key="macro6_preset_picker",
                    label_visibility="collapsed",
                )
            if _macro6_preset == _macro6_separator_key:
                _macro6_preset = _MACRO6_COMBO1_ORDER[0]
            st.session_state["macro6_preset"] = _macro6_preset
            _macro6_preset_cfg = _macro6_presets[_macro6_preset]
            _macro6_is_combo2 = _macro6_preset_cfg.get("kind") == "combo2_final8" or bool(_macro6_preset_cfg.get("components"))
            with _m62:
                st.selectbox(
                    "기준지수",
                    options=["S&P500"],
                    index=0,
                    key="macro6_benchmark",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with _m63:
                _yr_opts6 = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro6_years = st.select_slider(
                    "기간",
                    options=list(_yr_opts6.keys()),
                    value=5,
                    format_func=lambda x: _yr_opts6[x],
                    key="macro6_years",
                    label_visibility="collapsed",
                )
            with _m64:
                st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
                _show_raw_macro6 = st.checkbox("보조선 표시", value=False, key="macro6_show_raw", label_visibility="collapsed")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _l65, _l66 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _l65:
                st.markdown('<div class="macro2-control-label">조합 지표</div>', unsafe_allow_html=True)
            with _l66:
                st.markdown('<div class="macro2-control-label">리스크 기준</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)

            _m65, _m66 = st.columns([4.4, 1.6], vertical_alignment="bottom")
            with _m65:
                _macro6_options = _macro6_preset_cfg.get("components", []) if _macro6_is_combo2 else _MACRO3_INDICATOR_ORDER
                _macro6_default = _macro6_preset_cfg.get("components", []) if _macro6_is_combo2 else _macro6_preset_cfg.get("selected_indicators", [])
                if list(st.session_state.get("macro6_selected_codes", [])) != list(_macro6_default):
                    st.session_state["macro6_selected_codes"] = list(_macro6_default)
                st.multiselect(
                    "조합 지표",
                    options=_macro6_options,
                    default=_macro6_default,
                    format_func=lambda x: _macro3_component_label(x, _macro6_preset_cfg.get("component_cfgs", {}).get(x)) if _macro6_is_combo2 else _MACRO3_INDICATOR_LABELS.get(x, x),
                    key="macro6_selected_codes",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with _m66:
                st.markdown(
                    (
                        "<div style='padding-top:8px;font-size:11.5px;line-height:1.42;color:rgba(255,255,255,0.84);'>"
                        f"시작 {int(_macro6_preset_cfg.get('combo_k', 1))}개 이상 ON<br>"
                        f"종료 {int(_macro6_preset_cfg.get('combo_l', 0))}개 이하 ON"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

            _macro6_selected_blocking = _macro6_blocking.get(_macro6_preset, [])
            if _macro6_selected_blocking:
                st.warning("선택한 후보는 계산 불가 상태입니다.")
                with st.expander("계산 불가 사유", expanded=True):
                    for _reason in _macro6_selected_blocking:
                        st.write(f"- {_reason}")
                return

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            _macro6_selected_snapshot = _macro6_snapshot_map.get(_macro6_preset)
            _spx_s6_full = _macro6_selected_snapshot.get("spx_s", pd.Series(dtype=float)) if _macro6_selected_snapshot else pd.Series(dtype=float)
            _macro6_spx_cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=int(_macro6_years))
            _spx_s6 = _spx_s6_full.loc[_spx_s6_full.index >= _macro6_spx_cutoff].dropna() if not _spx_s6_full.empty else pd.Series(dtype=float)
            if _spx_s6.empty and not _spx_s6_full.empty:
                _spx_s6 = _spx_s6_full.dropna()
            if _spx_s6 is None or _spx_s6.empty:
                st.warning("기준 지수 데이터를 불러오지 못했습니다.")
                return

            with st.spinner("📡 Proxy-only 후보 데이터 로딩 중..."):
                _macro6_combo_fig, _macro6_combo_event_df = _make_macro6_combo_chart_from_snapshot(
                    years=_macro6_years,
                    benchmark_name="S&P500",
                    preset_cfg=_macro6_preset_cfg,
                    snapshot=_macro6_selected_snapshot,
                    return_debug=True,
                )
                if _macro6_is_combo2:
                    _macro6_indicator_charts = {
                        _component: _build_macro6_component_chart(
                            component_key=_component,
                            years=_macro6_years,
                            benchmark_name="S&P500",
                            preset_cfg=_macro6_preset_cfg,
                            spx_s=_spx_s6,
                            sync_bucket=_macro6_sync_bucket,
                        )
                        for _component in _macro6_preset_cfg.get("components", [])
                    }
                else:
                    _macro6_indicator_charts = {
                        _indicator: _build_macro6_indicator_chart(
                            indicator=_indicator,
                            years=_macro6_years,
                            benchmark_name="S&P500",
                            preset_cfg=_macro6_preset_cfg,
                            spx_s=_spx_s6,
                            show_raw=_show_raw_macro6,
                            sync_bucket=_macro6_sync_bucket,
                        )
                        for _indicator in _MACRO3_INDICATOR_ORDER
                    }

            if _macro6_combo_fig is None:
                st.warning("선택한 Proxy-only 후보 차트를 만들지 못했습니다. 데이터 지연 또는 필수 지표 누락 여부를 확인해 주세요.")
                return

            _macro6_full_event_df = _macro6_selected_snapshot.get("event_frame", _macro6_combo_event_df) if _macro6_selected_snapshot else _macro6_combo_event_df
            _macro6_status_html, _macro6_status_table_html = _build_macro6_status_panel(
                benchmark_name="S&P500",
                years=_macro6_years,
                preset_cfg=_macro6_preset_cfg,
                combo_event_df=_macro6_full_event_df,
                sync_bucket=_macro6_sync_bucket,
            )
            if _macro6_status_html:
                st.markdown(
                    _macro6_status_html,
                    unsafe_allow_html=True,
                )

            _macro6_bt_compare_combo2_html = _build_macro6_backtest_panel(
                _macro6_preset,
                preset_defs=_macro6_presets,
                preset_order=_MACRO6_COMBO2_ORDER,
                years=_macro6_years,
                sync_bucket=_macro6_sync_bucket,
                snapshot_map=_macro6_snapshot_map,
            )
            _macro6_bt_compare_combo1_html = _build_macro6_backtest_panel(
                _macro6_preset,
                preset_defs=_macro6_presets,
                preset_order=_MACRO6_COMBO1_ORDER,
                years=_macro6_years,
                sync_bucket=_macro6_sync_bucket,
                snapshot_map=_macro6_snapshot_map,
            )
            if _macro6_bt_compare_combo2_html:
                with st.expander("백테스트 비교 보기 · 조합2", expanded=False):
                    st.markdown(_macro6_bt_compare_combo2_html, unsafe_allow_html=True)
            if _macro6_bt_compare_combo1_html:
                with st.expander("백테스트 비교 보기 · 조합1", expanded=False):
                    st.markdown(_macro6_bt_compare_combo1_html, unsafe_allow_html=True)

            if _macro6_status_table_html:
                with st.expander("지표별 상태 보기", expanded=False):
                    st.markdown(_macro6_status_table_html, unsafe_allow_html=True)
                    st.caption(_macro6_preset_cfg.get("review_status", "사용자 선택 완료·운영 미승인 대시보드 검토 후보"))
                    if _macro6_preset_cfg.get("selection_reason"):
                        st.caption(f"선정 이유: {_macro6_preset_cfg['selection_reason']}")
                    if _macro6_preset_cfg.get("dashboard_review_focus"):
                        st.caption(f"대시보드 확인 포인트: {_macro6_preset_cfg['dashboard_review_focus']}")

            st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
            st.plotly_chart(
                _macro6_combo_fig,
                width="stretch",
                config={"displayModeBar": False},
                key=f"macro6_combo_{_macro6_preset}_{_macro6_years}",
            )
            _macro6_detail_items = _macro6_preset_cfg.get("components", []) if _macro6_is_combo2 else _MACRO3_INDICATOR_ORDER
            for _indicator in _macro6_detail_items:
                _fig = _macro6_indicator_charts.get(_indicator)
                _expanded = True if _macro6_is_combo2 else _indicator in _macro6_preset_cfg.get("selected_indicators", [])
                _label = _macro3_component_label(_indicator, _macro6_preset_cfg.get("component_cfgs", {}).get(_indicator)) if _macro6_is_combo2 else _MACRO3_INDICATOR_LABELS.get(_indicator, _indicator)
                with st.expander(_label, expanded=_expanded):
                    if _fig is not None:
                        st.plotly_chart(
                            _fig,
                            width="stretch",
                            config={"displayModeBar": False},
                            key=f"macro6_chart_{_macro6_preset}_{_macro6_years}_{_macro3_indicator_key(_indicator)}",
                        )
                    else:
                        st.caption("이 후보에서는 사용되지 않거나 차트 데이터가 없습니다.")

            _macro_debug_log(
                "render_macro6_proxy_final_section",
                preset_key=_macro6_preset,
                years=_macro6_years,
                elapsed_ms=round((time.perf_counter() - _started) * 1000, 1),
            )

    def render_market_macro_main_section(container):
        with container:
            st.markdown("""
            <style>
            .macro-main-helper-text {
                font-size: 11.5px;
                line-height: 1.45;
                color: rgba(255,255,255,0.56);
                margin: 2px 0 14px 0;
            }
            .macro-main-divider {
                border-top: 1px solid rgba(255,255,255,0.08);
                margin: 24px 0;
            }
            .macro-main-control-label {
                font-size: 11.5px;
                color: rgba(255,255,255,0.72);
                font-weight: 600;
                line-height: 1.2;
                margin-bottom: 0.7rem;
            }
            .macro-main-control-spacer {
                height: 18px;
            }
            .st-key-macro_main_benchmark div[data-baseweb="select"] > div,
            .st-key-macro_main_show_spx label,
            .st-key-macro_main_show_spx span,
            .st-key-macro_main_show_spx p,
            .st-key-macro_main_show_raw label,
            .st-key-macro_main_show_raw span,
            .st-key-macro_main_show_raw p,
            .st-key-macro_main_years div[data-baseweb="slider"] + div {
                font-size: 13.5px !important;
                color: rgba(255,255,255,0.92) !important;
            }
            .st-key-macro_main_benchmark div[data-baseweb="select"] > div {
                min-height: 2.55rem;
                border-color: rgba(95,86,214,0.56) !important;
                background: rgba(52,44,112,0.18) !important;
                box-shadow: none !important;
            }
            .st-key-macro_main_show_spx [data-baseweb="checkbox"] > div,
            .st-key-macro_main_show_raw [data-baseweb="checkbox"] > div {
                border-color: rgba(95,86,214,0.68) !important;
            }
            </style>
            """, unsafe_allow_html=True)

            st.markdown('<div class="macro-main-helper-text">FRED + yfinance 기반 매크로 지표입니다. 나스닥은 미국 세트를 그대로 쓰고, 코스피는 변동성·텀스프레드·신용계열을 한국형 프록시로 대체합니다.</div>', unsafe_allow_html=True)

            st.markdown('<div class="macro-main-divider"></div>', unsafe_allow_html=True)
            _l0, _l1, _l2, _l3 = st.columns([1.35, 2.85, 1.0, 1.0], vertical_alignment="bottom")
            with _l0:
                st.markdown('<div class="macro-main-control-label">기준지수</div>', unsafe_allow_html=True)
            with _l1:
                st.markdown('<div class="macro-main-control-label">기간</div>', unsafe_allow_html=True)
            with _l2:
                st.markdown('<div class="macro-main-control-label">지수 오버레이</div>', unsafe_allow_html=True)
            with _l3:
                st.markdown('<div class="macro-main-control-label">원본선 표시</div>', unsafe_allow_html=True)
            st.markdown('<div class="macro-main-control-spacer"></div>', unsafe_allow_html=True)

            _c0, _c1, _c2, _c3 = st.columns([1.35, 2.85, 1.0, 1.0], vertical_alignment="bottom")
            with _c0:
                _benchmark_name = st.selectbox("기준지수", options=["S&P500", "Nasdaq", "KOSPI"], index=0, label_visibility='collapsed', key='macro_main_benchmark')
            with _c1:
                _yr_opts = {2: '2년', 3: '3년', 5: '5년', 7: '7년', 10: '10년', 15: '15년', 20: '20년'}
                _macro_years = st.select_slider("기간", options=list(_yr_opts.keys()), value=3, format_func=lambda x: _yr_opts[x], label_visibility='collapsed', key='macro_main_years')
            with _c2:
                _show_spx = st.checkbox("S&P500 오버레이", value=True, key='macro_main_show_spx', label_visibility='collapsed')
            with _c3:
                _show_raw_macro = st.checkbox("원본선 표시", value=False, key='macro_main_show_raw', label_visibility='collapsed')

            st.markdown('<div class="macro-main-divider"></div>', unsafe_allow_html=True)
            with st.expander("고급 설정", expanded=False):
                _gp1, _gp2, _gp3, _gp4, _gp5 = st.columns(5)
                with _gp1:
                    _ema_span = st.selectbox("EMA", [10, 20], index=1, key='macro_main_ema')
                with _gp2:
                    _std_window = st.selectbox("rolling std N", [10, 20, 40], index=2, key='macro_main_std_window')
                with _gp3:
                    _ema_compare_days = st.selectbox("EMA 비교 M일", [5, 10, 20], index=1, key='macro_main_ema_compare_days')
                with _gp4:
                    _start_count = st.selectbox("하락 시작", [3, 4], index=1, format_func=lambda x: f"{x}/5", key='macro_main_start_count')
                with _gp5:
                    _end_count = st.selectbox("하락 종료", [3, 4], index=0, format_func=lambda x: f"{x}/5", key='macro_main_end_count')

            _downturn_params = {'ema_span': _ema_span, 'std_window': _std_window, 'ema_compare_days': _ema_compare_days, 'start_count': _start_count, 'end_count': _end_count}

            st.markdown('<div class="macro-main-divider"></div>', unsafe_allow_html=True)
            with st.spinner("📡 기준 지수 데이터 로딩 중..."):
                _benchmark_cfg = _get_macro_benchmark(_benchmark_name)
                _spx_s = _yf_close(_benchmark_cfg['code'], _macro_years) if _show_spx else None

            with st.spinner("📡 매크로 데이터 로딩 중..."):
                _macro_charts = [
                    make_macro_index_cycle_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_hy_spread_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_ig_spread_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_credit_stress_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_options_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_vix_spread_chart(_macro_years, _spx_s, _show_raw_macro, _downturn_params, _benchmark_name),
                    make_macro_rate_levels_chart(_macro_years, _spx_s, _benchmark_name),
                    make_macro_yield_spread_chart(_macro_years, _spx_s, _benchmark_name),
                    make_macro_pmi_chart(_macro_years, _spx_s, _benchmark_name),
                    make_macro_liquidity_chart(_macro_years, _spx_s, _benchmark_name),
                    make_macro_ai_capex_chart(_macro_years, _spx_s),
                ]

            _mc = st.columns(2)
            for i, ch in enumerate(_macro_charts):
                if ch is not None:
                    with _mc[i % 2]:
                        _chart = _tune_macro_main_chart(ch)
                        st.plotly_chart(_chart, width="stretch", config={"displayModeBar": False}, key=f"macro_main_chart_{i}_{_benchmark_name}_{_macro_years}_{int(_show_spx)}_{int(_show_raw_macro)}")
                        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
                else:
                    with _mc[i % 2]:
                        _labels = ['⓪ 지수 리스크 사이클', '① HY 스프레드', '② IG 스프레드', '③ 크레딧 스트레스', '④ VIX', '⑤ VIX 스프레드', '⑥ 금리 레벨', '⑦ 금리 스프레드', '⑧ 경기 모멘텀', '⑨ 유동성', '⑩ AI CAPEX']
                        st.warning(f"{_labels[i]} 데이터 로딩 실패 — FRED 일시 불가. 잠시 후 재시도해 주세요.")

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — 신호 스캐너
    # ═══════════════════════════════════════════════════════════
    if page == "signal2":
        _render_signal_scanner2_section(tab1, favorites=favorites)

    if page == "signal3":
        _render_signal_scanner3_section(tab1, favorites=favorites)

    if page in ("all", "signal"):
        with tab1:
            if page == "signal":
                _signal_mode_options = ["신호스캐너1", "신호스캐너3"]
                if st.session_state.get("signal_scanner_mode") not in _signal_mode_options:
                    st.session_state["signal_scanner_mode"] = "신호스캐너1"
                scanner_mode = st.radio(
                    "신호 스캐너 모드",
                    _signal_mode_options,
                    index=_signal_mode_options.index(st.session_state.get("signal_scanner_mode", "신호스캐너1")),
                    horizontal=True,
                    key="signal_scanner_mode",
                    help="신호스캐너1은 기존 BB+동적 RSI 규칙, 신호스캐너3은 선택한 조합 프리셋을 각 종목 가격에 적용합니다.",
                )
                if scanner_mode == "신호스캐너3":
                    today = datetime.now().date()
                    data_end = str(today + timedelta(days=1))
                    warmup_days = 900 if chart_mode == "분봉" else 1400
                    data_start = str(today - timedelta(days=period_days + warmup_days))
                    _render_signal_scanner3_mode(
                        st.container(),
                        favorites=favorites,
                        chart_mode=chart_mode,
                        yf_interval=yf_interval,
                        higher_interval=higher_interval if chart_mode != "분봉" else None,
                        period_days=period_days,
                        data_start=data_start,
                        data_end=data_end,
                        auto_refresh=auto_refresh,
                        refresh_ms=refresh_ms,
                    )
                    return

            _signal_debug_log("scanner_page_enter", chart_mode=chart_mode, favorites=len(favorites), auto_refresh=auto_refresh)
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

            with st.spinner("📡 데이터 로딩..."):
                _signal_snapshot, _ = _get_signal_table_snapshot(
                    tuple((item["code"], item["name"]) for item in favorites),
                    tuple((item["code"], item["name"]) for item in US_WATCHLIST),
                    chart_mode,
                    yf_interval,
                    higher_interval if chart_mode != "분봉" else None,
                    period_days,
                    data_start,
                    data_end,
                    bb_window=bb_window,
                    bb_std=bb_std,
                    rsi_period=rsi_period,
                    rsi_buy_center=rsi_buy_center,
                    rsi_sell_center=rsi_sell_center,
                    rsi_band=rsi_band,
                    rsi_lookback=rsi_lookback,
                    persist=persist,
                    phase2_rsi=phase2_rsi,
                    force_refresh=False,
                    auto_refresh=auto_refresh,
                )

            signal_rows = _signal_snapshot["signal_rows"]
            us_signal_rows = _signal_snapshot["us_signal_rows"]
            _missing_kr = _signal_snapshot["missing_kr"]
            _missing_us = _signal_snapshot["missing_us"]

            # 데이터 로딩 실패 종목 안내 (해당 종목만 빈 값으로 표시, 앱은 계속 동작)
            _missing_all = _missing_kr + _missing_us
            if _missing_all:
                st.warning(
                    "⚠️ 일부 종목 데이터를 가져오지 못했습니다 (Yahoo Finance 요청 제한/일시 오류일 수 있음): "
                    + ", ".join(_missing_all)
                    + " — 해당 종목은 빈 값으로 표시됩니다. 잠시 후 새로고침하면 자동으로 다시 시도됩니다."
                )

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
                st.markdown(
                    render_signal_table(
                        signal_rows,
                        market='kr',
                        current_chart_mode=chart_mode,
                        current_intra_interval=intra_interval_label,
                    ),
                    unsafe_allow_html=True,
                )

            with st.expander(f"📋 🇺🇸 미국 지수/ETF 현황 ({len(us_signal_rows)}개)", expanded=False):
                st.markdown(
                    render_signal_table(
                        us_signal_rows,
                        market='us',
                        current_chart_mode=chart_mode,
                        current_intra_interval=intra_interval_label,
                    ),
                    unsafe_allow_html=True,
                )

            # ② 종목 선택 — 한국 / 미국 좌우 분리
            col_kr, col_us = st.columns(2)

            kr_names = [f['name'] for f in favorites]
            us_names = [t['name'] for t in US_WATCHLIST]

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
                _sel_item = next((t for t in US_WATCHLIST if t['name'] == _us_name), US_WATCHLIST[0])
                selected_name = _sel_item['name']
                selected_code = _sel_item['code']

            # 한국 시간대 판별 (지수 코드 포함)
            _is_korean = selected_code.endswith(('.KS', '.KQ')) or \
                         selected_code in ('^KS11', '^KQ11')

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # ── 일/주/월봉 차트 ─────────────────────────────────
            if chart_mode != "분봉":
                _detail_fetch_started = time.perf_counter()
                with st.spinner("차트 로딩..."):
                    ohlcv = fetch_ohlcv(selected_code, data_start, data_end, higher_interval)
                _signal_debug_log(
                    "detail_chart_fetch",
                    chart_mode=chart_mode,
                    ticker=selected_code,
                    interval=higher_interval,
                    elapsed_ms=round((time.perf_counter() - _detail_fetch_started) * 1000, 1),
                    df_shape=ohlcv.shape if isinstance(ohlcv, pd.DataFrame) else None,
                )

                if ohlcv.empty:
                    st.warning(f"⚠️ {selected_name} 데이터를 가져올 수 없습니다.")
                else:
                    _display_bars = None
                    if chart_mode == "주봉":
                        _display_bars = max(1, round(period_days / _higher_bars_divisor["주봉"]))
                    elif chart_mode == "월봉":
                        _display_bars = max(1, round(period_days / _higher_bars_divisor["월봉"]))
                    _plot_started = time.perf_counter()
                    fig = make_detail_chart(
                        ohlcv, selected_name, period_days,
                        bb_window=bb_window, rsi_lookback=rsi_lookback,
                        rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                        persist=persist, phase2_rsi=phase2_rsi,
                        display_bars=_display_bars,
                    )
                    _signal_debug_log(
                        "detail_chart_plotly_create",
                        chart_mode=chart_mode,
                        ticker=selected_code,
                        elapsed_ms=round((time.perf_counter() - _plot_started) * 1000, 1),
                        has_figure=bool(fig),
                    )
                    if fig:
                        _signal_debug_log("detail_chart_render_before", chart_mode=chart_mode, ticker=selected_code)
                        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                        _signal_debug_log("detail_chart_render_after", chart_mode=chart_mode, ticker=selected_code)
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
                _signal_debug_log("intraday_mode_enter", ticker=_ticker, interval=yf_interval, period_days=period_days)
                with st.spinner(f"분봉 로딩... ({intra_interval_label}, {period_name} 기준)"):
                    ohlcv_intra, intra_err = _fetch_intraday_guarded(_ticker, yf_interval, chart_mode, "detail_chart")
                _signal_debug_log(
                    "detail_intraday_fetch",
                    ticker=_ticker,
                    interval=yf_interval,
                    chart_mode=chart_mode,
                    df_shape=ohlcv_intra.shape if isinstance(ohlcv_intra, pd.DataFrame) else None,
                    error=intra_err,
                )

                if ohlcv_intra.empty:
                    st.warning(f"⚠️ {selected_name} 분봉 데이터를 가져올 수 없습니다.")
                    if intra_err:
                        st.code(intra_err, language=None)
                else:
                    if intra_err:
                        st.caption(f"⚠️ 데이터 로딩 경고: {intra_err}")
                    _disp_bars = _intra_bars_per_day[yf_interval] * period_days
                    _session   = (15.5, 9.0) if _is_korean else None
                    _plot_started = time.perf_counter()
                    fig_intra  = make_detail_chart(
                        ohlcv_intra, f"{selected_name} ({intra_interval_label})", period_days,
                        bb_window=bb_window, rsi_lookback=rsi_lookback,
                        rsi_buy_center=40, rsi_sell_center=80, rsi_band=5,
                        persist=persist, phase2_rsi=phase2_rsi,
                        display_bars=_disp_bars,
                        intraday_session=_session,
                    )
                    _signal_debug_log(
                        "detail_intraday_plotly_create",
                        ticker=_ticker,
                        interval=yf_interval,
                        elapsed_ms=round((time.perf_counter() - _plot_started) * 1000, 1),
                        has_figure=bool(fig_intra),
                    )
                    if fig_intra:
                        _signal_debug_log("detail_intraday_render_before", ticker=_ticker, interval=yf_interval)
                        st.plotly_chart(fig_intra, width="stretch", config={"displayModeBar": False})
                        _signal_debug_log("detail_intraday_render_after", ticker=_ticker, interval=yf_interval)
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
                **다이내믹 신호 기준**
                - <span style="color:#4F88C6;font-weight:700;">▲ 매수 플래그</span>: RSI가 최근 분포 기준 동적 하단 아래로 내려가고, 동시에 **저가가 볼린저밴드 하단 이하**로 내려갈 때
                - <span style="color:#22C55E;font-weight:700;">★ 매수 신호</span>: 매수 플래그 이후 **저가가 볼린저밴드 하단 위로 복귀한 상태가 연속 유지**될 때
                - <span style="color:#E08A3A;font-weight:700;">▼ 매도 플래그</span>: RSI가 최근 분포 기준 동적 상단 위로 올라가고, 동시에 **고가가 볼린저밴드 상단 이상**으로 올라갈 때
                - <span style="color:#FF4B6E;font-weight:700;">★ 매도 신호</span>: 매도 플래그 이후 **고가가 볼린저밴드 상단 아래로 복귀한 상태가 연속 유지**될 때

                **보유 중**
                - 🟡 차트의 노란 구간은 **최근 매수 신호 이후, 최근 매도 신호 전까지**의 구간입니다.

                **해석 포인트**
                - 플래그는 과열/과매도 **관심 구간 진입**
                - 신호는 밴드 복귀가 확인된 **확정 구간**
                - 동적 RSI 기준이므로 종목별/구간별로 임계값이 자동 조정됩니다.

                > 이 신호는 참고 지표이며, 실제 매매 결정은 추가 분석 후 본인 판단으로 하세요.
                """, unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════════
        # TAB 2 — 시장 내부지표
        # ═══════════════════════════════════════════════════════════
    if page in ("all", "market") or (page == "market_macro" and _market_macro_section == "market"):
        render_market_internal_indicators_section(tab2)

        # ═══════════════════════════════════════════════════════════
        # TAB 3A — 매크로 지표 2 (실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro2" or (page == "market_macro" and _market_macro_section == "macro2"):
        _macro2_container = tab4 if page == "market_macro" else tab3
        render_macro2_experimental_section(_macro2_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3B — 매크로 지표 3 (정적 threshold 실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro3" or (page == "market_macro" and _market_macro_section == "macro3"):
        _macro3_container = tab5 if page == "market_macro" else tab3
        render_macro3_threshold_section(_macro3_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3C — 매크로 지표 4 (조합 리스크 실험용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro4" or (page == "market_macro" and _market_macro_section == "macro4"):
        _macro4_container = tab6 if page == "market_macro" else tab3
        render_macro4_combo_section(_macro4_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3D — 매크로 지표 5 (Final8 후보 비교용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro5" or (page == "market_macro" and _market_macro_section == "macro5"):
        _macro5_container = tab5 if page == "market_macro" else tab3
        render_macro5_final8_section(_macro5_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3E — 매크로 지표 6 (Proxy-only 후보 비교용)
        # ═══════════════════════════════════════════════════════════
    if page == "macro6" or (page == "market_macro" and _market_macro_section == "macro6"):
        _macro6_container = tab6 if page == "market_macro" else tab3
        render_macro6_proxy_final_section(_macro6_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3F — KOSPI 매크로 지표 5 (Frozen Shadow)
        # ═══════════════════════════════════════════════════════════
    if page == "macro5_kospi" or (page == "market_macro" and _market_macro_section == "macro5_kospi"):
        _macro5_kospi_container = tab7 if page == "market_macro" else tab3
        render_macro5_kospi_section(_macro5_kospi_container)

        # ═══════════════════════════════════════════════════════════
        # TAB 3 — 매크로 지표
        # ═══════════════════════════════════════════════════════════
    if page in ("all", "macro") or (page == "market_macro" and _market_macro_section == "macro"):
        render_market_macro_main_section(tab3)


if __name__ == "__main__":
    main()
