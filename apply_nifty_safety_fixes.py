#!/usr/bin/env python3
"""Conservative root-folder hotfix for Yash19815/openalgo at 5db10c9.

Usage (from repository root):
    python apply_nifty_safety_fixes.py           # inspect diff only
    python apply_nifty_safety_fixes.py --apply   # backup, apply verified replacements

No external dependencies. Refuses unexpected source text and does not edit partial files.
Review all diffs and run tests before committing. Live mode remains unchanged.
"""
from __future__ import annotations

import argparse
import difflib
from datetime import datetime
from pathlib import Path
import shutil
import sys

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "services/nifty_algo/config.py": [
        (
            'profit_lock_activation_net: Decimal = Field(default=Decimal("400"), ge=0, le=Decimal("400"))',
            'profit_lock_activation_net: Decimal = Field(\n'
            '        default=Decimal("400"), ge=Decimal("400"), le=Decimal("400")\n'
            '    )',
        ),
        (
            'profit_lock_floor_net: Decimal = Field(default=Decimal("350"), ge=0)',
            'profit_lock_floor_net: Decimal = Field(\n'
            '        default=Decimal("350"), ge=Decimal("350"), lt=Decimal("400")\n'
            '    )',
        ),
        (
            'early_booking_min_net: Decimal = Field(default=Decimal("300"), ge=0)',
            'early_booking_min_net: Decimal = Field(default=Decimal("300"), ge=Decimal("300"))',
        ),
        (
            '    _clamp("profit_lock_activation_net", Decimal("0"), Decimal("400"))\n'
            '    _clamp("profit_lock_floor_net", Decimal("0"))',
            '    # Existing v1/v2/v3 settings must migrate to the non-weakening guardrails.\n'
            '    changed["profit_lock_activation_net"] = "400"\n'
            '    _clamp("profit_lock_floor_net", Decimal("350"), Decimal("399.99"))\n'
            '    _clamp("early_booking_min_net", Decimal("300"))',
        ),
    ],
    "database/nifty_algo_db.py": [
        (
            '            if row.segment != "NFO" or any(item.get("ambiguous") for item in row.entries):\n'
            '                raise ValueError("Calendar has an unconfirmed segment or ambiguous entries")',
            '            if row.segment != "NFO" or any(item.get("ambiguous") for item in row.entries):\n'
            '                raise ValueError("Calendar has an unconfirmed segment or ambiguous entries")\n'
            '            # An empty/unparsed calendar would treat every ordinary weekday as tradable.\n'
            '            if not row.entries or not all(\n'
            '                isinstance(item, dict) and item.get("date")\n'
            '                for item in row.entries\n'
            '            ):\n'
            '                raise ValueError("Calendar must contain reviewed dated NFO holidays")',
        ),
    ],
    "services/nifty_algo/calendar.py": [
        (
            '                return {"status": "TRADING", "window": None}',
            '                return {"status": "SESSION_WINDOW_UNAVAILABLE", "window": None}',
        ),
    ],
    "test/test_nifty_algo_phase2.py": [
        (
            '        profit_lock_floor_net=D("35"),\n'
            '        profit_lock_activation_net=D("50"),',
            '        profit_lock_floor_net=D("350"),\n'
            '        profit_lock_activation_net=D("400"),',
        ),
    ],
    "test/test_nifty_algo_gap_p1.py": [
        (
            '    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("349.99")})\n'
            '    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("360")})',
            '    _bad(profit_lock_floor_net=Decimal("349.99"))\n'
            '    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("350")})\n'
            '    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("360")})\n'
            '    _bad(profit_lock_activation_net=Decimal("399.99"))\n'
            '    _bad(early_booking_min_net=Decimal("299.99"))',
        ),
    ],
    "test/nifty_calendar_helpers.py": [
        (
            '    data = b"date,name\\n"\n'
            '    draft = store.create_calendar_draft(',
            '    # Use a genuine known holiday as the empty-fixture default; never\n'
            '    # approve a blank production calendar just to satisfy unit tests.\n'
            '    entries = list(entries) or [\n'
            '        {"date": f"{year}-01-26", "name": "Republic Day (test fixture)"}\n'
            '    ]\n'
            '    data = ("date,name\\n" + "".join(\n'
            '        f"{entry[\'date\']},{entry.get(\'name\') or \'Test holiday\'}\\n"\n'
            '        for entry in entries\n'
            '    )).encode("utf-8")\n'
            '    draft = store.create_calendar_draft(',
        ),
    ],
    "test/test_nifty_algo_phase1.py": [
        (
            '    data = b"date,name\\n"\n'
            '    draft = store.create_calendar_draft(',
            '    data = f"date,name\\n{year}-01-26,Republic Day (fixture)\\n".encode()\n'
            '    draft = store.create_calendar_draft(',
        ),
        (
            '        entries=[],\n'
            '        issues=[],\n'
            '        data=data,',
            '        entries=[{"date": f"{year}-01-26", "name": "Republic Day (fixture)"}],\n'
            '        issues=[],\n'
            '        data=data,',
        ),
    ],
    "test/test_nifty_algo_calendar.py": [
        (
            '    created = draft(store, "alice", [])\n'
            '    ambiguous = store.update_draft_entries(',
            '    created = draft(store, "alice", [])\n'
            '    with pytest.raises(ValueError, match="reviewed dated NFO holidays"):\n'
            '        approve(store, created)\n'
            '    ambiguous = store.update_draft_entries(',
        ),
        (
            '    second = approve(store, draft(store, "alice", []))',
            '    second = approve(store, draft(store, "alice", [\n'
            '        {"date": "2026-01-26", "name": "Republic Day"}\n'
            '    ]))',
        ),
        (
            'def approved(store, entries=(), *, year=2026):\n'
            '    row = draft(store, "alice", list(entries), year)',
            'def approved(store, entries=(), *, year=2026):\n'
            '    values = list(entries) or [{"date": f"{year}-01-26", "name": "Republic Day"}]\n'
            '    row = draft(store, "alice", values, year)',
        ),
    ],
}


def main() -> int:
    raise SystemExit("RETIRED: historical source patcher; use reviewed Git commits. No files changed.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write files (default dry-run)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="OpenAlgo checkout root")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "services/nifty_algo/config.py").is_file() or not (root / "database/nifty_algo_db.py").is_file():
        print("ERROR: Run from OpenAlgo repository root or use --root PATH", file=sys.stderr)
        return 2

    outputs: dict[Path, tuple[str, str]] = {}
    failures = []
    for rel, replacements in REPLACEMENTS.items():
        target = root / rel
        if not target.is_file():
            failures.append(f"Missing file: {rel}")
            continue
        original = target.read_text(encoding="utf-8")
        updated = original
        for i, (old, new) in enumerate(replacements, start=1):
            occurrences = updated.count(old)
            if occurrences != 1:
                failures.append(f"{rel}: replacement {i}: expected exactly 1 match, got {occurrences}")
            else:
                updated = updated.replace(old, new, 1)
        outputs[target] = (original, updated)
    if failures:
        print("ABORTED: the checkout differs from the audited commit. NO FILES CHANGED.")
        for failure in failures:
            print(" - " + failure)
        return 2

    for target, (original, updated) in outputs.items():
        print("".join(difflib.unified_diff(
            original.splitlines(keepends=True), updated.splitlines(keepends=True),
            fromfile=str(target.relative_to(root)), tofile=str(target.relative_to(root)) + " (patched)")), end="")
    if not args.apply:
        print("\nDRY RUN ONLY. If the diffs are correct, rerun with --apply.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root.parent / (root.name + "_nifty_patch_backups") / timestamp
    written = []
    try:
        for target in outputs:
            relative = target.relative_to(root)
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
        for target, (_, updated) in outputs.items():
            target.write_text(updated, encoding="utf-8", newline="")
            written.append(target)
    except Exception as exc:
        for target in written:
            shutil.copy2(backup_dir / target.relative_to(root), target)
        print(f"ERROR while writing: {exc}; restored written files; backups: {backup_dir}", file=sys.stderr)
        return 1
    print(f"\nApplied {len(outputs)} files. Backups: {backup_dir}")
    print("NEXT: run Python tests, Ruff, and git diff --check; do NOT enable LIVE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
