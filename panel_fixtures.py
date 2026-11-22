# Source inputs for the shared-panel examples. This module also checks their V1 projection.
import argparse
import tempfile
from pathlib import Path

from evidence.acceptance import accept_panel, accept_station
from evidence.freeze import freeze_panel, freeze_station
from records.identity import StationKey
from records.intake import accept_revision
from records.readings import ActionRow, RevisionDraft, WitnessRow
from records.storage import RevisionStore
from reports.publish import issue_panel, issue_report
from reports.retrieve import read_panel, read_report
from reports.storage import ReportStore
from review.commands import CommandCatalog


CATALOG = CommandCatalog("panel-retest", ("p", "q", "r", "s", "t"))
ALPHA = StationKey(CATALOG.job, "alpha")
BETA = StationKey(CATALOG.job, "beta")


def _route(rows):
    actions = []
    witnesses = []
    for row_id, source, target, command, witnessed in rows:
        kind = "local" if command is None else "public"
        actions.append(ActionRow(
            row_id, f"private-{source}", f"private-{target}", kind,
            "private-preparation" if command is None else command, f"reading-{row_id}",
        ))
        if witnessed:
            witnesses.append(WitnessRow(f"witness-{row_id}", row_id, "qualified at source"))
    return RevisionDraft("private-opening", tuple(actions), tuple(witnesses))


ALPHA_ROUTE = _route((
    ("a-p0", "opening", "before-0", "p", False),
    ("a-p1", "opening", "before-1", "p", False),
    ("a-q0", "before-0", "after-0", "q", False),
    ("a-q1", "before-1", "after-1", "q", False),
    ("a-r0", "after-0", "done", "r", True),
    ("a-s0", "after-0", "done", "s", True),
    ("a-t1", "after-1", "done", "t", True),
))
BETA_ROUTE = _route((
    ("b-p0", "opening", "before-0", "p", False),
    ("b-p1", "opening", "before-1", "p", False),
    ("b-q0", "before-0", "after-0", "q", False),
    ("b-q1", "before-1", "after-1", "q", False),
    ("b-r1", "after-1", "done", "r", True),
    ("b-s0", "after-0", "done", "s", True),
    ("b-t0", "after-0", "done", "t", True),
    ("b-t1", "after-1", "done", "t", True),
))
WITNESS_LEFT = _route((
    ("a-local", "opening", "opening", None, True),
    ("a-p", "opening", "done", "p", False),
))
WITNESS_RIGHT = _route((("b-p", "opening", "done", "p", True),))


def stage_sources(alpha_path, beta_path, freeze):
    pieces = {}
    with RevisionStore(alpha_path) as alpha:
        alpha.initialize((CATALOG,))
        original = accept_revision(alpha, ALPHA, ALPHA_ROUTE)
        pieces["alpha"] = freeze(alpha, original, ("a-p1", "a-q1"))
        flat = accept_revision(alpha, ALPHA, ALPHA_ROUTE, parent=original)
        pieces["alpha_flat"] = freeze(alpha, flat, ("a-p1",))
        local = accept_revision(alpha, ALPHA, WITNESS_LEFT)
        pieces["witness_left"] = freeze(alpha, local, ())
    with RevisionStore(beta_path) as beta:
        beta.initialize((CATALOG,))
        original = accept_revision(beta, BETA, BETA_ROUTE)
        pieces["beta"] = freeze(beta, original, ("b-p1",))
        reversed_lamp = accept_revision(beta, BETA, BETA_ROUTE, parent=original)
        pieces["beta_reversed"] = freeze(beta, reversed_lamp, ("b-p0",))
        witnessed = accept_revision(beta, BETA, WITNESS_RIGHT)
        pieces["witness_right"] = freeze(beta, witnessed, ())
    return pieces


def _freeze_v1(store, key, lamps):
    return freeze_station(store, key)


def check_v1(alpha_path, beta_path, report_path):
    raw = stage_sources(alpha_path, beta_path, _freeze_v1)
    left = accept_station(raw["alpha"], CATALOG.job, ALPHA.station)
    right = accept_station(raw["beta"], CATALOG.job, BETA.station)
    corrected = accept_station(raw["beta_reversed"], CATALOG.job, BETA.station)
    if right.identity == corrected.identity or right.body != corrected.body:
        raise RuntimeError("V1 must see distinct beta revisions with identical route bodies")
    with ReportStore(report_path) as reports:
        reports.initialize()
        old = issue_report(reports, left, right, CATALOG.commands)
        new = issue_report(reports, left, corrected, CATALOG.commands)
        if old.first_commands or new.first_commands:
            raise RuntimeError("V1 must find no repeatable first command on finite routes")
        if read_report(reports, old.number) != old or read_report(reports, new.number) != new:
            raise RuntimeError("V1 did not preserve the original parent order and reports")
    if report_path != ":memory:":
        with ReportStore(report_path) as reopened:
            if read_report(reopened, old.number) != old or read_report(reopened, new.number) != new:
                raise RuntimeError("V1 reports changed on reopen")
    print(f"V1 beta revisions {right.identity.revision}, {corrected.identity.revision}: equal route bodies")
    print(f"V1 offline reports {old.number}, {new.number}: [], []")


def _final_steps(strategy):
    found = {}

    def walk(node, lamps):
        for lamp, child in node["next"].items():
            history = lamps + (int(lamp),)
            if "stop" in child:
                found[history] = node["command"]
            else:
                walk(child, history)

    walk(strategy, ())
    return found


def check_v2(alpha_path, beta_path, report_path):
    """Exercise the V2 panel path end to end and return the staged source texts."""
    raw = stage_sources(alpha_path, beta_path, freeze_panel)
    left = accept_panel(raw["alpha"], CATALOG.job, ALPHA.station)
    right = accept_panel(raw["beta"], CATALOG.job, BETA.station)
    corrected = accept_panel(raw["beta_reversed"], CATALOG.job, BETA.station)
    with ReportStore(report_path) as reports:
        reports.initialize()
        two = issue_panel(reports, left, right, CATALOG.commands, 2)
        old = issue_panel(reports, left, right, CATALOG.commands, 3)
        new = issue_panel(reports, left, corrected, CATALOG.commands, 3)
        if two.status != "impossible" or two.strategy is not None:
            raise RuntimeError("V2 must not guarantee a two-step panel run")
        old_steps = _final_steps(old.strategy)
        new_steps = _final_steps(new.strategy)
        expected_old = {(0, 0, 0): "s", (1, 0, 0): "r", (1, 1, 0): "t"}
        expected_new = {(0, 0, 0): "r", (1, 0, 0): "s", (1, 1, 0): "t"}
        if old_steps != expected_old or new_steps != expected_new:
            raise RuntimeError(
                f"V2 final steps {old_steps!r} / {new_steps!r} do not match the lamp correction"
            )
        old_again = read_panel(reports, old.number)
        new_again = read_panel(reports, new.number)
        if old_again != old or new_again != new:
            raise RuntimeError("V2 reports changed after reopening")
    print(f"V2 final steps original {sorted(old_steps.items())}")
    print(f"V2 final steps corrected {sorted(new_steps.items())}")
    print(f"V2 reports {old.number} impossible-at-2 / {new.number} guaranteed-at-3")
    return raw


def main():
    parser = argparse.ArgumentParser(description="Stage panel inputs and verify their V1/V2 behavior")
    parser.add_argument("--memory", action="store_true", help="use independent in-memory databases")
    args = parser.parse_args()
    if args.memory:
        check_v1(":memory:", ":memory:", ":memory:")
        return
    with tempfile.TemporaryDirectory(prefix="panel-fixtures-") as folder:
        root = Path(folder)
        check_v1(root / "alpha.sqlite3", root / "beta.sqlite3", root / "reports.sqlite3")
        check_v2(
            root / "alpha.sqlite3", root / "beta.sqlite3", root / "panel-reports.sqlite3"
        )


if __name__ == "__main__":
    main()
