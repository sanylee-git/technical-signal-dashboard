# KOSPI Macro5 D1-B Implementation Review

## Summary

- Final Gate: `PASS_KOSPI_MACRO5_D1B_FROZEN_SHADOW_PAGE_READY`
- D1-A Gate: `PASS_WITH_RECOMPUTED_COMBO1_REFERENCE_SIGNALS`
- D1-B UI Asset Gate: `PASS_KOSPI_MACRO5_D1B_UI_ASSET_COVERAGE`
- Final9 selector count: `9`
- Combo1 / Combo2: `4` / `5`
- Frozen 기준일: `2026-07-28`
- Reference signal rows: `51,733`
- Component signal rows: `478,803`

## Parity

- Raw mismatch: `0`
- T+1 mismatch: `0`
- Start event mismatch: `0`
- End event mismatch: `0`

## Runtime Contract

- Frozen reference mode: `true`
- Live extension connected: `false`
- Final9 aggregate vote: `false`
- Official operating model: `false`
- Network loader in Macro5 KOSPI: `0`

## Candidate Reference Types

slot,model_type,role,candidate_id,source_signal_parity
1,combo1,균형 코어,combo1_n11_k9_l5_b984a8e53ad69a2d,PASS_VS_STAGE06A_RAW_BANK
2,combo1,방어 코어,combo1_n11_k8_l5_93919287424179bd,PASS_VS_STAGE06A_RAW_BANK
3,combo1,공격 수익,combo1_n11_k9_l6_ad654f06d0d609cb,RECOMPUTED_FROM_CORE15_COMPONENTS
4,combo1,고수익·독립,combo1_n11_k9_l6_9f0105582a0f0745,RECOMPUTED_FROM_CORE15_COMPONENTS
5,combo2,균형·강건,m6::combo2_m6_k4_l2_2d90a80e824f7336,PASS_STORED_STAGE07C2_DAILY_SIGNAL
6,combo2,성과 코어,m6::combo2_m6_k4_l3_f976de57b8b4a80e,PASS_STORED_STAGE07C2_DAILY_SIGNAL
7,combo2,MDD·Calmar 앵커,m5::combo2_m5_k2_l1_2bc7e194fdecfd9e,PASS_STORED_STAGE07C2_DAILY_SIGNAL
8,combo2,최상위 성과,m10::combo2_m10_k7_l4_bbd8c760d49b44bb,PASS_STORED_STAGE07C2_DAILY_SIGNAL
9,combo2,다양성·안정 보완,m8::combo2_m8_k5_l4_cee6978af4789711,PASS_STORED_STAGE07C2_DAILY_SIGNAL

