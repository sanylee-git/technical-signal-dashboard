"""Static, display-only source refresh guidance for the macro pages."""

from __future__ import annotations

from html import escape


_US_CLOSE = "서머타임 06:10 이후 · 표준시간 07:10 이후"
_FRED_VIX = "서머타임 23:00 이후 · 표준시간 00:00 이후"
_FRED_CORP = "서머타임 다음날 00:45 이후 · 표준시간 다음날 01:45 이후"
_FRED_H15 = "서머타임 다음날 05:30 이후 · 표준시간 다음날 06:30 이후"
_NFCI = "서머타임 수요일 21:45 이후 · 표준시간 수요일 22:45 이후"


def _shared_us_rows(*, vix_source: str, availability: str) -> list[tuple[str, str, str, str]]:
    vix_time = _US_CLOSE if vix_source.startswith("Yahoo") else _FRED_VIX
    return [
        (f"VIX · VIX3M ({vix_source})", "평일 일 1회", vix_time, f"VIX 레벨·VIX 스프레드·신용스트레스 · {availability}"),
        ("미국 금리 (FRED DGS10·DGS2·DGS3MO·DFII10)", "평일 일 1회", _FRED_H15, f"10Y·10Y-2Y·10Y-3M·실질금리 · {availability}"),
        ("미국 회사채 (FRED DBAA·DAAA)", "평일 일 1회", _FRED_CORP, f"HY·IG 프록시·신용스트레스 · {availability}"),
        ("NFCI 신용스트레스 (FRED NFCI)", "주 1회 · 수요일", _NFCI, f"신용스트레스 · {availability}"),
    ]


_SCHEDULES = {
    "snp": [
        ("S&P500 (Yahoo ^GSPC)", "평일 일 1회", _US_CLOSE, "S&P 기반 지표 · 완료 일봉 사용"),
        *_shared_us_rows(vix_source="Yahoo ^VIX·^VIX3M", availability="다음 시간 버킷 새로고침"),
    ],
    "kospi": [
        ("KOSPI (Yahoo ^KS11)", "KRX 거래일 장중", "장중 매 정각 +5분 · 확정은 15:40 이후", "BB·NATR·RSI 등 · 장중값은 잠정"),
        ("원/달러 환율 (Yahoo KRW=X)", "평일 일 1회", "다음 KRX 영업일 아침", "환율 지표 · +1 KRX 영업일 후 사용"),
        *_shared_us_rows(vix_source="FRED VIXCLS·VXVCLS", availability="+1 KRX 영업일 후 사용"),
    ],
    "kosdaq": [
        ("KOSDAQ (네이버 · Yahoo ^KQ11 fallback)", "KRX 거래일 장중", "장중 다음 1분 이후 · 확정은 15:40 이후", "BB·HV·NATR·RSI 등 · 장중값은 잠정"),
        ("원/달러 환율 (Yahoo KRW=X)", "평일 일 1회", "다음 KRX 영업일 아침", "환율 지표 · +1 KRX 영업일 후 사용"),
        *_shared_us_rows(vix_source="FRED VIXCLS·VXVCLS", availability="+1 KRX 영업일 후 사용"),
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
        "미국 서머타임: 3월 둘째 일요일~11월 첫째 일요일<br>"
        "자동 갱신은 없으며, 새로고침 또는 화면 조작으로 다시 조회합니다. "
        "표의 시각은 권장 확인 시각이며 FRED 실제 반영은 지연될 수 있습니다."
        "</div>"
        "<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32;'>"
        "<thead><tr>"
        f"<th style='{header_style}'>원천·영향 지표</th>"
        f"<th style='{header_style}'>갱신 주기</th>"
        f"<th style='{header_style}'>권장 확인 시각(KST)</th>"
        f"<th style='{header_style}'>모델 반영</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )
