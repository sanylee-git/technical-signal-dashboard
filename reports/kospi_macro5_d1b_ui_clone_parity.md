# KOSPI Macro5 D1-B UI Clone Parity

- Gate: `PASS_KOSPI_MACRO5_D1B_FROZEN_SHADOW_PAGE_READY`
- Page key: `macro5_kospi`
- Page label: `🇰🇷 매크로 지표 5`
- Macro4 hash before: `619ea6d2aa80cb8decb86edaddce22845b3babe8a905c7b772aa8328896d262a`
- Macro4 hash after: `619ea6d2aa80cb8decb86edaddce22845b3babe8a905c7b772aa8328896d262a`
- Macro4 modified: `False`

## Structure

Macro5 KOSPI follows the Macro4 control flow: helper text, common CSS, preset/benchmark/period/raw toggle controls, component/K-L row, status cards, backtest expander, status expander, main chart, component expanders.

Allowed differences:

- S&P/Nasdaq data adapter replaced by frozen KOSPI assets.
- Editable Macro4 indicator settings replaced by read-only Final9 details.
- Component chart raw threshold lines are not bundled; component state charts are shown instead.

Unexplained UI differences: `0` by source review.

Review flags:

- `RECOMPUTED_COMBO1_REFERENCE_DISPLAY_REVIEW`
- `FROZEN_COMPONENT_RAW_LINE_NOT_BUNDLED_REVIEW`
- `VISUAL_SCREENSHOT_TOOL_UNAVAILABLE_REVIEW`
- `EXISTING_WORKTREE_DIFF_REVIEW`
