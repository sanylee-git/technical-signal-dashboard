"""Static, display-only source refresh guidance for the macro pages."""

from __future__ import annotations

from html import escape


_SCHEDULES = {
    "snp": [
        ("S&P500 기반 지표", "미국 거래일 일 1회", "여름 06:10 / 겨울 07:10 이후", "완료 일봉 · 다음 시간 버킷 새로고침"),
        ("미국 일간: VIX·금리·HY/IG", "미국 거래일 일 1회", "VIX 여름 23:10/겨울 00:10 · BAA/AAA 다음날 00:45/01:45 · 금리 05:30/06:30", "FRED 반영 후 다음 시간 버킷 새로고침"),
        ("NFCI 신용스트레스", "주 1회 · 수요일", "여름 21:45 / 겨울 22:45 이후", "휴일이면 목요일 가능"),
    ],
    "kospi": [
        ("KOSPI 파생: BB·NATR·RSI 등", "KRX 거래일 장중", "장중 매 정각 +5분 · 종가 15:40 이후", "시간 단위 재조회 · 장중값은 잠정"),
        ("미국 일간: VIX·금리·HY/IG·환율", "미국 거래일 일 1회", "VIX 여름 23:10/겨울 00:10 · BAA/AAA 다음날 00:45/01:45 · 금리 05:30/06:30", "원천별 availability 후 다음 시간 버킷 재조회"),
        ("NFCI 신용스트레스", "주 1회 · 수요일", "여름 21:45 / 겨울 22:45 이후", "휴일이면 목요일 가능"),
    ],
    "kosdaq": [
        ("KOSDAQ 파생: BB·HV·NATR·RSI 등", "KRX 거래일 장중", "장중 다음 1분 이후 · 종가 15:40 이후", "다음 분 새로고침 · 장중값은 잠정"),
        ("미국 일간: VIX·금리·HY/IG·환율", "미국 거래일 일 1회", "VIX 여름 23:10/겨울 00:10 · BAA/AAA 다음날 00:45/01:45 · 금리 05:30/06:30", "원천별 availability 후 다음 분 재조회"),
        ("NFCI 신용스트레스", "주 1회 · 수요일", "여름 21:45 / 겨울 22:45 이후", "휴일이면 목요일 가능"),
    ],
}


def source_schedule_table_html(market: str) -> str:
    """Return a compact table; it deliberately performs no runtime work."""

    rows = _SCHEDULES.get(market, [])
    header_style = (
        "text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;"
        "border-bottom:1px solid rgba(255,255,255,0.08);white-space:nowrap;"
    )
    cell_style = "padding:6px 8px;color:#D6D6D6;line-height:1.32;vertical-align:top;"
    body = "".join(
        "<tr>"
        + "".join(f"<td style='{cell_style}'>{escape(value)}</td>" for value in row)
        + "</tr>"
        for row in rows
    )
    return (
        "<div style='font-size:11px;color:rgba(255,255,255,.56);margin:0 0 8px 0;'>"
        "자동 갱신은 없으며, 새로고침 또는 화면 조작으로 다시 조회합니다. "
        "원천 갱신이 곧 신호 전환을 뜻하지는 않습니다."
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
