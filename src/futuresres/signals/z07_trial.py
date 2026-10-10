"""Z07's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z07`. decisions.md 111."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from futuresres.signals.z07 import PRIOR_MEAN, PRIOR_SD, TEST_END, TEST_START, direction

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z07_injection.json"
OUT = ROOT / "reports" / "z07_trial.json"
OUT_MD = ROOT / "reports" / "z07_trial.md"


def _sharpe(x) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252))


def _data():
    from futuresres.data.daily_bars import load_market
    from futuresres.signals.z06_trial import window_returns       # MNQ 09:30-16:00, real, cached (decisions.md 110)
    mk = load_market("NQ")
    d, r = window_returns("MNQ")
    m = (d >= np.datetime64(TEST_START)) & (d <= np.datetime64(TEST_END))
    d, r = d[m], r[m]
    s = direction(d.astype("datetime64[D]"), mk.dates.astype("datetime64[D]"), mk.ret)
    ok = np.isfinite(s)
    # the paper's own return, for comparison only: the close-to-close daily return dated on the session
    i = np.searchsorted(mk.dates.astype("datetime64[D]"), d.astype("datetime64[D]"))
    have = (i < len(mk.dates)) & (mk.dates.astype("datetime64[D]")[np.minimum(i, len(mk.dates) - 1)] == d.astype("datetime64[D]"))
    cc = np.where(have, mk.ret[np.minimum(i, len(mk.ret) - 1)], np.nan)
    return d[ok], r[ok], s[ok], cc[ok]


def injection(reps: int = 2000, seed: int = 111) -> int:
    d, r, s, _ = _data()
    x0 = s * r; n = len(x0)
    mu = PRIOR_MEAN / math.sqrt(252) * float(x0.std())
    rng = np.random.default_rng(seed)
    est = np.array([_sharpe(rng.choice(x0 - x0.mean(), size=n, replace=True) + mu) for _ in range(reps)])
    res = {"n_sessions": n, "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()),
           "sd_estimate": float(est.std(ddof=1)), "power_sharpe_gt_0": float((est > 0).mean()),
           "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.03)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    d, r, s, cc = _data()
    x = s * r
    sh, sh_long = _sharpe(x), _sharpe(r)
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / inj["sd_estimate"] ** 2
    post = (PRIOR_MEAN * p0 + sh * p1) / (p0 + p1); post_sd = math.sqrt(1 / (p0 + p1))
    okc = np.isfinite(cc)
    eras = {}
    for name, lo, hi in (("2017-20", "2017-01-01", "2020-12-31"), ("2021-26", "2021-01-01", "2026-12-31")):
        mm = (d >= np.datetime64(lo)) & (d <= np.datetime64(hi))
        eras[name] = {"sessions": int(mm.sum()), "sharpe_signal": _sharpe(x[mm]), "sharpe_long": _sharpe(r[mm]),
                      "short_share": float((s[mm] < 0).mean())}
    c1, c2, c3 = sh > 0, float(x.mean()) > float(r.mean()), post > 0
    out = {"hypothesis": "Z07", "window": [str(d[0]), str(d[-1])], "sessions": int(len(d)),
           "sharpe_signal": sh, "sharpe_always_long": sh_long, "mean_signal_bps": float(x.mean() * 1e4),
           "mean_long_bps": float(r.mean() * 1e4), "short_share": float((s < 0).mean()),
           "mean_bps_on_short_sessions": float(r[s < 0].mean() * 1e4), "mean_bps_on_long_sessions": float(r[s > 0].mean() * 1e4),
           "close_to_close_sharpe_of_rule": _sharpe((s * cc)[okc]), "close_to_close_sessions": int(okc.sum()),
           "posterior": {"mean": post, "sd": post_sd}, "eras": eras,
           "conditions": {"sharpe_gt_0": bool(c1), "beats_always_long": bool(c2), "posterior_gt_0": bool(c3)},
           "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z07", symbol="MNQ",
                           date_range=(out["window"][0], out["window"][1]), status="completed", sharpe=sh / math.sqrt(252),
                           params={"statistic": "annualised Sharpe of MAC(5)-reversal direction x MNQ 09:30-16:00 return",
                                   "sharpe_signal": sh, "sharpe_always_long": sh_long, "posterior_mean": post,
                                   "close_to_close_sharpe_of_rule": out["close_to_close_sharpe_of_rule"], "decision": out["decision"]},
                           note="provenance=native; source=external (Baltussen, van Bekkum & Da 2019), tested 2017-2026 after the paper's sample. decisions.md 111."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    c = s["conditions"]; i = s["injection"]
    rows = ["| period | sessions | signal Sharpe | always-long Sharpe | short share |", "|---|---|---|---|---|"]
    rows += [f"| {k} | {e['sessions']} | {e['sharpe_signal']:+.2f} | {e['sharpe_long']:+.2f} | {e['short_share']:.0%} |" for k, e in s["eras"].items()]
    return "\n".join([
        "# Z07 — index reversal (MAC(5)) sets the MNQ bracket's direction: the trial", "",
        f"**Decision: {s['decision']}.** {s['sessions']} sessions, {s['window'][0]} → {s['window'][1]}; short in {s['short_share']:.0%}.", "",
        f"- Direction × 09:30–16:00 window: Sharpe **{s['sharpe_signal']:+.2f}** (mean {s['mean_signal_bps']:+.2f} bps) — needs > 0: {c['sharpe_gt_0']}.",
        f"- Always long: Sharpe {s['sharpe_always_long']:+.2f} (mean {s['mean_long_bps']:+.2f} bps) — must beat it: {c['beats_always_long']}. "
        f"Window mean on short sessions {s['mean_bps_on_short_sessions']:+.2f} bps, on long sessions {s['mean_bps_on_long_sessions']:+.2f} bps.",
        f"- Posterior {s['posterior']['mean']:+.2f} ± {s['posterior']['sd']:.2f} — needs > 0: {c['posterior_gt_0']}.",
        f"- For comparison with the paper (not decisive): the same rule on the close-to-close daily return, Sharpe {s['close_to_close_sharpe_of_rule']:+.2f} ({s['close_to_close_sessions']} sessions).", "",
        *rows, "",
        f"Outcome injection: {i['sought_sharpe']} planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); P(estimate > 0) {i['power_sharpe_gt_0']:.0%}.", ""])
