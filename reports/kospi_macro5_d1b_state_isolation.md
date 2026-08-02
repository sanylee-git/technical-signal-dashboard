# KOSPI Macro5 D1-B State Isolation

- Macro5 namespace: `macro5_kospi_*`
- Existing Macro4 keys reused in Macro5: `0`
- Shared session key count: `0`
- Duplicate widget key count: `0`
- Shared mutable preset object count: `0`
- Cache collision count: `0`
- Cross-loader call count: `0`
- Macro5 network request count: `0`

Macro5 KOSPI loaders read only `kospi_macro5_assets/` files at runtime. They do not call Yahoo, FRED, Macro4 loaders, or S&P benchmark loaders.
