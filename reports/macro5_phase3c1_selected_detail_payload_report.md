# Macro5 Phase 3-C1 Selected Detail Payload

## Gate

PASS_MACRO5_PHASE3C1_SELECTED_DETAIL_PAYLOAD_READY

## Change Summary

- Split Macro5 live page payload into common summary/history data plus selected-candidate component detail.
- Removed the full Final9 `component_signal_history` DataFrame from the common cached payload.
- Added `build_selected_component_signal_history()` to reconstruct only the selected candidate's component history from cached Core15/child Combo1 histories and filtered frozen reference rows.
- Kept source fetch, retry, freshness, Core15 calculation, Combo1/Combo2 semantics, T+1, market stage, UI layout, charts, and backtest values unchanged.

## Runtime Measurement

- `component_signal_history_present`: False
- `component_signal_history_mode`: selected_detail_only
- common payload DataFrame memory: 107.35 MB
- selected detail sample: `combo1_n11_k8_l5_93919287424179bd`
- selected detail shape: 80,245 rows x 15 columns
- selected detail memory: 40.20 MB

Previous read-only audit found the full common `component_signal_history` payload at about 222 MB and the total returned DataFrame payload at about 347 MB.

## Validation

- Selected component history equals the corresponding slice from the full legacy builder for Combo1 and Combo2 samples.
- Selected detail helper does not fetch live sources or recompute the live tree.
- Macro5 latest-history, chart regression, page wiring, table UI, and visual parity tests passed.
- Macro4 detail chart cache and summary snapshot tests passed.
