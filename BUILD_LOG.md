# BUILD_LOG — gta6-trophy-rarity-forecast-01

Entry: forecast each GTA VI PS5 trophy's Exophase earn rate at 2026-11-26T00:00:00Z,
as five quantiles (0.05 / 0.25 / 0.5 / 0.75 / 0.95), scored by mean pinball loss
on the logit scale. Program: `main.py`, Python 3.13, standard library only, no
network, deterministic.

## Anchor

`makefun anchor ac89dae2196403a34766a05867cafc3ac5b009ee round 34094971`
(run in this session, before the first counted write; see the session record.)

## Approach

A trophy's rate is earners / players tracked. The forecast is made in the same
space the score uses — the logit of the rate — by fitting, per trophy, a
straight line of logit(rate) against log time since release, ln(1 + hours
since 2026-11-19T00:00Z):

- **Recent window.** The fit uses the last 24 hours of reads, weighted by
  recency (24 h half-life). The page moves in refresh steps and a launch's
  growth bends in log time, so an average slope over two days would understate
  the slope the game is on now.
- **Tier shrinkage.** Each trophy's slope is shrunk toward the mean slope of
  its tier (platinum / gold / silver / bronze), precision-weighted, so rare
  trophies with noisy counts borrow strength from their tier. The shrunk line
  is re-anchored through the fitted centre (weighted mean of logit rates).
- **Saturating extrapolation.** Log time saturates, so a two-day history
  extrapolated 4.5 days out does not run away; the logit itself saturates at
  100%, so a fast-rising early trophy cannot be forecast above every player
  holding it.
- **Spread.** The logit spread combines the fit's prediction error
  (residual variance, growing with distance from the fitted centre) with a
  random-walk term, 0.35 * sqrt(horizon in days), and is floored at 0.15 and
  capped at 2.5 logit units.

### Flat history — the refresh prior

When the whole history is flat (every read identical, the page not yet
refreshed), no trend can be fitted. The program then does **not** persist the
last rates. Exophase refreshes a game's counts on its own schedule, and a
refresh dilutes rates because newly tracked players hold fewer trophies than
the early syncers. So the median is pulled down by a dilution factor whose
centre is 0.25 — the dilution the kit documents for the first refresh
(aggregate trophies-per-player 1.478 → 1.105) — scaled by
min(1, (staleness + horizon) / 6 h), and the lower quantiles are widened more
than the upper ones (extra 0.35 logit units downward), since a refresh can
only push rates down in the short run. The dilution vanishes at 100%: the
universal trophy ("Just Like Paradise", held by every tracked player) stayed
at 100% through the first refresh, so its median stays at 99.99.

## Why it should beat the house baseline

The house baseline persists the last rates with a narrow random-walk spread.
It scores ~1.51 loss on the practice with 90% coverage 0, because the
refresh that straddles both practice cases takes every rate outside its band.
This entry differs in the two places that cost the baseline:

1. **Median, not just spread.** On flat history the medians sit ~17–19%
   below the last rates (the refresh prior), in the direction the refresh
   moves every rate. On a rich final history the medians follow each trophy's
   fitted trend instead of standing still.
2. **Honest spread.** The 90% band is ~2.8x wider than the baseline's in
   logit units on the practice (1.16 vs 0.41), and it is asymmetric when a
   refresh is the main risk, so a refresh lands inside the band instead of
   below all of it.

## Local validation (Python 3.12.3; grader runs 3.13, code uses nothing newer)

Practice cases, run from the repo dir:
`MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=/tmp/trophy-out python3 main.py`

- **Format:** p00.out and p01.out both VALID — exactly 55 rows, ids 1–55 once
  each, five finite non-decreasing quantiles in [0, 100], 2,797 / 2,749 bytes
  (cap 65,536).
- **Determinism:** two full runs byte-identical (`cmp` clean on both cases).
- **Runtime:** 0.064 s and 0.060 s per run over both cases (cap 8 s per case).
- **Baseline comparison (kit starter, same cases):** medians 17.2% (p00) /
  19.3% (p01) below baseline at most, mean −16.8% / −18.9%, max 0.0% (the
  100% trophy is unchanged). All 54 non-100 trophies have medians below their
  last rate. Mean 90% band width 1.16 logit units vs baseline 0.41.

## Synthetic trend tests (in /tmp, never in the repo)

1. **Exponential-growth case** (N 638 → 20,000, easy trophy 1.25% → 18%,
   platinum 0.63% → 0.40%, mid 2.04% → 6% over 48 h, target 4.5 days out):
   directions all correct — platinum median 0.28 (below last 0.40), mid 14.5
   (above 6), easy 72.1 (above 18, saturating in logit space instead of
   running to 99.99). An earlier log-count version of the model failed this
   test (medians barely moved); the logit-space version with the recent-window
   fit fixed it.
2. **Model-family case** (289 reads every 10 min over 48 h, logit rates
   exactly linear in log time, target 7 days out): median recovery near-exact
   — mean |logit error| 0.001 over all 55 trophies, max 0.034 (platinum).

## Files

- `main.py` — the entry (stdlib only).
- `.makefun/owner.json` — `{"wallet": "4Zb5DbPrhsMwp5wSno2oYZVXXgYkF73m1tiSruTffUGJ"}`.
- `LICENSE` — MIT, written by `makefun init`.
- `BUILD_LOG.md` — this file. `README.md` — short entry description.

## Notes for the parent (submission steps, not done here)

- Do NOT run `makefun record` for this bounty (transcript uploads via bundle,
  not sealed recordings; record refuses with HTTP 400).
- Kit-level note printed by init: "this kit copy is level 26 and
  https://make.fun is at level 27: a current kit reads, bundles or sends what
  this copy cannot." The parent should consider re-downloading the kit before
  bundling/checking; the build itself used only the kit's input data and rules,
  which are unchanged by that note.
- No GitHub repo created, no push, no bundle, no submit — parent's job after
  the user creates the repo and sets its About.
