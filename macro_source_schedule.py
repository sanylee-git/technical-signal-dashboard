"""Static, display-only source refresh guidance for the macro pages."""

from __future__ import annotations

from html import escape


_US_DST = "3월 둘째 일요일~11월 첫째 일요일"
_US_STANDARD = "그 외 기간"
_US_CLOSE = f"{_US_DST}: 06:10 이후 · {_US_STANDARD}: 07:10 이후"
_FRED_VIX = f"{_US_DST}: 23:10 이후 · {_US_STANDARD}: 00:10 이후"
_FRED_CORP = f"{_US_DST}: 다음날 00:45 이후 · {_US_STANDARD}: 01:45 이후"
_FRED_H15 = f"{_US_DST}: 다음날 05:30 이후 · {_US_STANDARD}: 다음날 06:30 이후"
_NFCI = f"{_US_DST}: 수요일 21:45 이후 · {_US_STANDARD}: 수요일 22:45 이후"


def _us_daily_rows(*, vix_provider: str, availability: str) -> list[tuple[str, str, str, str]]:
    vix_time = _US_CLOSE if vix_provider == "Yahoo" else _FRED_VIX
    return [
        (f"VIX ({'Yahoo ^VIX' if vix_provider == 'Yahoo' else 'FRED VIXCLS'})", "미국 거래일 일 1회", vix_time, f"VIX 레벨 · {availability}"),
        (f"VIX 스프레드 ({'Yahoo ^VIX - ^VIX3M' if vix_provider == 'Yahoo' else 'FRED VIXCLS - VXVCLS'})", "미국 거래일 일 1회", vix_time, f"VIX 스프레드 · {availability}"),
        ("미국 10년 금리 (FRED DGS10)", "미국 거래일 일 1회", _FRED_H15, f"10Y·스프레드·HY/IG 프록시 · {availability}"),
        ("미국 2년 금리 (FRED DGS2)", "미국 거래일 일 1회", _FRED_H15, f"10Y-2Y 스프레드 · {availability}"),
        ("미국 3개월 금리 (FRED DGS3MO)", "미국 거래일 일 1회", _FRED_H15, f"10Y-3M 스프레드 · {availability}"),
        ("미국 10년 실질금리 (FRED DFII10)", "미국 거래일 일 1회", _FRED_H15, f"실질금리 지표 · {availability}"),
        ("미국 BAA 회사채 (FRED DBAA)", "미국 거래일 일 1회", _FRED_CORP, f"HY 프록시·신용스트레스 · {availability}"),
        ("미국 AAA 회사채 (FRED DAAA)", "미국 거래일 일 1회", _FRED_CORP, f"IG 프록시 · {availability}"),
        ("NFCI 신용스트레스 (FRED NFCI)", "주 1회 · 수요일", _NFCI, f"신용스트레스 · {availability}"),
    ]


_SCHEDULES = {
    "snp": [
        ("S&P500 (Yahoo ^GSPC)", "미국 거래일 일 1회", _US_CLOSE, "S&P 기반 지표 · 완료 일봉 사용"),
        *_us_daily_rows(vix_provider="Yahoo", availability="다음 시간 버킷 새로고침"),
    ],
    "kospi": [
        ("KOSPI (Yahoo ^KS11)", "KRX 거래일 장중", "09:00~15:30 · 장중 매 정각 +5분 · 종가 15:40 이후", "BB·NATR·RSI 등 · 시간 단위 재조회"),
        ("원/달러 환율 (Yahoo KRW=X)", "평일 일간", "다음 영업일 아침 점검", "환율 지표 · 1영업일 availability 적용"),
        *_us_daily_rows(vix_provider="FRED", availability="1영업일 availability 후 시간 단위 재조회"),
    ],
    "kosdaq": [
        ("KOSDAQ (네이버 · Yahoo ^KQ11 fallback)", "KRX 거래일 장중", "09:00~15:30 · 장중 다음 1분 이후 · 종가 15:40 이후", "BB·HV·NATR·RSI 등 · 다음 분 새로고침"),
        ("원/달러 환율 (Yahoo KRW=X)", "평일 일간", "다음 영업일 아침 점검", "환율 지표 · 1영업일 availability 적용"),
        *_us_daily_rows(vix_provider="FRED", availability="1영업일 availability 후 다음 분 재조회"),
    ],
}


def source_schedule_table_html(market: str) -> str:
    """Return static guidance only; no data access or model work occurs here."""

    rows = _SCHEDULES.get(market, [])
    header_style = (
        "text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;"
        "border-bottom:1px solid rgba(255,255,255,0.08);white-space:nowrap;"
    )
    cell_style = "padding:6px 8px;color:#D6D6D6;line-height:1.32;vertical-align:top;"
    body = "".join(
        "<tr>" + "".join(f"<td style='{cell_style}'>{escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return (
        "<div style='font-size:11px;color:rgba(255,255,255,.56);margin:0 0 8px 0;'>"
        "자동 갱신은 없으며, 새로고침 또는 화면 조작으로 다시 조회합니다. "
        "표의 시각은 권장 확인 시각이며 FRED 실제 반영은 지연될 수 있습니다."
        "</div>"
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32;'>"
        "<thead><tr>"
        f"<th style='{header_style}'>원천·영향 지표</th>"
        f"<th style='{header_style}'>갱신 주기</th>"
        f"<th style='{header_style}'>권장 확인 시각(KST)</th>"
        f"<th style='{header_style}'>모델·페이지 반영</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )
