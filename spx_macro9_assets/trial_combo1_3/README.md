# S&P2 Combo1 Three-Candidate Visual Trial

This is a read-only visual review view, not a live or production signal feed.

- Models shown: `3e12d084c6d477f9341a659b`, `1cb2304e4f83508d7d20b788`, `9b0bf6eb468f0e0f9ead4022`
- Model family: Combo1 only; Combo2 count is zero.
- Frozen evaluation range: 2008-04-01 through 2026-08-21 (4,628 sessions).
- No post-cutoff live tail is included.
- UI reads these materialized Parquet assets and does not fetch data or calculate model states.
- The builder validates corrected Single69 raw values/events and each candidate's Official T+1 state against the pinned source runs before writing the payload.

The complete source/output lineage and QA counts are in `trial_asset_manifest.json`.
