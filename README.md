# GTA VI Trophy Rarity Forecast

Entry for make.fun's `gta6-trophy-rarity-forecast-01` bounty: forecast every
Grand Theft Auto VI PlayStation 5 trophy's earn rate on Exophase at
2026-11-26T00:00:00Z, as five quantiles per trophy, scored by mean pinball
loss on the logit scale.

## How it works

`main.py` (Python 3.13, standard library only, no network, deterministic)
reads every `<id>.in` case and writes one `<id>.out` per case. Per trophy it
fits a straight line of logit(rate) against log time since release, using the
last 24 hours of reads with recency weights, shrinks each slope toward its
tier's mean slope, and reads the line at the target for the median. The
spread combines the fit's prediction error with a random-walk term that grows
with the horizon.

When the history is flat — the page not yet refreshed — it does not just
persist the last rates: it applies a refresh prior, pulling medians down
(newly tracked players hold fewer trophies) and widening the lower quantiles,
because Exophase refreshes a game's counts on its own schedule and a refresh
dilutes every rate except the universal one.

See `BUILD_LOG.md` for the validation numbers (practice format checks,
determinism, runtimes, baseline comparison, synthetic trend tests).
