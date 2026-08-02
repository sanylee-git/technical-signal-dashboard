# KOSPI Macro5 D1-A Runtime Asset & Historical Parity

- Gate: `PASS_WITH_RECOMPUTED_COMBO1_REFERENCE_SIGNALS`
- Scope: UI code was not modified in D1-A.
- Final9 status: `manual_user_selected_final9=true`, `official_operating_model=false`, `shadow_mode=true`.
- Candidates: 9 total (4 Combo1, 5 Combo2)
- Reference signal rows: 51,733 (1996-12-11 ~ 2026-07-28)

## Source Resolution
| slot | model_type | role | candidate_id | K | L | source_label | source_signal_parity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combo1 | 균형 코어 | combo1_n11_k9_l5_b984a8e53ad69a2d | 9 | 5 | stage05e_a3_cycle_aware_review20 | PASS_VS_STAGE06A_RAW_BANK |
| 2 | combo1 | 방어 코어 | combo1_n11_k8_l5_93919287424179bd | 8 | 5 | stage05e_a2_relaxed_review20 | PASS_VS_STAGE06A_RAW_BANK |
| 3 | combo1 | 공격 수익 | combo1_n11_k9_l6_ad654f06d0d609cb | 9 | 6 | stage05e_a2_relaxed_review20 | RECOMPUTED_FROM_CORE15_COMPONENTS |
| 4 | combo1 | 고수익·독립 | combo1_n11_k9_l6_9f0105582a0f0745 | 9 | 6 | stage05e_a3_cycle_aware_review20 | RECOMPUTED_FROM_CORE15_COMPONENTS |
| 5 | combo2 | 균형·강건 | m6::combo2_m6_k4_l2_2d90a80e824f7336 | 4 | 2 | stage07c2_proposed_decision10 | PASS_STORED_STAGE07C2_DAILY_SIGNAL |
| 6 | combo2 | 성과 코어 | m6::combo2_m6_k4_l3_f976de57b8b4a80e | 4 | 3 | stage07c2_proposed_decision10 | PASS_STORED_STAGE07C2_DAILY_SIGNAL |
| 7 | combo2 | MDD·Calmar 앵커 | m5::combo2_m5_k2_l1_2bc7e194fdecfd9e | 2 | 1 | stage07c2_proposed_decision10 | PASS_STORED_STAGE07C2_DAILY_SIGNAL |
| 8 | combo2 | 최상위 성과 | m10::combo2_m10_k7_l4_bbd8c760d49b44bb | 7 | 4 | stage07c2_proposed_decision10 | PASS_STORED_STAGE07C2_DAILY_SIGNAL |
| 9 | combo2 | 다양성·안정 보완 | m8::combo2_m8_k5_l4_cee6978af4789711 | 5 | 4 | stage07c2_proposed_decision10 | PASS_STORED_STAGE07C2_DAILY_SIGNAL |

## Combo1 Stored Reference Parity
| candidate_id | reference_source | common_rows | mismatch_count | reference_column |
| --- | --- | --- | --- | --- |
| combo1_n11_k9_l5_b984a8e53ad69a2d | stage06a_combo1_main32_raw_risk_state_bank | 4513 | 0.0 | c26 |
| combo1_n11_k8_l5_93919287424179bd | stage06a_combo1_main32_raw_risk_state_bank | 4513 | 0.0 | c13 |
| combo1_n11_k9_l6_ad654f06d0d609cb | no_stored_raw_bank_match | 0 | nan | None |
| combo1_n11_k9_l6_9f0105582a0f0745 | no_stored_raw_bank_match | 0 | nan | None |

## Macro4 Reference
- Macro4 render slice: `technical_signal_dashboard.py:13545`
- Macro4 slice hash: `619ea6d2aa80cb8decb86edaddce22845b3babe8a905c7b772aa8328896d262a`

## D1-B Guardrails
- Clone Macro4 structure only after this D1-A asset is accepted.
- Use `macro5_kospi_*` namespace for session_state, widget keys, cache, debug events, and loaders.
- Do not share mutable Macro4 preset dictionaries or cache keys.
- Keep `official_operating_model=false` until separate user approval.
