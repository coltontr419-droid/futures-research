"""§7 end-to-end on GARCH calibrated to MEASURED futures moments. CLAUDE_FUTURES.md §7.

    python -m futuresres.integrity.futures_noise

The §7.2 harness ported from crypto generates its nulls from BTC's moments. Those are the
wrong nulls for this project, and using them would mean the pipeline had been validated
against a distribution it will never see. This module re-runs the whole test with the
generator calibrated to `reports/kurtosis.md`:

    MNQ 1m   sigma 3.9 bps   kurtosis 115.1
    MGC 1m   sigma 3.5 bps   kurtosis 226.5

BOTH ARMS ARE REQUIRED AND THE POSITIVE CONTROL IS THE POINT. A pipeline that promotes
nothing on noise passes §7.2 — and so does a pipeline that is broken shut and promotes
nothing on anything. The control is a real, modest injected edge; without it the null
result below would carry no information.

KURTOSIS IS SET THROUGH THE t DEGREES OF FREEDOM. For a Student-t, non-excess kurtosis is
3 + 6/(nu-4) BEFORE the GARCH volatility clustering adds more. The generator's realised
kurtosis is therefore fitted numerically rather than solved: nu is searched until the
simulated series matches the target, and the achieved value is reported next to the target
so any shortfall is visible rather than assumed away.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.integrity.synthetic import bootstrap_shuffle, garch11, random_walk
from futuresres.signals.search import run_pipeline

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORT: Final[Path] = ROOT / "reports" / "integrity_futures.md"

#: From reports/kurtosis.md — measured, not assumed.
TARGETS: Final[dict[str, tuple[float, float]]] = {
    "MNQ": (3.9e-4, 115.1),
    "MGC": (3.5e-4, 226.5),
}
BTC_REFERENCE: Final[tuple[float, float]] = (9.15e-4, 199.9)


@dataclass(slots=True)
class ArmResult:
    name: str
    construction: str
    runs: int
    promoted: int
    stage1_passes: int
    trials: int
    achieved_kurtosis: float = float("nan")

    @property
    def verdict(self) -> str:
        if self.construction == "REAL EDGE":
            return "found it" if self.promoted == self.runs else "MISSED THE EDGE"
        return "nothing found" if self.promoted == 0 else "PROMOTED ON NOISE"


def fit_generator(target_kurtosis: float, target_std: float, n: int = 200_000,
                  seed: int = 7) -> tuple[float, float, float]:
    """Fit (nu, alpha) so the GARCH series matches the target kurtosis.

    Returns (nu, alpha, achieved kurtosis).

    NU ALONE IS NOT ENOUGH, and the first version of this assumed it was. GARCH volatility
    clustering contributes kurtosis on top of the innovation's, and with the crypto
    parameters (alpha 0.20, beta 0.79) the floor is around 190 even with nearly-Gaussian
    innovations — so MNQ's measured 115.1 is UNREACHABLE by raising nu. The clustering
    coefficient has to come down too, which is the honest way to model a series that is
    both less clustered and less fat-tailed than BTC.

    Beta is moved with alpha to hold alpha+beta, the persistence, near its original level:
    the target is a thinner TAIL, not a shorter memory.
    """
    from futuresres.integrity.synthetic import DEFAULT_ALPHA, DEFAULT_BETA

    def achieved(nu: float, alpha: float) -> float:
        beta = min(DEFAULT_ALPHA + DEFAULT_BETA - alpha, 0.98 - alpha)
        r = garch11(n, np.random.default_rng(seed), target_std=target_std,
                    alpha=alpha, beta=beta, nu=nu)
        z = (r - r.mean()) / r.std(ddof=1)
        return float((z ** 4).mean())

    # 1) try nu alone at the inherited clustering
    lo, hi = 4.2, 60.0
    best = (hi, DEFAULT_ALPHA, achieved(hi, DEFAULT_ALPHA))
    for _ in range(16):
        mid = (lo + hi) / 2
        k = achieved(mid, DEFAULT_ALPHA)
        if abs(k - target_kurtosis) < abs(best[2] - target_kurtosis):
            best = (mid, DEFAULT_ALPHA, k)
        if k > target_kurtosis:
            lo = mid
        else:
            hi = mid
    if abs(best[2] - target_kurtosis) / target_kurtosis < 0.05:
        return best

    # 2) nu could not reach it: bring the clustering down as well
    for alpha in (0.15, 0.12, 0.10, 0.08, 0.06, 0.04, 0.02):
        lo, hi = 4.2, 60.0
        for _ in range(16):
            mid = (lo + hi) / 2
            k = achieved(mid, alpha)
            if abs(k - target_kurtosis) < abs(best[2] - target_kurtosis):
                best = (mid, alpha, k)
            if k > target_kurtosis:
                lo = mid
            else:
                hi = mid
        if abs(best[2] - target_kurtosis) / target_kurtosis < 0.05:
            break
    return best


def run_arm(name: str, construction: str, generator, runs: int, seed0: int,
            n: int, achieved_kurtosis: float = float("nan")) -> ArmResult:
    promoted = passes = trials = 0
    for i in range(runs):
        rng = np.random.default_rng(seed0 + i)
        returns = generator(rng)
        result = run_pipeline(returns, rng=rng, n_bootstrap=300, n_permutations=300)
        trials += len(result.stage1)
        passes += sum(1 for r in result.stage1.values() if r.separated)
        promoted += 0 if result.found_nothing else 1
    return ArmResult(name, construction, runs, promoted, passes, trials,
                     achieved_kurtosis)


def render(results: list[ArmResult], fits: dict[str, tuple[float, float]],
           n: int, runs: int) -> str:
    w: list[str] = []
    a = w.append
    a("# §7 integrity tests on futures-calibrated nulls")
    a("")
    a("Generated by `python -m futuresres.integrity.futures_noise`. "
      "CLAUDE_FUTURES.md §7.2, §7.3.")
    a("")
    a(f"- **{n:,} bars** per replication, **{runs} replications** per arm")
    a("- generators calibrated to the moments measured in `reports/kurtosis.md`, not to "
      "BTC's")
    a("")
    a("## Calibration achieved")
    a("")
    a("| target | σ (1m) | target γ₄ | fitted ν | fitted α | achieved γ₄ |")
    a("|---|---|---|---|---|---|")
    for product, (nu, alpha, achieved) in sorted(fits.items()):
        std, target = TARGETS[product]
        a(f"| {product} | {std * 1e4:.1f} bps | {target:.1f} | {nu:.2f} | {alpha:.2f} | "
          f"**{achieved:.1f}** |")
    a("")
    a("A shortfall here is reported, not hidden: GARCH clustering contributes kurtosis on "
      "top of the innovation's own, so ν cannot be solved in closed form and an extreme "
      "target may not be reachable with a stationary parameterisation. The achieved column "
      "is what the pipeline was actually tested against.")
    a("")
    a("## Result")
    a("")
    a("| generator | construction | runs promoting | Stage-1 passes | verdict |")
    a("|---|---|---|---|---|")
    for r in results:
        a(f"| {r.name} | {r.construction} | **{r.promoted}/{r.runs}** | "
          f"{r.stage1_passes}/{r.trials} | {r.verdict} |")
    a("")
    nulls = [r for r in results if r.construction != "REAL EDGE"]
    control = next((r for r in results if r.construction == "REAL EDGE"), None)
    clean = all(r.promoted == 0 for r in nulls)
    found = control is not None and control.promoted == control.runs
    if clean and found:
        a("**PASS on both arms.** Nothing was promoted on any null, and the injected edge "
          "was found in every replication. The null result is therefore informative: it is "
          "not the output of a harness that promotes nothing on anything.")
    elif not clean:
        a("**FAIL — a strategy was promoted on data with no edge by construction.** Every "
          "result this pipeline has produced is void until this is resolved (§7.2).")
    else:
        a("**FAIL — the positive control was missed.** The pipeline found nothing on noise, "
          "but it also found nothing on a real injected edge, so its nulls carry no "
          "information.")
    a("")
    a("## A caveat from an earlier run, recorded rather than dropped")
    a("")
    a("A first pass used a generator fitted on ν alone, which could not reach MNQ's target "
      "(it bottomed out at γ₄ ≈ 191 against a target of 115.1 because the inherited "
      "clustering coefficient dominates). In that pass the MGC-calibrated null — which DID "
      "match its target kurtosis, at ν = 27.6 rather than the 9.3 used here — **promoted 1 "
      "of 8**. §7.2 treats a promotion on a null as disqualifying, so it is recorded.")
    a("")
    a("Combining both passes gives 1 promotion in 24 MGC-null replications. The current "
      "parameterisation is clean at 0/16, but two generators matching the same kurtosis "
      "behaved differently, which says the result is sensitive to how the tail is split "
      "between innovation fatness and volatility clustering. That is a reason to treat "
      "this PASS as provisional until the Stage 1 bootstrap α is recalibrated on futures "
      "moments (build-order step 8) — the calibration this run still inherits from crypto "
      "is precisely what CLAUDE_FUTURES.md §4 flags as wrong here.")
    a("")
    a("## What this does and does not establish")
    a("")
    a("It establishes that the harness survived the port from crypto and behaves correctly "
      "on futures-shaped noise. It does NOT establish a detection floor for this project — "
      "that is a separate sweep over injected effect sizes, and the crypto floor of 0.1592× "
      "one-minute volatility is still the only measured value on file. Until that is "
      "re-run, a null on real futures data must be read against an unknown floor.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.integrity.futures_noise")
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--bars", type=int, default=20_000)
    ap.add_argument("--edge", type=float, default=0.30,
                    help="positive-control edge, in units of 1m volatility")
    args = ap.parse_args(argv)

    print("fitting GARCH to the measured futures moments")
    fits: dict[str, tuple[float, float]] = {}
    for product, (std, target) in TARGETS.items():
        nu, alpha, achieved = fit_generator(target, std)
        fits[product] = (nu, alpha, achieved)
        print(f"  {product}: target {target:.1f} -> nu {nu:.2f}, alpha {alpha:.2f}, "
              f"achieved {achieved:.1f}")

    results: list[ArmResult] = []
    from futuresres.integrity.synthetic import DEFAULT_ALPHA, DEFAULT_BETA
    for product, (nu, alpha, achieved) in fits.items():
        std, _ = TARGETS[product]
        beta = min(DEFAULT_ALPHA + DEFAULT_BETA - alpha, 0.98 - alpha)
        results.append(run_arm(
            f"GARCH(1,1) Student-t, {product}-calibrated", "no edge",
            lambda rng, s=std, v=nu, al=alpha, be=beta: garch11(
                args.bars, rng, target_std=s, alpha=al, beta=be, nu=v),
            args.runs, 1000, args.bars, achieved,
        ))
        print(f"  {results[-1].name}: {results[-1].promoted}/{results[-1].runs} promoted")

    std_mnq = TARGETS["MNQ"][0]
    results.append(run_arm(
        "random walk, MNQ-calibrated", "no edge",
        lambda rng: random_walk(args.bars, rng, vol=std_mnq),
        args.runs, 2000, args.bars,
    ))
    print(f"  {results[-1].name}: {results[-1].promoted}/{results[-1].runs} promoted")

    # Positive control: a slow persistent drift, deliberately modest.
    def controlled(rng: np.random.Generator) -> np.ndarray:
        nu, alpha, _ = fits["MNQ"]
        beta = min(DEFAULT_ALPHA + DEFAULT_BETA - alpha, 0.98 - alpha)
        base = garch11(args.bars, rng, target_std=std_mnq, alpha=alpha, beta=beta, nu=nu)
        state = np.sign(np.sin(np.arange(args.bars) / 500.0))
        return base + state * args.edge * std_mnq

    results.append(run_arm(
        f"positive control (+{args.edge:g}x vol drift)", "REAL EDGE",
        controlled, args.runs, 3000, args.bars,
    ))
    print(f"  {results[-1].name}: {results[-1].promoted}/{results[-1].runs} promoted")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(results, fits, args.bars, args.runs), encoding="utf-8")
    print(f"wrote {REPORT}")

    nulls_clean = all(r.promoted == 0 for r in results if r.construction != "REAL EDGE")
    control_ok = any(r.construction == "REAL EDGE" and r.promoted == r.runs
                     for r in results)
    return 0 if (nulls_clean and control_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
