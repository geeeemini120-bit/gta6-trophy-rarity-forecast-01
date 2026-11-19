"""GTA VI trophy rarity forecast for make.fun's gta6-trophy-rarity-forecast-01.

Forecasts every trophy's earn rate on Exophase at the case's target, as five
quantiles, from the house's recorded reads of the game's trophy page.

How it works
------------
A trophy's rate is earners divided by players tracked. The program works in
the same space the score uses -- the logit of the rate -- and fits, per
trophy, a straight line of logit(rate) against log time since release
(log(1 + hours since 2026-11-19T00:00Z)):

* The fit uses the last 24 hours of reads, weighted by recency (24 h
  half-life), because the page moves in refresh steps and a launch's growth
  bends in log time: an average slope over two days understates the slope
  the game is on now.
* Each trophy's slope is shrunk toward the mean slope of its tier
  (platinum, gold, silver, bronze), so rare trophies with noisy counts
  borrow strength from their tier.
* The line is read at the target to give the median. Log time saturates,
  so a two-day history extrapolated four and a half days out does not run
  away the way a straight line in time would, and the logit itself
  saturates at 100%, so a fast-rising early trophy cannot be forecast
  above every player holding it.

When the whole history is flat -- every read identical, the page not yet

When the whole history is flat -- every read identical, the page not yet
refreshed -- no trend can be fitted. The program then falls back to a
refresh prior instead of pure persistence: Exophase refreshes a game's
counts on its own schedule, and a refresh dilutes rates because the newly
tracked players hold fewer trophies than the early syncers. The median is
pulled down by a dilution factor that grows with how stale the page already
is plus the horizon, and the lower quantiles are widened more than the upper
ones, since a refresh can only push rates down in the short run.

The spread combines the fit's own prediction error with a random-walk term
that grows with the square root of the horizon, and is turned into
quantiles on the logit scale. Everything is deterministic: no randomness,
no wall-clock reads, no network, standard library only.
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the five levels.
Z_SCORES = [-1.6448536269514722, -0.6744897501960817, 0.0,
            0.6744897501960817, 1.6448536269514722]

# Release day, midnight UTC: the origin of the log-time axis.
RELEASE = datetime(2026, 11, 19, tzinfo=timezone.utc)

# --- small numeric helpers -------------------------------------------------

def clamp_rate(pct):
    """Keep a percent inside the range the logit can take."""
    return min(99.99, max(0.01, pct))


def logit(pct):
    p = clamp_rate(pct)
    return math.log(p / (100.0 - p))


def inv_logit(value):
    if value >= 0:
        return 100.0 / (1.0 + math.exp(-value))
    e = math.exp(value)
    return 100.0 * e / (1.0 + e)


def round4(x):
    """Round to 4 decimals, halves away from zero, like the starter does."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value == int(value) else value


def parse_time(text):
    """Parse an ISO 8601 UTC timestamp (with or without a trailing Z)."""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def log_time(moment):
    """Log hours since release: ln(1 + hours), floored so it stays defined."""
    hours = (moment - RELEASE).total_seconds() / 3600.0
    return math.log(1.0 + max(hours, -0.9))


# --- weighted least squares -------------------------------------------------

def weighted_fit(xs, ys, ws):
    """Weighted straight-line fit. Returns (slope, intercept, resid_var,
    slope_var, x_bar, sxx, n_eff) or None when there is nothing to fit."""
    sw = sum(ws)
    if sw <= 0 or len(xs) < 1:
        return None
    x_bar = sum(w * x for w, x in zip(ws, xs)) / sw
    y_bar = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - x_bar) ** 2 for w, x in zip(ws, xs))
    if sxx <= 1e-12:
        return (0.0, y_bar, 0.0, float("inf"), x_bar, sxx,
                sw * sw / sum(w * w for w in ws))
    sxy = sum(w * (x - x_bar) * (y - y_bar)
              for w, x, y in zip(ws, xs, ys))
    slope = sxy / sxx
    intercept = y_bar - slope * x_bar
    n = len(xs)
    if n > 2:
        # Plain residual variance; the weights only shape the fit itself.
        resid_var = sum((y - (intercept + slope * x)) ** 2
                        for x, y in zip(xs, ys)) / (n - 2)
    else:
        resid_var = 0.0
    slope_var = resid_var / sxx if resid_var > 0 else float("inf")
    n_eff = sw * sw / sum(w * w for w in ws)
    return (slope, intercept, resid_var, slope_var, x_bar, sxx, n_eff)


# --- the forecast -----------------------------------------------------------

def forecast_case(case):
    trophies = case["trophies"]
    history = case["history"]
    if not history:
        raise ValueError("case %s has no history" % case.get("id", "?"))
    horizon_days = case["horizon_minutes"] / 1440.0
    target = parse_time(case["target"])
    x_target = log_time(target)

    # Read times and the players-tracked series.
    read_times = [parse_time(read["at"]) for read in history]
    last_time = read_times[-1]
    first_time = read_times[0]
    counts = [read["players_tracked"] for read in history]

    # Fit on the recent window: the last 24 hours of reads (all of them when
    # the history is shorter). A launch's growth bends in log time, so an
    # average slope over two days understates the slope the game is on now;
    # the recent window tracks the current trend instead.
    recent = [j for j, t in enumerate(read_times)
              if (last_time - t).total_seconds() <= 86400.0]
    if len(recent) < 3:
        recent = list(range(len(history)))
    xs_all = [log_time(t) for t in read_times]
    xs = [xs_all[j] for j in recent]

    # Recency weights: a read a day old counts half as much as the latest.
    ws = [0.5 ** ((last_time - read_times[j]).total_seconds() / 86400.0)
          for j in recent]

    # Is the page flat -- no refresh at all in the history?
    flat = (len(set(counts)) == 1 and all(
        read["rates"] == history[0]["rates"] for read in history))

    # Fit logit(rate) against log time, on the recent window.
    tier_slopes = {}
    tier_counts = {}
    fits = []
    for i, trophy in enumerate(trophies):
        ex, ey, ew = [], [], []
        for k, j in enumerate(recent):
            read = history[j]
            rate = read["rates"][i]
            if rate is None:
                continue
            ex.append(xs[k])
            ey.append(logit(rate))
            ew.append(ws[k])
        fit = weighted_fit(ex, ey, ew) if ex else None
        fits.append(fit)
        if fit is not None:
            tier = trophy["tier"]
            tier_slopes[tier] = tier_slopes.get(tier, 0.0) + fit[0]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
    global_slope = (sum(f[0] for f in fits if f is not None)
                    / max(1, sum(1 for f in fits if f is not None)))
    tier_mean = {}
    for tier, total in tier_slopes.items():
        n_tier = tier_counts[tier]
        tier_mean[tier] = total / n_tier if n_tier >= 3 else global_slope

    # Prior spread of a slope around its tier mean (log units).
    PRIOR_SLOPE_VAR = 0.25

    rows = []
    for i, trophy in enumerate(trophies):
        last_rate = history[-1]["rates"][i]
        if last_rate is None:
            last_rate = 0.0
        fit = fits[i]
        if fit is None:
            slope, inter = 0.0, logit(last_rate)
            resid_var, slope_var, x_bar, sxx, n_eff = 0.0, float("inf"), xs[-1], 0.0, 1.0
        else:
            slope, inter, resid_var, slope_var, x_bar, sxx, n_eff = fit
            # Shrink the slope toward the tier mean, precision-weighted.
            prior_mean = tier_mean.get(trophy["tier"], global_slope)
            if math.isfinite(slope_var) and slope_var > 0:
                w_data = 1.0 / slope_var
                w_prior = 1.0 / PRIOR_SLOPE_VAR
                slope = (slope * w_data + prior_mean * w_prior) / (w_data + w_prior)
            else:
                slope = prior_mean
            # Re-anchor the line at the fitted centre, so the shrunk slope
            # still passes through the weighted mean of logit rates.
            y_bar = inter + fit[0] * x_bar
            inter = y_bar - slope * x_bar

        median = clamp_rate(inv_logit(inter + slope * x_target))

        # Prediction error on the logit scale, plus a random-walk term that
        # grows with the horizon.
        if fit is not None and sxx > 1e-12 and math.isfinite(slope_var):
            var_fit = resid_var * (1.0 / max(n_eff, 1.0)
                                   + (x_target - x_bar) ** 2 / sxx)
        else:
            var_fit = 0.04
        rw_var = (0.35 * math.sqrt(horizon_days)) ** 2
        sigma_logit = math.sqrt(var_fit + rw_var + 0.02)

        if flat:
            # Refresh prior: the page has been stale for a while already and
            # the horizon gives it more time to refresh. A refresh dilutes
            # each rate toward the newcomers' lower earn rate; the dilution
            # is strongest for rare trophies and vanishes at 100%.
            stale_hours = (last_time - first_time).total_seconds() / 3600.0
            horizon_hours = case["horizon_minutes"] / 60.0
            refresh_weight = min(1.0, (stale_hours + horizon_hours) / 6.0)
            dilution = 0.25 * refresh_weight
            median = clamp_rate(last_rate * (1.0 - dilution * (1.0 - last_rate / 100.0)))
            sigma_down = math.sqrt(sigma_logit ** 2 + 0.35 ** 2)
            sigma_up = math.sqrt(sigma_logit ** 2 + (0.35 * math.sqrt(horizon_days)) ** 2)
        else:
            sigma_down = sigma_logit
            sigma_up = sigma_logit

        # Quantiles on the logit scale, with the spread floored and capped.
        centre = logit(median)
        sig_down = min(2.5, max(0.15, sigma_down))
        sig_up = min(2.5, max(0.15, sigma_up))

        quantiles = []
        for level, z in zip(LEVELS, Z_SCORES):
            spread = sig_down if z < 0 else sig_up
            value = inv_logit(centre + z * spread)
            quantiles.append(round4(min(99.99, max(0.01, value))))
        # Rounding can only break monotonicity by a hair; repair it.
        for k in range(1, 5):
            if quantiles[k] < quantiles[k - 1]:
                quantiles[k] = quantiles[k - 1]
        rows.append({"id": trophy["id"], "q": quantiles})

    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / (path.stem + ".out")).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
