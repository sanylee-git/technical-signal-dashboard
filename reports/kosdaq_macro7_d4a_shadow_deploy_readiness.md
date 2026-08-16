# KOSDAQ Macro7 D4A - Shadow Deploy Readiness

## Result

`BLOCKED_KOSDAQ_MACRO7_D4_SHADOW_TARGET_NOT_RESOLVED`

Additional required substatus:

`BLOCKED_KOSDAQ_MACRO7_D4_CLOUD_OBSERVABILITY_CONTRACT_INSUFFICIENT`

No commit, push, deployment, application-code, runtime, asset, config, or
dependency-file change was made. The only D4A writes are this report and the
paired release manifest.

## Local Baseline and Regression

- Local HEAD and `origin/main`: `1e4cd49a894189ea5211e706449c9d93f66d20db`.
- Stage 4 UI baseline SHA: PASS (`19190339...deddf12`).
- Stage 3.1 presentation baseline SHA: PASS (`409227c2...ccaebf`).
- `python3 -m py_compile technical_signal_dashboard.py kosdaq_macro7_ui.py`: PASS.
- Stage 1 to D3 targeted suite: `17 passed`.
- Full suite: `126 passed, 21 existing warnings`.

The warnings are existing pandas/yfinance warnings from Macro5/Macro6 tests;
there were no test failures.

## Local Live Smoke

One real local `run_live_runtime -> build_presentation_payload` execution
completed with 10/10 Final10 candidates usable. The market's last valid close
and every candidate basis date were `2026-08-14`; invalid-to-Risk-on count was
zero; Combo2 input remained `CHILD_COMBO1_RAW_RISK_STATE`; final T+1 count was
one. Source freshness contained ten `FRESH` rows and one expected weekly
release row. Values are recorded in the paired manifest.

## Deployment Contract Audit

- Entrypoint present: `market_macro_dashboard.py`, which invokes the actual
  dashboard with `page=market_macro`.
- Dependency file present: `requirements.txt`.
- Required Macro7 third-party packages are available through the dependency
  contract: Streamlit, pandas, numpy (pandas dependency), Plotly, and requests
  through pinned yfinance's declared dependency. `streamlit-autorefresh` is
  optional in the existing application and is not imported by Macro7.
- No repository deployment workflow, provider config, production target, or
  existing Shadow/staging target was found.
- The local Streamlit secret file is ignored and excluded. Macro7 does not read
  secrets or environment variables. No secret value was inspected or recorded.
- Absolute research paths occur only in immutable provenance fields inside
  frozen manifests. Macro7 runtime reads its local copied assets by module-
  relative path and does not consume those provenance paths as runtime inputs.

## Cloud Observability Matrix

| Validation item | Existing evidence in repository | Observable now? |
|---|---|---|
| Deployed revision / commit SHA | No provider metadata or workflow | No |
| Cloud build and startup result | No provider target | No |
| KOSDAQ last valid close/date | Local runtime only; not existing Cloud diagnostic | No |
| Source/freshness status | Selected UI summaries only; no Cloud runtime diagnostic | No |
| Final10 usability and all basis dates | No Cloud payload/log evidence | No |
| Current state, active count, T+1 | Selected UI state is partial evidence only | No |
| Chart x-end <= basis date | No existing Cloud diagnostic evidence | No |
| KOSPI/KOSDAQ session isolation | Requires a resolved normal Shadow browser session | No |
| Candidate/period cache refetch | No existing Cloud log or diagnostic evidence | No |

Because a Shadow target and the necessary normal evidence paths are both
unresolved, deploying to `origin/main` would risk touching the existing
production deployment without proving the requested Shadow conditions.

## Required User Decision Before D4B

Provide or approve an existing Shadow/staging deployment target and its normal
access/observability method. D4B must then use only that existing target, a
precisely reviewed allowlist, and explicit external-mutation approval. No new
diagnostic code or hidden UI is authorized in Stage 5.
