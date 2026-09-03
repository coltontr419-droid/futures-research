"""No Stage 1 may run without logging. CLAUDE_FUTURES.md §6.

The trial log was ported from the crypto repo with passing tests and no runner ever called
it. Three hypotheses ran and 342 trials were spent before that was noticed, because N was
being reconstructed by counting rows in output files. These tests exist so the same thing
cannot happen twice: one checks the machinery works, the others check it is actually wired
into every runner that exists — including runners nobody has written yet.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Final

import pytest

from futuresres.signals.logged_run import (
    PROVENANCE,
    Recorder,
    UnloggedRun,
    stage1_run,
)
from futuresres.stats.trials import TrialLog

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SIGNALS: Final[Path] = ROOT / "src" / "futuresres" / "signals"

#: Every runner module: f01.py, f02.py, ... Discovered, not listed, so a new runner is
#: covered the moment it is created rather than when someone remembers to add it here.
RUNNERS: Final[list[Path]] = sorted(
    p for p in SIGNALS.glob("f[0-9][0-9].py") if p.is_file()
)


def test_there_are_runners_to_check() -> None:
    """Guards the guard: a glob that matches nothing would make every test below vacuous."""
    assert RUNNERS, f"no runner modules found under {SIGNALS}"


@pytest.mark.parametrize("path", RUNNERS, ids=lambda p: p.stem)
def test_every_runner_wraps_main_in_stage1_run(path: Path) -> None:
    """A runner's main() must go through the enforcing context manager.

    Checked structurally rather than by running each one, because running them takes
    minutes and the point is to catch a runner that was written without the wiring — which
    is a source-level fact.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    main = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    assert main is not None, f"{path.name} has no main()"

    withs = [n for n in ast.walk(main) if isinstance(n, ast.With)]
    calls = [item.context_expr for w in withs for item in w.items
             if isinstance(item.context_expr, ast.Call)]
    names = {c.func.id for c in calls if isinstance(c.func, ast.Name)}
    assert "stage1_run" in names, (
        f"{path.name}: main() does not run inside `with stage1_run(...)`. Every Stage 1 "
        f"run spends trials against the catalog's shared multiple-testing budget, and an "
        f"unlogged run makes N unverifiable for every hypothesis, not just this one."
    )


@pytest.mark.parametrize("path", RUNNERS, ids=lambda p: p.stem)
def test_every_runner_records_inside_the_block(path: Path) -> None:
    """Wrapping main() is not enough — something must actually be recorded."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    main = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    recorded = [
        n for n in ast.walk(main)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "record"
    ]
    assert recorded, (
        f"{path.name}: main() opens stage1_run but never calls recorder.record(...). "
        f"The context manager would raise at exit; this test says so at review time."
    )


@pytest.mark.integrity
def test_a_run_that_records_nothing_raises(tmp_path: Path) -> None:
    """The whole point: a silent no-op run must fail loudly."""
    log = tmp_path / "trials.jsonl"
    with pytest.raises(UnloggedRun, match="without appending"):
        with stage1_run("F99", path=log):
            pass  # computed cells, forgot to record them
    assert not log.exists() or len(TrialLog(log)) == 0


@pytest.mark.integrity
def test_a_run_that_records_passes_and_chains(tmp_path: Path) -> None:
    log = tmp_path / "trials.jsonl"
    cells = [
        {"product": "MGC", "slot": 3, "hold": 60, "events": 3800,
         "sharpe": 0.02, "p_value": 0.4, "blocked": False},
        {"product": "MNQ", "slot": 3, "hold": 60, "events": 4100,
         "sharpe": -0.01, "p_value": 0.7, "blocked": True},
    ]
    with stage1_run("F99", path=log) as rec:
        rec.record(cells)
    assert rec.written == 2
    tl = TrialLog(log)
    assert len(tl) == 2
    assert tl.verify_chain().ok
    trials = tl.read_all()
    assert {t.symbol for t in trials} == {"MGC", "MNQ"}
    assert all("provenance=native" in t.note for t in trials)
    # a blocked cell must say so in the record, not only in a report
    blocked = next(t for t in trials if t.symbol == "MNQ")
    assert "UNINFORMATIVE" in blocked.note


@pytest.mark.integrity
def test_an_exception_inside_the_block_is_not_masked(tmp_path: Path) -> None:
    """A crashed run has its own story; UnloggedRun must not bury it."""
    log = tmp_path / "trials.jsonl"
    with pytest.raises(ZeroDivisionError):
        with stage1_run("F99", path=log):
            1 / 0


@pytest.mark.integrity
def test_provenance_must_be_declared_not_invented(tmp_path: Path) -> None:
    log = TrialLog(tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="provenance"):
        Recorder("F99", log, "probably-fine", ("2010-01-01", "2026-08-28"))
    assert PROVENANCE == {"native", "reconstructed"}


@pytest.mark.integrity
def test_the_real_log_exists_and_verifies() -> None:
    """The repo's own log must be present and internally consistent."""
    path = ROOT / "trials.jsonl"
    assert path.exists(), (
        "trials.jsonl is missing. Every completed run must be in it — backfilled and "
        "marked reconstructed if it predates the wiring."
    )
    log = TrialLog(path)
    result = log.verify_chain()
    assert result.ok, f"trial log chain is broken: {result}"
    assert len(log) > 0


@pytest.mark.integrity
def test_reconstructed_trials_are_marked_as_such() -> None:
    """A backfilled trial must never be indistinguishable from a natively logged one."""
    log = TrialLog(ROOT / "trials.jsonl")
    for trial in log.read_all():
        assert "provenance=" in trial.note, (
            f"{trial.trial_id} has no provenance. A reader must be able to tell a "
            f"backfilled record from one written by the run that produced it, without "
            f"consulting git history."
        )
        assert any(p in trial.note for p in PROVENANCE)


@pytest.mark.integrity
def test_every_run_with_a_cell_file_is_represented_in_the_log() -> None:
    """The gap that started this: results on disk with no corresponding trials."""
    log = TrialLog(ROOT / "trials.jsonl")
    logged = {}
    for trial in log.read_all():
        logged[trial.hypothesis_id] = logged.get(trial.hypothesis_id, 0) + 1
    for path in sorted((ROOT / "reports").glob("f*_cells.json")):
        hid = path.stem.split("_")[0].upper()
        n_cells = len(json.loads(path.read_text(encoding="utf-8")))
        assert logged.get(hid, 0) >= n_cells, (
            f"{hid}: {n_cells} cells on disk but only {logged.get(hid, 0)} trials logged. "
            f"Results exist that N does not know about."
        )


@pytest.mark.integrity
def test_every_documented_entry_point_actually_runs() -> None:
    """A `python -m ...` string in the source must name a module with a main().

    Found the hard way: the detectability gate told anyone hitting a FIRING RATE UNMEASURED
    row to run `python -m futuresres.reporting.measured_rates`, and that module had no
    main() at all. The command silently did nothing, so the gate's own remediation
    instruction was a no-op and the file it depends on could only be produced by an ad-hoc
    script that lived outside the repo.
    """
    import importlib
    import re

    src = ROOT / "src" / "futuresres"
    referenced: set[str] = set()
    for path in src.rglob("*.py"):
        for m in re.finditer(r"python -m (futuresres[\w.]+)",
                             path.read_text(encoding="utf-8")):
            referenced.add(m.group(1))
    assert referenced, "no documented entry points found - the regex is wrong"

    missing = []
    for name in sorted(referenced):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(f"{name} (cannot import)")
            continue
        if not callable(getattr(mod, "main", None)):
            missing.append(f"{name} (no main())")
    assert not missing, (
        "documented commands that do nothing: " + ", ".join(missing)
        + ". A remediation instruction that is a no-op is worse than none."
    )
