"""Fault-inject P03's outcome path: a null from a broken sign looks exactly like a real one.

P03 returned +0.079 bps against a pre-registered +0.625 and did not clear. That verdict is
only worth anything if the machinery could have SEEN a clearing effect, so the path is tested
against a known injected reversion rather than trusted. §46's instruction is to look for the
bug when something clears; the mirror risk - a null manufactured by a sign error or an
off-by-one in the hold - needs the same treatment, and nothing else in the suite covers it.
"""

from __future__ import annotations

import numpy as np

from futuresres.signals.p03 import HOLD_BARS, outcomes

N_SESSIONS: int = 200
BARS: int = 78


def _world(inject_bps: float, seed: int = 0):
    """A random walk with a KNOWN reversion pasted in after each firing."""
    sid = np.repeat(np.arange(N_SESSIONS), BARS)
    rng = np.random.default_rng(seed)
    lp = np.cumsum(rng.normal(0.0, 5.0, sid.size))

    fire = np.zeros(sid.size, bool)
    fire[np.arange(10, sid.size - 10, 37)] = True
    fire[np.flatnonzero(np.diff(sid, prepend=-1) != 0)] = False   # never the session's first bar

    if inject_bps:
        for i in np.flatnonzero(fire):
            if i + HOLD_BARS >= lp.size or sid[i + HOLD_BARS] != sid[i]:
                continue
            back = np.sign(lp[i] - lp[i - 1]) * inject_bps
            ramp = np.arange(1, HOLD_BARS + 1) / HOLD_BARS
            lp[i + 1:i + 1 + HOLD_BARS] -= back * ramp
            lp[i + 1 + HOLD_BARS:] -= back

    close = 10_000 * np.exp(lp / 1e4)
    ret = np.abs(np.diff(np.log(close), prepend=np.nan)) * 1e4
    ret[np.diff(sid, prepend=-1) != 0] = np.nan
    return {"close": close, "session": sid, "ret_bps": ret}, np.flatnonzero(fire)


def test_a_known_reversion_is_recovered_with_the_right_sign_and_size() -> None:
    """The decisive one. Fading a move that reverts 4 bps must PAY about 4 bps."""
    w, fire = _world(inject_bps=4.0)
    got = outcomes(w, fire)
    got = got[np.isfinite(got)]
    assert got.size > 300, got.size
    assert 3.0 < got.mean() < 4.5, (
        f"injected +4.0 bps of reversion, recovered {got.mean():+.3f} - the outcome path "
        f"cannot see the effect it was built to measure, so its null means nothing"
    )


def test_the_same_path_returns_nothing_on_a_pure_random_walk() -> None:
    """Otherwise the test above would pass on a path that always returns a constant."""
    w, fire = _world(inject_bps=0.0)
    got = outcomes(w, fire)
    got = got[np.isfinite(got)]
    se = float(got.std() / np.sqrt(got.size))
    assert abs(got.mean()) < 3 * se, f"{got.mean():+.3f} against SE {se:.3f}"


def test_the_hold_never_crosses_a_session_boundary() -> None:
    """A hold that runs into the next session would splice an overnight gap into the result."""
    w, fire = _world(inject_bps=0.0)
    got = outcomes(w, fire)
    kept = fire[np.isfinite(got)]
    sid = w["session"]
    assert (sid[kept + HOLD_BARS] == sid[kept]).all()


def test_the_direction_is_a_fade_not_a_follow() -> None:
    """Sign convention, pinned: a CONTINUING move must lose money for this rule."""
    w, fire = _world(inject_bps=-4.0)      # negative injection = the move extends
    got = outcomes(w, fire)
    got = got[np.isfinite(got)]
    assert got.mean() < -3.0, (
        f"a move that extends must cost the fade rule; got {got.mean():+.3f}"
    )
