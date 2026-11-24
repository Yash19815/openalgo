#!/usr/bin/env python3
"""Optional report-recovery patch for OpenAlgo 5db10c9 (run AFTER safety patch).

Adds a durable, transactional daily scan cursor to find older missing reports
without an unbounded per-minute scan. Rechecks the current/previous month,
blocks scan progress when the approved calendar/session window is unknown,
and rewinds the cursor on calendar amendments.

From OpenAlgo root:
    python apply_nifty_report_recovery.py          # preview only
    python apply_nifty_report_recovery.py --apply  # apply with backups

REVIEW THE DIFF; RUN TESTS AND A DATABASE BACKUP FIRST.
"""
from __future__ import annotations

import argparse
import difflib
from datetime import datetime
from pathlib import Path
import shutil
import sys

NEW_MODEL = '''class NiftyReportScan(Base):
    """Durable position of bounded report-period discovery per user.

    The cursor is an IST ISO date (next unexamined session); it does not
    imply PDF generation or delivery succeeded. Those are separate rows.
    """

    __tablename__ = "nifty_algo_report_scan"
    user_id = Column(String(255), primary_key=True)
    next_day = Column(String(10), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


'''

NEW_METHODS = '''    def report_scan_cursor(self, user_id, since):
        """Create/read durable scan cursor using the established per-user lock."""
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is None:
                row = NiftyReportScan(
                    user_id=user_id, next_day=since.isoformat(), updated_at=datetime.now(UTC)
                )
                db.add(row)
                db.flush()
            return row.next_day

    def advance_report_scan_cursor(self, user_id, expected, next_day):
        """Advance only after all due periods in a bounded scan were reserved."""
        if next_day <= expected:
            return False
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is None or row.next_day != expected:
                return False
            row.next_day = next_day
            row.updated_at = datetime.now(UTC)
            return True

    def rewind_report_scan_cursor(self, user_id, year):
        """Revisit affected session periods after an approved calendar amendment."""
        candidate = f"{int(year):04d}-01-01"
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is not None and row.next_day > candidate:
                row.next_day = candidate
                row.updated_at = datetime.now(UTC)

'''

OLD_DUE = '''    def due_periods(self, now):
        since = self._since()
        if since is None:
            return []
        today = now.astimezone(IST).date()
        first = max(since, today - timedelta(days=LOOKBACK_DAYS))
        due = []
        day = first
        while day <= today:
            if self._session(day)["status"] == "TRADING" and now >= self._closes_at(day):
                due.append(("DAILY", day.isoformat()))
            day += timedelta(days=1)
        for month in sorted({first.strftime("%Y-%m"), today.strftime("%Y-%m")}):
            # An unapproved calendar leaves the month's last session undecidable.
            if self.store.approved_calendar_version(self.user_id, int(month[:4])) is None:
                continue
            last = next(
                (
                    d
                    for d in reversed(list(_month_days(month)))
                    if self._session(d)["status"] == "TRADING"
                ),
                None,
            )
            if last is not None and last >= since and now >= self._closes_at(last):
                due.append(("MONTH_END", month))
        for month in self.store.report_months(self.user_id):
            if month["loss_locked_at"]:
                due.append(("MILESTONE", f"{month['month']}-LOSS_LOCK"))
            if month["profit_locked_at"]:
                due.append(("MILESTONE", f"{month['month']}-PROFIT_LOCK"))
        return due
'''

NEW_DUE = '''    def due_periods(self, now):
        since = self._since()
        self._scan_expected = self._scan_next = None
        if since is None:
            return []
        today = now.astimezone(IST).date()
        if since > today:
            return []
        stored = self.store.report_scan_cursor(self.user_id, since)
        first = max(since, date.fromisoformat(stored))
        due = []
        months = {today.strftime("%Y-%m"),
                  (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
        if first <= today:
            self._scan_expected = stored
            last = min(today, first + timedelta(days=SCAN_DAYS_PER_TICK - 1))
            day = first
            while day <= last:
                session = self._session(day)
                if session["status"] in (
                    "CALENDAR_UNAPPROVED", "SESSION_WINDOW_UNAVAILABLE", "UNAVAILABLE"
                ):
                    # Do not declare an undecidable historical day processed.
                    break
                if session["status"] == "TRADING":
                    if not session.get("window") or now < self._closes_at(day):
                        # Today's incomplete session must be reconsidered later.
                        break
                    due.append(("DAILY", day.isoformat()))
                months.add(day.strftime("%Y-%m"))
                day += timedelta(days=1)
            self._scan_next = day.isoformat()

        for month in sorted(months):
            # Month-end requires a complete, approved/dated session authority.
            if self.store.approved_calendar_version(self.user_id, int(month[:4])) is None:
                continue
            sessions = [self._session(d) for d in _month_days(month)]
            if any(row["status"] in (
                "CALENDAR_UNAPPROVED", "SESSION_WINDOW_UNAVAILABLE", "UNAVAILABLE"
            ) for row in sessions):
                continue
            last = next(
                (d for d in reversed(list(_month_days(month)))
                 if self._session(d)["status"] == "TRADING"
                 and self._session(d).get("window")), None,
            )
            if last is not None and last >= since and now >= self._closes_at(last):
                due.append(("MONTH_END", month))
        for month in self.store.report_months(self.user_id):
            if month["loss_locked_at"]:
                due.append(("MILESTONE", f"{month['month']}-LOSS_LOCK"))
            if month["profit_locked_at"]:
                due.append(("MILESTONE", f"{month['month']}-PROFIT_LOCK"))
        return due
'''

TESTS = r'''def test_report_backlog_scans_old_days_and_intermediate_months(tmp_path):
    """A long outage cannot silently discard reports more than 7 days old."""
    value = make_store(tmp_path, "long_outage", holidays=[MONTH_END_HOLIDAY])
    try:
        now = datetime(2026, 12, 15, 10, 20, tzinfo=UTC)
        for _ in range(7):
            service(value, Clock(now), since=date(2026, 10, 1), send=ok_send()).tick(now)
        all_rows = rows(value)
        month_keys = {row["period_key"] for row in all_rows if row["kind"] == "MONTH_END"}
        day_keys = {row["period_key"] for row in all_rows if row["kind"] == "DAILY"}
        assert {"2026-10", "2026-11"} <= month_keys
        assert "2026-10-01" in day_keys
        assert "2026-11-16" in day_keys
        assert value.report_scan_cursor(USER, date(2026, 10, 1)) > "2026-12-15"
    finally:
        value.engine.dispose()


def test_unknown_session_window_does_not_consume_report_scan_day(store, monkeypatch):
    class MissingMarketHours(Phase1MarketCalendar):
        @staticmethod
        def get_market_timing(exchange):
            return None

    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: MissingMarketHours())
    assert session_calendar.nifty_session(USER, SESSION, store=store)["status"] == (
        "SESSION_WINDOW_UNAVAILABLE"
    )
    service(store, Clock(AFTER_CLOSE), send=ok_send()).tick(AFTER_CLOSE)
    assert not [item for item in rows(store) if item["kind"] == "DAILY"]
    assert store.report_scan_cursor(USER, SESSION) == SESSION.isoformat()


'''

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "database/nifty_algo_db.py": [
        (
            'MODE_HISTORY_LIMIT = 50\n',
            NEW_MODEL + 'MODE_HISTORY_LIMIT = 50\n',
        ),
        (
            '    def report_months(self, user_id):\n',
            NEW_METHODS + '    def report_months(self, user_id):\n',
        ),
        (
            '        # A revised calendar recomputes current and future cooldown sessions.\n'
            '        self.resolve_cooldowns(user_id, now or datetime.now(UTC), recompute=True)',
            '        # A revised calendar can affect historical report eligibility as well.\n'
            '        self.rewind_report_scan_cursor(user_id, result["year"])\n'
            '        # A revised calendar recomputes current and future cooldown sessions.\n'
            '        self.resolve_cooldowns(user_id, now or datetime.now(UTC), recompute=True)',
        ),
    ],
    "test/test_nifty_algo_phase6.py": [
        (
            "# Milestones ---------------------------------------------------------------------",
            TESTS + "# Milestones ---------------------------------------------------------------------",
        ),
    ],
    "services/nifty_algo/reports.py": [
        (
            'LOOKBACK_DAYS = 7',
            'SCAN_DAYS_PER_TICK = 14  # Durable backlog scan, bounded per scheduler tick',
        ),
        (
            '        self._sessions = {}\n',
            '        self._sessions = {}\n'
            '        self._scan_expected = None\n'
            '        self._scan_next = None\n',
        ),
        (
            '        return [day for day in _month_days(month_key) if self._session(day)["status"] == "TRADING"]',
            '        return [\n'
            '            day for day in _month_days(month_key)\n'
            '            if self._session(day)["status"] == "TRADING"\n'
            '            and self._session(day).get("window") is not None\n'
            '        ]',
        ),
        (
            OLD_DUE,
            NEW_DUE,
        ),
        (
            '        for kind, period_key in self.due_periods(now):\n'
            '            self.store.ensure_report(self.user_id, kind, period_key, now)\n'
            '        generated = []',
            '        for kind, period_key in self.due_periods(now):\n'
            '            self.store.ensure_report(self.user_id, kind, period_key, now)\n'
            '        # Only commit cursor progress after reserving every discovered period.\n'
            '        if self._scan_expected is not None and self._scan_next > self._scan_expected:\n'
            '            self.store.advance_report_scan_cursor(\n'
            '                self.user_id, self._scan_expected, self._scan_next\n'
            '            )\n'
            '        generated = []',
        ),
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "database/nifty_algo_db.py").is_file():
        print("Run from repository root or supply --root", file=sys.stderr)
        return 2
    outputs = {}
    errors = []
    for rel, pairs in REPLACEMENTS.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"Missing: {rel}")
            continue
        original = path.read_text(encoding="utf-8")
        revised = original
        for idx, (old, new) in enumerate(pairs, 1):
            found = revised.count(old)
            if found != 1:
                errors.append(f"{rel}: anchor {idx} expected once, got {found}")
            else:
                revised = revised.replace(old, new, 1)
        outputs[path] = (original, revised)
    if errors:
        print("ABORT: no files changed. Source mismatch detected.", *errors, sep="\n - ")
        return 2
    for path, (before, after) in outputs.items():
        print("".join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile=str(path.relative_to(root)),
            tofile=str(path.relative_to(root)) + " (patched)")), end="")
    if not args.apply:
        print("\nDRY RUN ONLY. Run again with --apply after inspecting diff.")
        return 0
    backup = root.parent / (root.name + "_nifty_patch_backups") / ("reports_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    written = []
    try:
        for path in outputs:
            destination = backup / path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        for path, (_, new) in outputs.items():
            path.write_text(new, encoding="utf-8", newline="")
            written.append(path)
    except Exception as exc:
        for path in written:
            shutil.copy2(backup / path.relative_to(root), path)
        print(f"Write failed: {exc}. Restored written files; backups at {backup}", file=sys.stderr)
        return 1
    print(f"\nApplied. Backups: {backup}")
    print("IMPORTANT: This adds a database table at next initialize() call. Back up DB first.")
    print("Run focused reports, calendar, and full NIFTY tests; then Linux gthread gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
