# NEEDLE-03 — BTC/ETH beta core (Stage 3)

**Brad GO:** Stage 3 live clip (2026-09-30). Not Stage 4 size-up.

## Contract

When `regime_layer` is `soft_up` / `climb` / `pre_bull`, **or** regime `transition` + `deploy`:

- Hold a **beta core** in BTC+ETH. Target **40–55% of equity** is the *end state*, not the first order.
- **First clip:** $200–$400 (default $300), split **60/40 BTC/ETH**.
- Core **ignores** tryout 0.30 sentiment floor.
- Core **does not** attach a 3% stop. Structure / 6–8% SL is NEEDLE-04; until then **no native SL on core**.
- Alts stay on the $25 tryout sleeve.
- Bear / `usdc_park` → no core buys.
- Keep ~$150 USD tryout powder. Unwind USDC **only** enough for clip + reserve. Do not dump the $2k park.

## Must not

- 40% of book overnight
- `enforce: false`
- Market-IOC fallback
- Stage 4 / NEEDLE-05 size split until 14d on this clip
