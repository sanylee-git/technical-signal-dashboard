# KOSPI Macro5 Preimplementation Audit

- D1-A created runtime assets only; `technical_signal_dashboard.py` was not edited.
- Macro4 and Macro5 must be state/cache isolated in D1-B.
- Allowed D1-B changes: new Macro5 KOSPI route/renderer, KOSPI asset loader, KOSPI signal adapter, KOSPI-only widget keys.
- Forbidden D1-B changes: Macro4 design/function redesign, Macro4 cache/session mutation, shared mutable preset dictionaries.

- Macro4 slice hash: `619ea6d2aa80cb8decb86edaddce22845b3babe8a905c7b772aa8328896d262a`
