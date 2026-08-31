# NASDAQ Macro8 D0 Contract Freeze

## Gate

`PASS_NASDAQ_MACRO8_D0_OPERATING_CONTRACT_FREEZE_READY`

## Fixed Final20

- Excel filter: `tier == Primary` only
- Combo1 Performance: `5/5` source-exact
- Combo1 Practical: `5/5` source-exact
- Combo2 Performance: `5/5` source-exact
- Combo2 Practical: `5/5` source-exact
- Reserve candidates used: `0`
- Combo2 child mapping: `84` rows / `30` unique Combo1 definitions
- Core definitions resolved against NQ-3 and NQ-4R: `48/48`

## Frozen execution contract

- Benchmark: `^NDX` Nasdaq-100 Index; QQQ is excluded.
- Evaluation: `2008-04-01` through `2026-08-21`.
- Core state: canonical T+1 exactly once; Combo1/Combo2 receive the canonical state directly with no additional shift.
- Combo2 input: child Combo1 raw risk state.
- Missing state: fail closed; it is not converted to Risk-on or Risk-off.
- Transaction cost: `10` bps on final position changes.

## Scope

- Existing dashboard code/UI/runtime modified: `0`
- Existing tabs modified: `0`
- Research repo modified: `0`
- Commit/push/deploy: `0`

Stage 2 may build dashboard-owned immutable assets only from this contract and its pinned source inventory.
