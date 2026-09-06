# S&P 지표2 Stage 1 Contract Freeze

`PASS_SPX_MACRO9_STAGE1_CONTRACT_FROZEN`

- Final 운영 집합은 사용자 지정 `SNP_ProxyOnly_Final_Combo1_5_Combo2_5_20260906.xlsx`의 exact Combo1 5개와 Combo2 5개다.
- 후보, K/L, Combo1 component, Combo2 child 순서와 material index는 [JSON 계약](spx_macro9_stage1_contract_freeze.json)에 고정했다. Dashboard는 이를 재선별하거나 재정렬하지 않는다.
- Main 표시는 Combo1 `7b12636f...` / `93978829...`, Combo2 `61b4f8da...` / `0e715f71...`이며, 표시 우선순위일 뿐 연구 후보 membership 변경이 아니다.

## Proxy-only 핵심 계약

- HY: `DBAA - DGS10`, IG: `DAAA - DGS10`; 같은 날짜 inner join만 허용한다.
- 직접 ICE OAS, stitching, median level shift, interpolation, ffill/bfill은 모두 금지한다.
- Global Credit Stress는 Proxy HY, NFCI, VIX의 clipped Z252 결합이며 세 입력이 모두 필요하다.
- 최신 Core 기준은 `proxy_only_core15_canonical_signal_bank_index.json`이다. 이전 `SP0/SP1` 및 `sp2_frozen_build.py`의 stitched-OAS 계약은 이번 Final10에 사용하지 않는다.

## 실행 및 성과 계약

- 신호/성과 기준은 모두 `^GSPC`이며, 공식 평가기간은 2008-04-01~2026-08-21, 4,628 거래일이다.
- 상태 순서는 `raw -> K/L hysteresis -> final T+1 exactly once -> return`이다. Combo2 입력은 child Combo1 raw state이며, child T+1 state가 아니다.
- 비용은 0bp, Risk-off 현금수익률은 0%다.
- Frozen 공식 성과표는 불변이고, 향후 Live tail은 현재 상태·차트만 연장한다. 결측·stale 구간은 메우거나 Risk-on으로 해석하지 않는다.
- Live basis date는 모든 필수 입력에 source별 availability lag를 적용한 뒤의 마지막 공통 유효 S&P 계산 거래일이다. HY/IG의 same-date 규칙은 raw Proxy 원천 결합에만 적용한다.

## 화면 표시 원칙

- 현재 상태 블록의 기존 `기준일`은 candidate basis date를 그대로 표시한다.
- `Proxy-only · ^GSPC · T+1 · Cost 0bp · Cash 0% · Missing No Fill · Frozen Final5+5`는 새 상단 UI를 만들지 않고 기존 Frozen/Proxy 계약 expander에 짧게 남긴다.
- 배포 전에는 UI payload의 Final10 exact ID, K/L, Combo1 component, Combo2 child mapping이 이 계약과 완전히 같은지 검증한다.

## 다음 단계

Dashboard 전용 Frozen asset을 만들고, 이 exact Final10이 Proxy-only canonical signal bank와 Combo2 material input에서 모두 resolve되는지 확인한 뒤 Core -> Combo1 -> Combo2 -> T+1 parity를 검증한다.
