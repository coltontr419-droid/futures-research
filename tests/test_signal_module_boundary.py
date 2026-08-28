"""Structural guard: signal modules may not build their own return series.

WHY THIS EXISTS. On 2026-08-27 a drift bias was found in Stage 1. It was not a bug in the
statistic itself — `evaluate_signal` is correct for what it claims, a constant-exposure
signal against the same series' unconditional mean. The bug was that four call sites each
built a long/short return series INLINE, orienting the events and filling every other bar
LONG, and then handed that to a comparison whose unconditional side was therefore a
long-only baseline. The gap between the two exposures is the asset's drift, charged to the
signal. Measured false-positive rate on a drifting null: 0.180 against a nominal 0.05.

Fixing the four call sites does not stop a fifth from being written. The defect was easy to
introduce precisely because building the series looks like ordinary signal work — six lines
of numpy, no obvious boundary crossed. So the boundary is made explicit and tested:

    A signal module produces (signal, direction). It does NOT produce returns.
    Turning prices into a scored series happens in exactly one place: stage1.py.

`evaluate_signed_signal` takes `(direction, log_price)` and derives the series itself, so a
module routed through it has no opportunity to orient anything. A module that wants to
misbehave now has to manufacture a fake price path, which is a far louder thing to do than
multiplying by an orientation array.

WHAT IS ALLOWED. Computing returns as a FEATURE is fine and unavoidable — S09's realized
volatility is a standard deviation of one-minute returns, S01 compares two closes. What is
banned is holding the API that scores a return series: `forward_returns`, `rotation_null`,
`signed_rotation_null`, and `evaluate_signal`. Without those, a constructed series has
nowhere to go.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SIGNALS: Final[Path] = ROOT / "src" / "futuresres" / "signals"
PACKAGE: Final[Path] = ROOT / "src" / "futuresres"

#: The scoring API. A module holding any of these can feed it a series it built itself.
SCORING_API: Final[frozenset[str]] = frozenset({
    "forward_returns", "rotation_null", "signed_rotation_null", "evaluate_signal",
})

#: stage1.py defines them; staged.py is the shared runner and is allowed the Result type
#: only. Everything else in signals/ must go through `evaluate_signed_signal`.
DEFINING_MODULE: Final[str] = "stage1.py"

#: Justified exceptions. Each entry must say WHY, and the reason must be checkable by
#: reading the module — not "legacy" or "needed for now".
#:
#: search.py — its candidates are boolean long-only masks (`crossover_signals` returns a
#:   T×N BOOLEAN matrix) scored against RAW returns. Exposure is constant on both sides of
#:   the comparison, which is exactly the contract `evaluate_signal` documents. There is no
#:   direction vector anywhere in the module, so the defect is not expressible there.
ALLOWED: Final[dict[str, frozenset[str]]] = {
    "search.py": frozenset({"evaluate_signal"}),
}

#: Modules that run a hypothesis end to end. Each must route through the shared evaluator.
RUNNER_ENTRYPOINTS: Final[frozenset[str]] = frozenset({
    "evaluate_signed_signal", "evaluate_cell", "run_staged",
})

#: Vocabulary that only a module producing a Stage 1 VERDICT has any use for. Referencing
#: any of it means the module compares against a baseline, which is where the drift bias
#: lives — per-event means carry no baseline and cannot express the defect.
VERDICT_VOCABULARY: Final[frozenset[str]] = frozenset({
    "Stage1Result", "separated", "p_value", "mean_shift", "ci_low", "ci_high",
})

#: Per-hypothesis modules that report effect sizes only and reach no verdict. Each is
#: asserted below to use none of VERDICT_VOCABULARY, so the exemption is earned by what the
#: module actually does rather than asserted by being listed here.
#:
#: Empty at the start of this project. The crypto repo had one entry (s01_holds.py, a
#: hold-scaling diagnostic); nothing here has earned the exemption yet, and it must be
#: earned by what a module does rather than by being listed.
DIAGNOSTIC_MODULES: Final[frozenset[str]] = frozenset()


def _identifiers(tree: ast.AST) -> set[str]:
    """Every bare name and attribute tail referenced in the module."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.asname or node.name.split(".")[-1])
    return out


def _modules(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if p.name != "__init__.py")


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.integrity
@pytest.mark.parametrize("path", _modules(SIGNALS), ids=lambda p: p.name)
def test_signal_modules_do_not_hold_the_scoring_api(path: Path) -> None:
    """Only stage1.py may name the functions that score a return series."""
    if path.name == DEFINING_MODULE:
        return
    used = _identifiers(_parse(path)) & SCORING_API
    permitted = ALLOWED.get(path.name, frozenset())
    forbidden = used - permitted
    assert not forbidden, (
        f"{path.name} references {sorted(forbidden)}, which scores a caller-supplied "
        f"return series. A signal module produces (signal, direction) and hands them to "
        f"evaluate_signed_signal, which derives the series itself — that is what stops a "
        f"long/short signal being scored against a long-only baseline. If this use is "
        f"genuinely constant-exposure, add it to ALLOWED with a reason a reader can check."
    )


@pytest.mark.integrity
def test_the_allowlist_is_not_a_place_to_hide_a_signed_signal() -> None:
    """An allowlisted module must have no direction vector at all.

    The exemption is for constant-exposure signals. A module carrying a `direction` is by
    definition not one, so the presence of the name is enough to void the exemption —
    without this, the allowlist becomes the hole the guard was built to close.
    """
    for name in ALLOWED:
        path = SIGNALS / name
        assert path.exists(), f"ALLOWED names {name}, which does not exist"
        identifiers = _identifiers(_parse(path))
        assert "direction" not in identifiers, (
            f"{name} is allowlisted as constant-exposure but defines or uses "
            f"`direction` — it is a signed signal and must use evaluate_signed_signal."
        )


def _hypothesis_modules() -> list[Path]:
    """Per-hypothesis runners: f01.py, f02.py, ... (s01.py in the crypto lineage)."""
    return [p for p in _modules(SIGNALS)
            if len(p.stem) >= 3 and p.stem[0] in "fs" and p.stem[1:3].isdigit()]


@pytest.mark.integrity
def test_the_runner_guard_is_wired_even_before_any_runner_exists() -> None:
    """An empty parametrize is a silent skip, and a silent skip stays green forever.

    This project starts with no hypothesis modules, so the guard below has nothing to check
    yet. That is a fact worth asserting rather than a reason to let the check disappear:
    when f01.py lands, the parametrized test must actually run against it.
    """
    found = _hypothesis_modules()
    assert found == [] or all(p.exists() for p in found)


@pytest.mark.integrity
@pytest.mark.parametrize(
    "path", _hypothesis_modules() or [None], ids=lambda p: p.name if p else "none-yet",
)
def test_hypothesis_runners_route_through_the_shared_evaluator(path: Path | None) -> None:
    if path is None:
        pytest.skip("no hypothesis runners registered yet — guard is wired, see above")
    """A module that reaches a Stage 1 verdict must do it by the one supported path.

    Membership is decided by what the module references, not by its filename: anything
    using the verdict vocabulary is comparing against a baseline, and that is where the
    drift bias lives. A module reporting per-event effect sizes carries no baseline and is
    exempt — but it must then be declared as a diagnostic, checked below.
    """
    identifiers = _identifiers(_parse(path))

    # Routing correctly is sufficient on its own. s01.py and s09.py delegate entirely to
    # run_staged and never name a Stage1Result — that is the intended shape, not a gap.
    if identifiers & RUNNER_ENTRYPOINTS:
        return

    assert not identifiers & VERDICT_VOCABULARY, (
        f"{path.name} reaches a Stage 1 verdict — it references "
        f"{sorted(identifiers & VERDICT_VOCABULARY)} — but routes through none of "
        f"{sorted(RUNNER_ENTRYPOINTS)}. It is scoring by hand, which is exactly how the "
        f"drift bias came to exist in four places at once."
    )
    assert path.name in DIAGNOSTIC_MODULES, (
        f"{path.name} looks like a hypothesis module but neither routes through the "
        f"shared evaluator nor reaches a verdict, and is not declared in "
        f"DIAGNOSTIC_MODULES. Either it should be scoring and is not, or it is a "
        f"diagnostic and should say so."
    )


@pytest.mark.integrity
def test_declared_diagnostics_really_reach_no_verdict() -> None:
    """The diagnostic exemption must be earned by the code, not by the declaration."""
    for name in DIAGNOSTIC_MODULES:
        path = SIGNALS / name
        assert path.exists(), f"DIAGNOSTIC_MODULES names {name}, which does not exist"
        used = _identifiers(_parse(path)) & VERDICT_VOCABULARY
        assert not used, (
            f"{name} is declared a diagnostic but references {sorted(used)}. It reaches a "
            f"verdict after all, and must route through the shared evaluator."
        )


@pytest.mark.integrity
@pytest.mark.parametrize("path", _modules(PACKAGE), ids=lambda p: p.name)
def test_the_long_fill_idiom_appears_nowhere(path: Path) -> None:
    """Ban the exact fingerprint of the defect: np.where(x != 0, x, <constant>).

    This is the line that made every non-event bar long:

        flow = np.where(oriented != 0, oriented, 1.0) * r1

    The name-based guard above is the real boundary; this one catches the specific
    construction wherever it might reappear, including outside signals/. It is narrow on
    purpose — a comparison against zero with a constant fallback is a distinctive shape,
    and banning anything broader would flag legitimate numpy.
    """
    for node in ast.walk(_parse(path)):
        if not (isinstance(node, ast.Call) and len(node.args) == 3):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "where"):
            continue
        test, _, fallback = node.args
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], (ast.NotEq, ast.Eq)):
            continue
        comparator = test.comparators[0]
        zero = isinstance(comparator, ast.Constant) and comparator.value == 0
        const_fallback = isinstance(fallback, ast.Constant) and isinstance(
            fallback.value, (int, float)
        )
        assert not (zero and const_fallback), (
            f"{path.name}:{node.lineno} builds a series with a constant fill over a "
            f"!= 0 mask. That is the orientation long-fill that biased Stage 1 by the "
            f"asset's drift. Pass (signal, direction) to evaluate_signed_signal instead."
        )
