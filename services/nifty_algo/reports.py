"""PDF reports and their email delivery. Read-only over feature data; never orders.

Kinds:

- ``DAILY`` (``YYYY-MM-DD``): each approved ``TRADING`` session, once its window
  has closed plus ``REPORT_GRACE``. A session with no primary entry is the
  ``ZERO_TRADE`` variant of the same report and lists why.
- ``MILESTONE`` (``YYYY-MM-LOSS_LOCK`` / ``YYYY-MM-PROFIT_LOCK``): a monthly lock
  latched on ``nifty_algo_month``. Its id is appended to the month row's
  ``milestone_report_ids``.
- ``MONTH_END`` (``YYYY-MM``): the monthly summary, after the last approved
  ``TRADING`` session of the IST month has closed. "Month-end" and "monthly"
  name the same report: same period, same trigger, same content.

Generation and delivery run from the runner's own scheduler job, never a request
thread and never the 1-second protection job. Each tick is bounded: at most
``GENERATIONS_PER_TICK`` PDFs and ``SENDS_PER_TICK`` emails, and every SMTP socket
operation times out after ``SMTP_TIMEOUT_SECONDS``. The job stays on the
scheduler's own worker (a green thread under eventlet), because the sockets are
patched there; a real OS thread would run patched sockets off the hub.
"""

import os
import re
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

from utils.logging import get_logger

from .calendar import IST, nifty_session

logger = get_logger(__name__)

KINDS = ("DAILY", "MILESTONE", "MONTH_END")
PERIOD_PATTERNS = {
    "DAILY": r"\d{4}-\d{2}-\d{2}",
    "MILESTONE": r"\d{4}-\d{2}-(LOSS|PROFIT)_LOCK",
    "MONTH_END": r"\d{4}-\d{2}",
}
REPORT_GRACE = timedelta(minutes=10)
SCAN_DAYS_PER_TICK = 14  # Durable backlog scan, bounded per scheduler tick
MAX_GENERATION_ATTEMPTS = 3
MAX_DELIVERY_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 60
CLAIM_LEASE_SECONDS = 300
SMTP_TIMEOUT_SECONDS = 20.0
GENERATIONS_PER_TICK = 3
SENDS_PER_TICK = 1
DEFAULT_CLOSE = time(15, 30)
SMTP_REQUIRED = ("smtp_server", "smtp_port", "smtp_username", "smtp_password", "smtp_from_email")


def backoff(attempts):
    """Delay before the next attempt after ``attempts`` failures: 1, 2, 4, 8 minutes."""
    return timedelta(seconds=BACKOFF_BASE_SECONDS * 2 ** (max(attempts, 1) - 1))


def user_directory(user_id):
    """A path-safe, collision-free directory name; the raw id never reaches the path."""
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", str(user_id))[:40].strip("_") or "user"
    return f"{slug}-{sha256(str(user_id).encode()).hexdigest()[:12]}"


def relative_path(user_id, kind, period_key):
    if kind not in KINDS or not re.fullmatch(PERIOD_PATTERNS[kind], str(period_key)):
        raise ValueError("REPORT_PERIOD_INVALID")
    return f"{user_directory(user_id)}/{kind.lower()}/{period_key}.pdf"


def resolve_report_path(root, relative):
    """Resolve a stored relative path, refusing anything outside the reports root."""
    base = Path(root).resolve()
    if not relative or Path(relative).is_absolute():
        raise ValueError("REPORT_PATH_INVALID")
    candidate = (base / relative).resolve()
    if candidate == base or not candidate.is_relative_to(base) or candidate.suffix != ".pdf":
        raise ValueError("REPORT_PATH_INVALID")
    return candidate


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".report-", suffix=".tmp")
    try:
        output = os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        Path(temporary).unlink(missing_ok=True)
        raise
    try:
        with output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=IST)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _month_bounds(key):
    year, month = (int(part) for part in key.split("-"))
    start = datetime(year, month, 1, tzinfo=IST)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=IST)
    return start.astimezone(UTC), end.astimezone(UTC)


def _month_days(key):
    start, end = _month_bounds(key)
    day = start.astimezone(IST).date()
    last = (end - timedelta(microseconds=1)).astimezone(IST).date()
    while day <= last:
        yield day
        day += timedelta(days=1)


def _amount(value):
    return Decimal(str(value or 0))


def _counts(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _trade_totals(trades):
    nets = [_amount(item["net"]) for item in trades]
    return {
        "trades": len(trades),
        "wins": sum(1 for net in nets if net > 0),
        "gross": str(sum((_amount(item["gross"]) for item in trades), Decimal("0"))),
        "fees": str(sum((_amount(item["fees"]) for item in trades), Decimal("0"))),
        "realized_net": str(sum(nets, Decimal("0"))),
        "best": str(max(nets)) if nets else None,
        "worst": str(min(nets)) if nets else None,
    }


def _refusals(events):
    codes = []
    for event in events:
        if event["kind"] == "entry_rejected":
            codes.extend(str(code) for code in event["payload"].get("reasons") or [])
        elif event["kind"] == "data_blocked" and event["payload"].get("reason"):
            codes.extend(
                part.strip() for part in re.split(r"[;,]", str(event["payload"]["reason"]))
            )
    return [code for code in codes if code]


LOCK_EVENTS = (
    "MONTHLY_LOSS_LOCKED",
    "MONTHLY_PROFIT_LOCKED",
    "SESSION_LOSS_COOLDOWN",
    "COOLDOWN_SCHEDULED",
    "COOLDOWN_RECOMPUTED",
)
CONTROL_EVENTS = ("start", "pause", "stop", "kill-switch")


def zero_trade_reasons(inputs, end):
    """Why a session had no primary entry, as codes, in a stable order."""
    reasons = list(inputs["cooldown_reasons"])
    month = inputs["month"] or {}
    if month.get("loss_locked_at") and datetime.fromisoformat(month["loss_locked_at"]) < end:
        reasons.append("MONTHLY_LOSS_LOCK")
    if month.get("profit_locked_at") and datetime.fromisoformat(month["profit_locked_at"]) < end:
        reasons.append("MONTHLY_PROFIT_LOCK")
    reasons.extend(_refusals(inputs["events"]))
    if any(event["kind"] == "kill-switch" for event in inputs["events"]):
        reasons.append("KILL_SWITCH")
    if not inputs["decisions"]:
        reasons.append("NO_ASSESSMENT_RECORDED")
    elif not any(item["eligible"] for item in inputs["decisions"]):
        reasons.append("NO_ELIGIBLE_SIGNAL")
    if inputs["buys"] and not any(item["filled"] for item in inputs["buys"]):
        reasons.append("ENTRY_NOT_FILLED")
    if not reasons:
        reasons.append("NO_ENTRY_ATTEMPTED")
    return list(dict.fromkeys(reasons))


def _shadow_section(inputs):
    independent = [row for row in inputs["shadows"] if row["additive"]]
    mirrors = [row for row in inputs["shadows"] if not row["additive"]]
    outcomes = _counts(row["outcome"] or row["status"] for row in inputs["opportunities"])
    rows = [
        ["Independent shadows", str(len(independent))],
        [
            "Independent hypothetical net (Rs)",
            str(sum((_amount(row["net"]) for row in independent), Decimal("0"))),
        ],
        ["Mirror shadows", str(len(mirrors))],
        [
            "Mirror net (Rs, non-additive)",
            str(sum((_amount(row["net"]) for row in mirrors), Decimal("0"))),
        ],
        ["Research opportunities", str(len(inputs["opportunities"]))],
    ]
    rows.extend([f"Outcome {code}", str(count)] for code, count in outcomes)
    return (
        "Shadow and research (hypothetical)",
        rows,
        "Mirror P&L duplicates the primary paper trade and is never added to totals.",
    )


def _decision_section(inputs):
    decisions = inputs["decisions"]
    rows = [
        ["Assessments", str(len(decisions))],
        ["Eligible", str(sum(1 for item in decisions if item["eligible"]))],
    ]
    for side in ("CE", "PE"):
        rows.append(
            [
                f"Eligible {side}",
                str(sum(1 for i in decisions if i["eligible"] and i["side"] == side)),
            ]
        )
    reasons = _counts(code for item in decisions for code in item["reasons"])[:10]
    rows.extend([f"Reason {code}", str(count)] for code, count in reasons)
    return "Signal decisions", rows, None


def _trade_rows(trades):
    rows = [["Closed (UTC)", "Contract", "Qty", "Entry", "Exit", "Fees", "Net", "Reason"]]
    rows.extend(
        [
            item["closed_at"][:16].replace("T", " "),
            item["symbol"],
            str(item["quantity"]),
            item["entry_price"],
            item["exit_price"],
            item["fees"],
            item["net"],
            item["reason"],
        ]
        for item in trades
    )
    return rows


def _lock_rows(inputs):
    rows = [[f"Cooldown {code}", "active"] for code in inputs["cooldown_reasons"]]
    month = inputs["month"] or {}
    rows.append(["Monthly loss lock", month.get("loss_locked_at") or "not set"])
    rows.append(["Monthly profit lock", month.get("profit_locked_at") or "not set"])
    for event in inputs["events"]:
        if event["kind"] in LOCK_EVENTS:
            payload = event["payload"]
            detail = payload.get("month") or payload.get("loss_session") or ""
            if payload.get("cooldown_session"):
                detail = f"{detail} -> {payload['cooldown_session']}"
            rows.append([event["kind"], str(detail)])
    controls = _counts(e["kind"] for e in inputs["events"] if e["kind"] in CONTROL_EVENTS)
    rows.extend([f"Control {kind}", str(count)] for kind, count in controls)
    return rows


def daily_content(store, user_id, period_key):
    day = date.fromisoformat(period_key)
    start, end = _day_bounds(day)
    inputs = store.report_inputs(user_id, start, end)
    totals = _trade_totals(inputs["trades"])
    entries = sum(1 for item in inputs["buys"] if item["filled"])
    zero = not inputs["trades"] and not entries
    reasons = zero_trade_reasons(inputs, end) if zero else []
    sections = [
        (
            "Session summary",
            [
                ["Session (IST)", period_key],
                ["Primary entries filled", str(entries)],
                ["Closed trades", str(totals["trades"])],
                ["Fees (Rs)", totals["fees"]],
                ["Realized net (Rs)", totals["realized_net"]],
            ],
            None,
        )
    ]
    if zero:
        sections.append(("Why no primary trade", [[code, "reason"] for code in reasons], None))
    if inputs["trades"]:
        sections.append(("Primary trades", _trade_rows(inputs["trades"]), None))
    sections.append(_decision_section(inputs))
    refusals = _counts(_refusals(inputs["events"]))
    sections.append(
        (
            "Refusals",
            [[code, str(count)] for code, count in refusals] or [["None recorded", "0"]],
            None,
        )
    )
    sections.append(("Locks and cooldown", _lock_rows(inputs), None))
    sections.append(_shadow_section(inputs))
    summary = {
        "session": period_key,
        "trades": totals["trades"],
        "entries": entries,
        "realized_net": totals["realized_net"],
        "zero_trade_reasons": reasons,
    }
    title = f"NIFTY paper daily report {period_key}" + (" (zero-trade session)" if zero else "")
    return ("ZERO_TRADE" if zero else "STANDARD"), title, sections, summary


def milestone_content(store, user_id, period_key):
    month_key, lock = period_key[:7], period_key[8:]
    month = next((row for row in store.report_months(user_id) if row["month"] == month_key), None)
    if month is None:
        raise ValueError("MONTH_ROW_MISSING")
    field = "loss" if lock == "LOSS_LOCK" else "profit"
    locked_at = month[f"{field}_locked_at"]
    if locked_at is None:
        raise ValueError("LOCK_NOT_SET")
    detail = month["lock_detail"].get(field, {})
    start, _ = _month_bounds(month_key)
    locked = datetime.fromisoformat(locked_at)
    inputs = store.report_inputs(user_id, start, locked + timedelta(microseconds=1))
    totals = _trade_totals(inputs["trades"])
    threshold = detail.get("limit") if field == "loss" else detail.get("target")
    sections = [
        (
            "Milestone",
            [
                ["Month (IST)", month_key],
                ["Lock", f"MONTHLY_{field.upper()}_LOCK"],
                ["Locked at (UTC)", locked_at[:19]],
                [
                    "Realized net at lock (Rs)",
                    str(detail.get("realized_net", month["realized_net"])),
                ],
                ["Loss limit (Rs)" if field == "loss" else "Profit target (Rs)", str(threshold)],
                ["Trades this month to lock", str(totals["trades"])],
            ],
            "New primary entries are refused for the rest of the month. Exits and "
            "protection continue.",
        )
    ]
    if inputs["trades"]:
        sections.append(("Trades this month", _trade_rows(inputs["trades"]), None))
    summary = {
        "month": month_key,
        "lock": f"MONTHLY_{field.upper()}_LOCK",
        "realized_net": str(detail.get("realized_net", month["realized_net"])),
        "locked_at": locked_at,
    }
    return "STANDARD", f"NIFTY paper milestone {month_key}: {field} lock", sections, summary


def month_content(store, user_id, period_key, sessions):
    start, end = _month_bounds(period_key)
    inputs = store.report_inputs(user_id, start, end)
    totals = _trade_totals(inputs["trades"])
    by_session = {}
    for item in inputs["trades"]:
        day = datetime.fromisoformat(item["closed_at"]).astimezone(IST).date().isoformat()
        by_session.setdefault(day, []).append(_amount(item["net"]))
    month = inputs["month"] or {}
    daily = {
        row["period_key"]: row["variant"]
        for row in store.reports(user_id, limit=400)
        if row["kind"] == "DAILY" and row["period_key"].startswith(period_key)
    }
    traded = [day for day in sessions if day in by_session]
    sections = [
        (
            "Month summary",
            [
                ["Month (IST)", period_key],
                ["Eligible sessions", str(len(sessions))],
                ["Sessions with trades", str(len(traded))],
                ["Zero-trade sessions", str(len(sessions) - len(traded))],
                ["Closed trades", str(totals["trades"])],
                ["Winning trades", str(totals["wins"])],
                ["Fees (Rs)", totals["fees"]],
                ["Realized net (Rs)", totals["realized_net"]],
                ["Best trade (Rs)", totals["best"] or "n/a"],
                ["Worst trade (Rs)", totals["worst"] or "n/a"],
                ["Monthly loss lock", month.get("loss_locked_at") or "not set"],
                ["Monthly profit lock", month.get("profit_locked_at") or "not set"],
            ],
            None,
        ),
        (
            "Sessions",
            [["Session", "Net (Rs)", "Daily report"]]
            + [
                [
                    day,
                    str(sum(by_session.get(day, []), Decimal("0"))),
                    daily.get(day, "not generated"),
                ]
                for day in sessions
            ],
            None,
        ),
    ]
    if inputs["cooldowns"]:
        sections.append(
            (
                "Loss cooldowns",
                [["Loss session", "Cooldown session", "Net (Rs)"]]
                + [
                    [
                        row["loss_session"],
                        row["cooldown_session"] or "unresolved",
                        row["realized_net"],
                    ]
                    for row in inputs["cooldowns"]
                ],
                None,
            )
        )
    refusals = _counts(_refusals(inputs["events"]))[:15]
    sections.append(
        (
            "Refusals",
            [[code, str(count)] for code, count in refusals] or [["None recorded", "0"]],
            None,
        )
    )
    sections.append(_shadow_section(inputs))
    summary = {
        "month": period_key,
        "sessions": len(sessions),
        "trades": totals["trades"],
        "realized_net": totals["realized_net"],
    }
    return "STANDARD", f"NIFTY paper month-end report {period_key}", sections, summary


#: Column shares of the printable width, by column count.
COLUMN_WIDTHS = {
    2: [0.6, 0.4],
    3: [0.4, 0.3, 0.3],
    8: [0.15, 0.27, 0.06, 0.1, 0.1, 0.09, 0.1, 0.13],
}


def render_pdf(title, sections, generated_at):
    """Deterministic PDF bytes: no wall clock, invariant document id and dates."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        invariant=1,
        title=title,
        author="OpenAlgo",
        creator="OpenAlgo NIFTY paper reports",
        subject="Paper simulation report",
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    story = [
        Paragraph(escape(title), styles["Title"]),
        Paragraph(
            escape(
                "Paper simulation only. No orders were placed or sent to a broker. "
                f"Generated {generated_at.astimezone(UTC).isoformat()}."
            ),
            styles["Italic"],
        ),
        Spacer(1, 6 * mm),
    ]
    small = ParagraphStyle("NiftyCell", parent=styles["BodyText"], fontSize=7.5, leading=9)
    width = A4[0] - 30 * mm
    for heading, rows, note in sections:
        story.append(Paragraph(escape(heading), styles["Heading2"]))
        if rows:
            columns = len(rows[0])
            widths = COLUMN_WIDTHS.get(columns) or [1 / columns] * columns
            cell = small if columns > 3 else styles["BodyText"]
            table = Table(
                [[Paragraph(escape(str(value)), cell) for value in row] for row in rows],
                colWidths=[width * share for share in widths],
                repeatRows=1 if columns > 3 else 0,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(table)
        if note:
            story.append(Paragraph(escape(note), styles["Italic"]))
        story.append(Spacer(1, 4 * mm))
    document.build(story)
    return buffer.getvalue()


def smtp_ready(settings):
    return bool(settings) and all(settings.get(field) for field in SMTP_REQUIRED)


def _default_smtp_settings():
    from database.settings_db import get_smtp_settings

    return get_smtp_settings()


def _default_recipient(user_id):
    from database.user_db import find_user_by_exact_username

    user = find_user_by_exact_username(user_id)
    return getattr(user, "email", None) or None


def _default_send(*args, **kwargs):
    from utils.email_utils import send_email

    return send_email(*args, **kwargs)


class ReportService:
    def __init__(
        self,
        store,
        user_id,
        *,
        clock=None,
        since=None,
        smtp_settings=None,
        recipient=None,
        send=None,
    ):
        self.store, self.user_id = store, user_id
        self.clock = clock or (lambda: datetime.now(UTC))
        self.since = since
        self.smtp_settings = smtp_settings or _default_smtp_settings
        self.recipient = recipient or (lambda: _default_recipient(user_id))
        self.send = send or _default_send
        self._sessions = {}
        self._scan_expected = None
        self._scan_next = None

    # Triggers --------------------------------------------------------------

    def _session(self, day):
        if day not in self._sessions:
            try:
                self._sessions[day] = nifty_session(self.user_id, day, store=self.store)
            except Exception as exc:
                logger.warning("NIFTY report session lookup failed: %s", type(exc).__name__)
                self._sessions[day] = {"status": "UNAVAILABLE", "window": None}
        return self._sessions[day]

    def _closes_at(self, day):
        window = self._session(day)["window"]
        close = window[1] if window else datetime.combine(day, DEFAULT_CLOSE, tzinfo=IST)
        return close.astimezone(UTC) + REPORT_GRACE

    def eligible_sessions(self, month_key):
        return [
            day for day in _month_days(month_key)
            if self._session(day)["status"] == "TRADING"
            and self._session(day).get("window") is not None
        ]

    def _since(self):
        if self.since is not None:
            return self.since
        first = self.store.user_since(self.user_id)
        return first.astimezone(IST).date() if first else None

    def due_periods(self, now):
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

    # Generation ------------------------------------------------------------

    def content(self, kind, period_key):
        if kind == "DAILY":
            return daily_content(self.store, self.user_id, period_key)
        if kind == "MILESTONE":
            return milestone_content(self.store, self.user_id, period_key)
        return month_content(
            self.store,
            self.user_id,
            period_key,
            [d.isoformat() for d in self.eligible_sessions(period_key)],
        )

    def generate(self, row):
        """Write the PDF atomically and record it. ``created_at`` is the stable generated_at."""
        try:
            relative = relative_path(self.user_id, row["kind"], row["period_key"])
            variant, title, sections, summary = self.content(row["kind"], row["period_key"])
            generated_at = datetime.fromisoformat(row["created_at"])
            data = render_pdf(title, sections, generated_at)
            write_atomic(resolve_report_path(self.store.report_dir, relative), data)
            self.store.complete_report_generation(
                self.user_id,
                row["id"],
                path=relative,
                sha256=sha256(data).hexdigest(),
                size_bytes=len(data),
                variant=variant,
                summary=summary,
                now=self.clock(),
            )
            if row["kind"] == "MILESTONE":
                self.store.link_milestone_report(
                    self.user_id, row["period_key"][:7], row["id"], self.clock()
                )
            return True
        except Exception as exc:
            logger.warning("NIFTY report generation failed: %s", type(exc).__name__)
            self.store.fail_report_generation(
                self.user_id, row["id"], type(exc).__name__, self.clock()
            )
            return False

    def generate_due(self, now):
        for kind, period_key in self.due_periods(now):
            self.store.ensure_report(self.user_id, kind, period_key, now)
        # Only commit cursor progress after reserving every discovered period.
        if self._scan_expected is not None and self._scan_next > self._scan_expected:
            self.store.advance_report_scan_cursor(
                self.user_id, self._scan_expected, self._scan_next
            )
        generated = []
        for row in self.store.reports_needing_generation(self.user_id, MAX_GENERATION_ATTEMPTS):
            if len(generated) >= GENERATIONS_PER_TICK:
                break
            if self.generate(row):
                generated.append(row["id"])
        return generated

    # Delivery --------------------------------------------------------------

    def _message(self, row):
        summary = row["summary"]
        lines = [
            f"OpenAlgo NIFTY paper report: {row['kind']} {row['period_key']}",
            f"Variant: {row['variant']}",
        ]
        for key in ("trades", "entries", "realized_net", "lock", "sessions"):
            if key in summary:
                lines.append(f"{key.replace('_', ' ').capitalize()}: {summary[key]}")
        if summary.get("zero_trade_reasons"):
            lines.append("No primary trade: " + ", ".join(summary["zero_trade_reasons"]))
        lines += [
            "",
            "Paper simulation only. The PDF report is attached.",
            "",
            "--",
            "Sent by OpenAlgo",
        ]
        return (
            f"OpenAlgo NIFTY {row['kind'].replace('_', '-').lower()} report {row['period_key']}",
            "\n".join(lines),
        )

    def _attachment(self, row):
        path = resolve_report_path(self.store.report_dir, row["path"])
        data = path.read_bytes()
        if sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("REPORT_FILE_MODIFIED")
        return (Path(row["path"]).name, data, "application/pdf")

    def deliver_due(self, now):
        self.store.fail_interrupted_deliveries(self.user_id, now)
        rows = self.store.deliverable_reports(self.user_id, now, MAX_DELIVERY_ATTEMPTS)
        if not rows:
            return []
        try:
            settings = self.smtp_settings()
            recipient = self.recipient() if smtp_ready(settings) else None
        except Exception as exc:
            # Leave rows PENDING: a failed settings read is not "SMTP not configured".
            logger.warning("NIFTY report SMTP settings unavailable: %s", type(exc).__name__)
            return []
        if not smtp_ready(settings) or not recipient:
            reason = "SMTP_NOT_CONFIGURED" if not smtp_ready(settings) else "RECIPIENT_UNAVAILABLE"
            for row in rows:
                self.store.skip_report_delivery(self.user_id, row["id"], reason, now)
            return [(row["id"], "SKIPPED_NO_SMTP") for row in rows]
        outcomes = []
        for row in rows:
            if len(outcomes) >= SENDS_PER_TICK:
                break
            token = uuid4().hex
            attempts = self.store.claim_report_delivery(
                self.user_id,
                row["id"],
                token,
                now,
                lease_seconds=CLAIM_LEASE_SECONDS,
                max_attempts=MAX_DELIVERY_ATTEMPTS,
            )
            if attempts is None:
                continue
            error_type = None
            retry_safe = True
            sending = False
            try:
                subject, text = self._message(row)
                attachment = self._attachment(row)
                sending = True
                result = self.send(
                    recipient,
                    subject,
                    text,
                    smtp_settings=settings,
                    attachments=[attachment],
                    timeout=SMTP_TIMEOUT_SECONDS,
                    redact=True,
                )
                sent = bool(result and result.get("success"))
                if not sent:
                    error_type = (result or {}).get("error_type") or "SMTP_SEND_FAILED"
                    retry_safe = bool(result and result.get("retry_safe"))
            except Exception as exc:
                sent, error_type = False, type(exc).__name__
                retry_safe = not sending
            if not sent and not retry_safe:
                error_type = "DELIVERY_OUTCOME_UNKNOWN"
            if error_type:
                logger.warning("NIFTY report delivery failed: %s", error_type)
            finished = self.clock()
            self.store.finish_report_delivery(
                self.user_id,
                row["id"],
                token,
                finished,
                sent=sent,
                error_type=error_type,
                next_attempt_at=(
                    None
                    if sent or not retry_safe or attempts >= MAX_DELIVERY_ATTEMPTS
                    else finished + backoff(attempts)
                ),
            )
            outcomes.append((row["id"], "SENT" if sent else error_type))
        return outcomes

    def tick(self, now=None):
        now = now or self.clock()
        return {"generated": self.generate_due(now), "delivered": self.deliver_due(now)}
