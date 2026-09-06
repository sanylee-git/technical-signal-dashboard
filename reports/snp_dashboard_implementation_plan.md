# S&P 지표2 대시보드 구현 실행 계획

## 목적

기존 S&P 탭과 다른 운영 지표 탭을 건드리지 않고, 안정화된 KOSDAQ/NASDAQ 대시보드 구현 경험을 바탕으로 새로운 S&P 지표2 탭을 추가한다.

- 기존 화면 구조와 사용 경험은 유지한다.
- S&P 후보·기준지수·데이터 계약만 S&P 전용으로 연결한다.
- 연구/백테스트에서 확정된 후보를 페이지에서 재선별하지 않는다.
- S&P runtime, asset, cache, session, widget key, chart key를 독립적으로 유지한다.
- 계산과 수식은 연구 계약 및 공식 결과를 그대로 재현한다.

이 문서는 구현 지시문이다. 각 단계에서 Gate가 실패하면 추가 구현을 하지 않고 결과만 보고한다.

## 절대 실행 규칙

### 변경 금지

- 기존 S&P 탭, KOSPI, KOSDAQ, NASDAQ 탭
- 기존 모델의 계산식, 신호, K/L, hysteresis, T+1
- 후보 재선별, 재최적화, 후보 순위 변경
- 백테스트 원본과 연구 산출물
- 기존 공통 runtime의 리팩터링
- 기존 탭의 cache/session/widget/chart key

### S&P 전용으로 분리할 것

- runtime namespace
- candidate/manifest namespace
- Frozen asset 또는 live source asset
- cache key
- session_state key
- widget key와 chart key
- diagnostic/report namespace

이미 존재하는 순수 표시 helper만 재사용한다. 데이터 fetch, freshness, 계산, 상태 판정, cache를 공통화하기 위해 기존 코드를 수정하지 않는다.

### 운영 후보 표시 원칙

최종 후보가 20개이고 연구 artifact에 `Practical` 5개씩 명시되어 있으면, 화면 운영 집합은 조합1·조합2 각각 Practical 5개로 제한한다.

- Final20 원본과 계산 결과는 삭제하지 않는다.
- 화면 선택창, 상단 집계, 백테스트 표, 상세 차트만 Practical10을 사용한다.
- `Practical` 태그가 없거나 조합별 개수가 5개가 아니면 임의로 고르지 않고 중단한다.
- 전체 Core registry, Final candidate dictionary, Combo2 child dictionary는 replay에 그대로 유지한다.
- Combo2 child가 화면에 숨긴 Combo1 후보를 참조할 수 있으므로, Practical 필터를 replay input이나 child mapping에 적용하지 않는다.
- `전체 replay -> snapshot/history/presentation payload -> Practical10 UI filter` 순서를 고정한다.

## 단계 0 — 기준선 및 입력자료 읽기 전용 점검

대상:

- Dashboard repo: `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard`
- S&P 연구/백테스트 repo 및 후보 artifact: 사용자가 지정한 실제 경로

확인할 것:

- `main` branch, 현재 `HEAD`, working tree, origin 기준선
- 기존 tracked 변경의 소유자와 의도, untracked 항목의 범위
- 기존 S&P 탭의 실제 render path
- 새 탭에 사용될 후보 파일과 공식 백테스트 결과
- S&P 기준지수 ticker/label
- Core 지표 목록과 각 source
- Proxy 사용 여부와 기간별 source 교체 여부
- Frozen 기준선 이후 최신 Live tail을 어떤 source 계약으로 연결할지

이 단계에서는 파일을 수정하지 않는다.

### Gate 0

- 구현 시작 전 S&P와 무관한 tracked 변경은 없거나 사용자가 명시적으로 보존 승인함
- 기존 tracked 변경을 reset, restore, clean, stash로 임의 정리하지 않음
- dirty 상태라면 clean 기준선 또는 승인된 분리 방법이 확보되기 전 S&P 파일 쓰기 금지
- S&P 최종 후보 artifact가 실제로 확인됨
- 기준지수, Frozen cutoff, Live tail 데이터 정책이 확인됨
- 기존 탭과 새 탭의 소유 경계가 확인됨

입력자료가 불명확하면 다음 단계로 진행하지 않는다.

## 단계 1 — 연구 측 계약 동결 및 Dashboard handoff

이 단계의 source of truth는 백테스트/연구 repo다. Dashboard에서 후보를 새로 선별하지 않는다.

연구 측에서 확정해 넘길 항목:

- 최종 Combo1 후보 ID
- 최종 Combo2 후보 ID
- 각 후보의 component 구성 및 순서
- `n_or_m`, `K`, `L`
- 역할과 Practical/Performance 구분
- 기준지수 ticker와 표시명
- 평가 시작일·종료일
- 공식 CAGR, MDD, Calmar, Risk-off, Cycle 등
- Core 지표별 source와 transform
- Proxy 정의, 직접 OAS 사용 여부
- T+1 적용 횟수
- 결측/invalid state 의미
- `runtime_mode`: `FROZEN_PREFIX_LIVE_TAIL`
- Frozen cutoff와 공식 성과 평가 종료일
- Live tail provider, ticker/series ID, source별 availability lag, freshness 기준
- source observation date와 모델 calculation date의 분리 규칙
- artifact path와 SHA256

Combo2가 Combo1 child를 참조하면 child mapping을 manifest에 고정한다.

```text
combo2_candidate_id
  child_order
  child_combo1_candidate_id
  child_component_ids
  child_K
  child_L
```

또한 UI 표시 계약을 같은 manifest에 고정한다.

- 조합1/조합2의 exact `display_order`
- exact 역할명과 Practical/Performance tag
- `default_selected_candidate`
- 기본 선택이 UI 초기 표시일 뿐 후보 순위나 Main 선정이 아니라는 의미

### Frozen 기준선 + Live tail 운영 계약

S&P 지표2는 NASDAQ 운영 방식과 같이 `FROZEN_PREFIX_LIVE_TAIL`만 사용한다. 이는 Frozen 평가 기준선을 바꾸는 방식이 아니라, 검증된 Frozen 이력 뒤에 최신 원천값으로 계산한 연속 tail만 추가하는 2계층 구조다.

```text
Dashboard-owned Frozen prefix (immutable, 공식 성과 기준)
  +
S&P 전용 provider의 source-approved Live tail
  -> 기존 Core 계산
  -> Combo1 raw/final
  -> Combo2 child raw/final
  -> 최종 T+1 정확히 1회
  -> 후보별 현재 snapshot / history / basis_date
```

- Frozen asset의 행·값·공식 평가 기간·공식 성과표는 불변이다.
- Live tail은 Frozen cutoff **이후**의 연속된 유효 거래일에만 추가한다.
- 공식 백테스트 비교표의 자산·CAGR·MDD·Risk-off·Cycle은 Frozen 평가 종료일 기준 display asset을 계속 사용한다. 현재 Live 상태가 공식 성과표를 덮어쓰면 안 된다.
- source observation date는 metadata로 보존하고, candidate basis date는 S&P 실제 거래일과 source별 availability 계약을 적용한 **마지막 공통 유효 calculation date**로 정한다.
- HY/IG의 same-date inner join은 `DBAA/DAAA`와 `DGS10` 원천값 사이의 raw Proxy 규칙이다. 전체 모델의 basis date는 모든 필수 입력에 source별 availability lag를 적용한 뒤 결정하며, 단순 source observation date의 공통 최종일로 축소하지 않는다.
- Daily source는 실제 S&P/미국 거래일 달력 기준 다음 계산 거래일에 반영한다. 주간 source의 lag도 연구 계약에 고정된 실제 거래일 수로 적용한다.
- 부분 행/장중 값의 허용 여부, primary/fallback provider, 각 series ID와 freshness 기준은 S&P 연구 계약에 명시된 것만 사용한다. 다른 시장의 fallback이나 임의 source splice는 금지한다.
- 60분 등 sync bucket을 쓰더라도 S&P 전용 cache namespace에만 둔다. 후보·차트 기간·expander 같은 표시 전용 UI 변경은 runtime 재조회 조건이 아니다.

Live tail을 붙일 수 없는 경우:

- 필수 source가 누락·stale·invalid이면 해당 날짜 이후 tail을 추가하지 않는다.
- raw 값, derived 지표, EMA/rolling 결과를 forward-fill하거나 합성하지 않는다.
- invalid를 Risk-on/inactive로 바꾸지 않으며, invalid gap을 건너 hysteresis/state를 이어가거나 임의 재시작하지 않는다.
- 따라서 현재 상태는 마지막 연속 유효 basis date에 머물거나, 연구 계약이 요구하면 `UNAVAILABLE`로 표시한다. 최신 provider 관측일을 억지로 basis date로 표시하지 않는다.

이 계약이 확정되지 않으면 runtime 또는 UI 구현을 시작하지 않는다.

### 계약 금지사항

- Dashboard에서 후보를 성과순으로 다시 고르지 않는다.
- 이름과 K/L만 보고 후보를 추정하지 않는다.
- 공식 metric만 보고 candidate_id를 역추론하지 않는다.
- S&P source를 KOSPI/KOSDAQ/NASDAQ source로 대체하지 않는다.
- Proxy와 직접 OAS를 임의로 splice하지 않는다.

### Gate 1

- 최종 후보 ID 중복 0
- Combo1/Combo2 후보 수가 artifact와 일치
- 모든 Combo2 child mapping resolve
- component 누락 0
- benchmark/cost/evaluation window 확인
- source/proxy 계약과 provenance 기록 완료
- `FROZEN_PREFIX_LIVE_TAIL` 및 source별 availability/freshness 정책 확정
- display order, 역할명, default selected candidate 확정
- 후보 재선별 0

이 Gate는 연구 artifact와 handoff 문서가 준비되어야 통과한다.

## 단계 2 — Dashboard 전용 asset 생성 및 Frozen Replay

연구 repo의 원본을 runtime이 직접 참조하지 않도록 Dashboard 전용 asset으로 가져온다.

권장 구조:

```text
technical-signal-dashboard/
  spx_macro9_assets/
    spx_macro9_manifest.json
    spx_macro9_core_registry.csv
    spx_macro9_final20.csv
    spx_macro9_combo2_children.csv
    frozen source files...
```

실제 후보 수와 파일명은 단계 1의 계약을 따른다.

반드시 기록한다.

- 원본 artifact path
- asset path
- 원본 SHA256
- Dashboard asset SHA256
- evaluation start/end
- benchmark
- source contract
- research code/provenance

그 다음 Dashboard 쪽 독립 replay로 다음 순서의 parity를 확인한다.

```text
Frozen Core
  -> Combo1 raw state
  -> Combo1 final state
  -> Combo2 child raw state
  -> Combo2 final state
  -> T+1
  -> performance metrics
```

### 필수 parity

- date
- valid_signal
- raw risk state
- final risk state
- risk start/end event
- active count
- current/1주 전 state
- candidate basis date
- CAGR/MDD/Calmar 및 공식 표시 metric

허용 오차는 공식 artifact의 숫자 정밀도와 기존 Dashboard parity 기준을 그대로 사용한다. 없는 reference를 새로 만들어 검증하지 않는다.

### 의미 계약

- `valid_signal`과 `risk_state`를 별도 필드로 유지한다.
- invalid를 Risk-on 또는 inactive로 변환하지 않는다.
- Combo2는 고정된 child Combo1 raw state를 입력으로 사용한다.
- 최종 T+1 적용 횟수는 연구 계약에 고정된 횟수와 같아야 한다.
- UI에서 지표 수식, state, T+1을 재계산하지 않는다.

### Gate 2

- asset SHA 검증 PASS
- Core parity PASS
- Combo1 parity PASS
- Combo2 child/final parity PASS
- T+1 적용 횟수 PASS
- metric parity PASS
- invalid-as-Risk-on 0
- Frozen prefix row/value overwrite 0
- network access는 S&P Live tail 계약에 명시된 policy와 일치
- 기존 탭 diff 0

## 단계 3 — S&P 독립 Runtime 및 Presentation Payload

단계 2의 검증된 asset과 계약만 읽는 S&P 전용 runtime을 만든다.

권장 namespace 예시:

```text
spx_macro9_runtime/
spx_macro9_ui.py
spx_macro9_* cache/session/widget keys
```

실제 내부 번호는 기존 프로젝트에서 사용하지 않는 namespace인지 확인 후 확정한다.

runtime 책임:

- S&P asset 검증
- S&P 전용 source fetch, availability/freshness 계약 적용
- Frozen prefix를 보존한 채 검증된 최신 Live tail만 append
- Core/Combo1/Combo2 상태와 history 생성
- snapshot과 presentation payload 생성
- chart-ready field 제공

Presentation payload에는 최소한 다음을 포함한다.

- 최종 후보 metadata, 표시명, family, display order, Practical tag
- snapshot, candidate history, 1주 전 state, basis date
- component history와 component kind
- benchmark history
- Combo1용 raw/EMA/threshold 등 chart-ready Core fields
- Combo2용 child Combo1 raw-state history
- 후보·benchmark backtest metric, display asset, evaluation start/end
- Proxy/source/runtime mode metadata
- Frozen cutoff, source observation date, source freshness, Live tail row 수

UI 책임:

- 이미 계산된 payload 표시
- 후보 선택
- 기간 선택
- 표와 차트 렌더링

UI가 직접 하면 안 되는 것:

- 외부 API 호출
- indicator 수식 계산
- hysteresis 계산
- T+1 재적용
- candidate 재선별
- 다른 시장 runtime 호출

Combo1 상세차트는 Core indicator chart-ready series를 사용하고, Combo2 상세차트는 고정된 child Combo1 raw state와 S&P benchmark만 사용한다. 없는 EMA/threshold를 UI에서 만들어내지 않는다.

### Gate 3

- S&P runtime이 다른 시장 runtime을 import하지 않음
- cache/session/widget/chart key 충돌 0
- payload 계산 1회 계약 준수
- 후보·기간 변경으로 runtime 재실행 0
- Frozen prefix parity와 no-overwrite PASS
- 최신 source/availability/freshness 정책이 계약과 일치
- candidate basis date가 provider 관측일이 아닌 마지막 연속 유효 공통 calculation date와 일치
- stale/missing source로 인한 invalid-as-Risk-on 0
- current/1주 전/basis date/history가 동일 payload에서 일관됨

### NASDAQ Live tail 레슨런 적용 Gate

S&P 구현은 아래 항목을 최소 회귀 테스트로 고정한다.

- Frozen cutoff에서 Core/Combo1/Combo2/T+1 replay parity 0 mismatch
- Frozen prefix semantic hash와 행 수가 Live runtime 전후 동일
- fixture Live tail에서 basis date, candidate/component/benchmark history, chart x-end가 유효한 최신 calculation date까지 함께 전진
- stale 또는 누락 source fixture에서 tail withheld, synthetic row 0, state 위조 0
- source observation date와 candidate basis date가 분리되어 기록됨
- 공식 백테스트 display metric은 Frozen cutoff 기준으로 유지됨
- Proxy Only 계약이면 direct OAS 사용 0
- 실제 provider smoke는 최신 유효 미국 거래일을 확인하되, 외부 provider의 일시 장애는 code FAIL이 아니라 `BLOCKED_SPX_LIVE_SMOKE_TRANSIENT_PROVIDER_FAILURE`로 분리

## 단계 4 — UI Clone 및 격리 검증

현재 NASDAQ UI를 단일 시각적 기준으로 사용한다. S&P 지표2는 미국 지수·Final20·Proxy/Frozen 구조가 NASDAQ과 가장 가까우므로, KOSDAQ의 별도 Live UI를 섞어 쓰지 않는다. 기존 페이지 코드를 공통 renderer로 리팩터링하지 않는다.

같게 유지할 것:

- 상단 3줄 요약 구조
- 선택 컨트롤 배치
- 조합 지표와 리스크 기준 영역
- 현재 상태 블록
- 백테스트 비교 표 2개
- 지표별 상태 표
- 상세 차트 순서와 스타일
- divider, 간격, 폰트, 색상, 표 헤더 정렬
- 시장단계 색상 팔레트

섹션 순서는 아래와 같이 고정한다.

```text
상단 divider
-> 3줄 상태 요약
-> divider
-> 프리셋 / 기준지수 / 기간 / 보조선
-> divider
-> 조합 지표 / 리스크 기준
-> divider
-> 현재 상태
-> divider
-> 백테스트 비교 보기 · 조합2
-> 백테스트 비교 보기 · 조합1
-> 지표별 상태 보기
-> Frozen 기준선·Proxy·Live tail source 계약
-> divider
-> 대표 차트
-> divider
-> 상세 지표 차트
-> 고급 정보
```

- 기본 기간은 NASDAQ 기준과 같은 `5년`으로 둔다.
- divider, 간격, 컨트롤 폭, 표 헤더 정렬, 시장단계 팔레트는 NASDAQ 기준을 그대로 복제한다.
- 상단 설명문, refresh UX, source schedule 같은 새 UI는 NASDAQ 기준에 없거나 runtime mode 계약에 없으면 추가하지 않는다.

S&P에 맞게 바꿀 것:

- 페이지/탭 표시명
- benchmark label
- S&P 후보명과 K/L
- S&P 지표명과 source 표시
- S&P asset/runtime/cache/session namespace
- 후보 수와 Practical 집계

### 화면 검증

- Practical 후보 조합1·조합2 각각 5개 표시
- 상단 계산 가능 `5 / 5`
- Risk-off 집계도 `x/5`
- 시장단계가 S&P 후보 5+5만으로 집계
- 백테스트 표의 후보 수 5행
- 1주 전/현재 ON-K 및 시장단계 표시
- 전체 기간 차트 시작일이 공식 평가 시작일
- 조합1/조합2의 5년·전체 차트 모두 `x_end == candidate basis date`
- 각 대표 차트 benchmark trace의 마지막 유효 날짜와 값이 candidate basis date에 정확히 대응
- x축 여백을 만들기 위한 가짜 날짜, synthetic tail, 별도 x-axis padding 0
- Combo1/Combo2 차트 계약이 지켜짐
- S&P Proxy/직접 source 문구가 계약과 일치
- 현재 상태 블록의 기존 `기준일`은 candidate basis date를 표시한다. 별도 상단 카드나 신규 레이아웃을 추가하지 않는다.
- Proxy-only, `^GSPC`, T+1, 0bp, 현금 0%, No Fill, Frozen Final5+5 계약은 기존 Frozen/Proxy 계약 expander 안에 짧게 표시한다.

### Gate 4

- 새 탭 진입 smoke PASS
- 표·차트·expander 렌더 PASS
- UI 구조 parity PASS
- S&P 외 탭 코드/asset/runtime diff 0
- 계산·성과·문구 외 변경 없음

## 단계 5 — 최종 검증 및 배포

커밋 전 확인:

```text
git status --short
git diff --name-only
git diff --stat
git diff --check
python3 -m py_compile <S&P 변경 Python 파일>
pytest <S&P 관련 최소 테스트>
```

커밋에는 S&P 전용 파일과 필요한 최소 테스트만 포함한다. 기존 untracked 산출물은 자동으로 포함하지 않는다.

커밋·push 전 최종 조건:

- 기존 운영 탭 기능·계산·UI 불변
- S&P parity PASS
- UI payload의 Final10 exact ID, K/L, Combo1 component, Combo2 child mapping이 Stage 1 manifest와 모두 일치
- 다른 탭 변경 0
- 예상치 못한 tracked diff 0
- 관련 테스트 PASS

그 후에만 S&P 전용 commit을 만들고 `origin/main`으로 정상 push한다. Cloud에서는 새 revision, 페이지 진입, 후보 집계, 현재 상태, 표, 차트 x_end를 확인한다.

## 실패 시 중단 Gate

다음 중 하나라도 발생하면 임의 보정하지 않는다.

- 후보 ID 또는 child mapping 불명확
- 기준지수 불명확
- source/proxy 계약 불명확
- Frozen asset parity mismatch
- T+1 또는 invalid semantics mismatch
- 다른 탭 diff 발생
- UI에 없는 chart field를 합성해야 함
- 기존 runtime 공통화가 필요함
- 테스트가 기존 기능 변경을 요구함

실패 보고에는 원인, 영향 범위, 필요한 사용자 결정만 남긴다.

## 최종 완료 문구

```text
PASS_SPX_NEW_DASHBOARD_READY
```

위 Gate를 모두 통과했을 때만 사용한다.
