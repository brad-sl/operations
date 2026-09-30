# NEEDLE-05 size split — FLAG OFF

Shadow sizer only. **No live 40–55% clip.**

- `allocator.min_move_usd` is already **25** (matches $25 tryout). Isolation: tryout is not dropped.
- `max_deployable_usd` 1000 vs equity ~$2,282: core uses the beta_core planner ($300 clips, ~26% now). 40–55% would be ~$900–$1,250 — **not this card**.
- Code: `phase6/core/needle05_size_split.py` (`enabled=False`).
- Live apply of the envelope is a **new Brad GO**.
