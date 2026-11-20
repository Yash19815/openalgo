"""Pure parsing and validation for operator-supplied NIFTY session calendars."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

from pypdf import PdfReader

MAX_CALENDAR_BYTES = 2 * 1024 * 1024
_WEEKDAY = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", re.IGNORECASE
)
_DATE = re.compile(
    r"\b(?:"
    r"\d{4}-\d{1,2}-\d{1,2}|"
    r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}|"
    r"\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r")\b"
)
_YEAR = re.compile(r"\b20\d{2}\b")
_MONTHS = {name.lower(): number for number, name in enumerate(
    ("", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December")
) if name}


class CalendarImportError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CalendarParse:
    year: int | None
    segment: str
    entries: list[dict]
    issues: tuple[str, ...]


def _check_size(data):
    if not isinstance(data, bytes):
        raise CalendarImportError("FILE_TYPE_UNSUPPORTED", "Upload must be bytes")
    if len(data) > MAX_CALENDAR_BYTES:
        raise CalendarImportError("FILE_TOO_LARGE", "Calendar upload exceeds 2 MB")


def _years(text):
    return sorted({int(value) for value in _YEAR.findall(text)})


def _segment(text):
    if re.search(r"\b(equity\s+derivatives|f\s*&\s*o|futures\s*(?:&|and)\s*options|nfo)\b",
                 text, re.IGNORECASE):
        return "NFO"
    return "UNKNOWN"


def _parse_date(token, circular_year):
    raw = token.strip()
    for fmt in ("%d-%b-%Y", "%d/%b/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date(), False
        except ValueError:
            pass
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if iso:
        try:
            return date(*map(int, iso.groups())), False
        except ValueError:
            return None, False
    named = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", raw)
    if named:
        month = _MONTHS.get(named.group(1).lower())
        if month:
            try:
                return date(int(named.group(3)), month, int(named.group(2))), False
            except ValueError:
                return None, False
    numeric = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?", raw)
    if not numeric:
        return None, False
    first, second, year_text = numeric.groups()
    if not year_text:
        return None, True
    year = int(year_text)
    if year < 100:
        year += 2000
    day, month = int(first), int(second)
    unclear = day <= 12 and month <= 12
    try:
        return date(year, month, day), unclear
    except ValueError:
        try:
            return date(year, day, month), True
        except ValueError:
            return None, unclear


def _entry_date_row(raw, token, circular_year):
    parsed, unclear = _parse_date(token, circular_year)
    weekdays = _WEEKDAY.findall(raw)
    stated = weekdays[0].title() if weekdays else None
    calculated = parsed.strftime("%A") if parsed else ""
    issues = []
    if unclear:
        issues.append("DATE_FORMAT_UNCLEAR")
    if parsed is None:
        issues.append("DATE_INVALID")
    if parsed is not None and circular_year is not None and parsed.year != circular_year:
        issues.append("DATE_OUTSIDE_CIRCULAR_YEAR")
    if parsed is not None and stated and stated.casefold() != calculated.casefold():
        issues.append("WEEKDAY_MISMATCH")
    if parsed is not None and parsed.weekday() >= 5:
        issues.append("WEEKEND_HOLIDAY")
    name = raw.replace(token, " ")
    if stated:
        name = re.sub(rf"\b{re.escape(weekdays[0])}\b", " ", name, count=1, flags=re.I)
    name = re.sub(r"[|•·\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" :-–—")
    return {
        "date": parsed.isoformat() if parsed else None,
        "weekday": stated or calculated or None,
        "name": name,
        "ambiguous": any(issue != "WEEKEND_HOLIDAY" for issue in issues),
        "issue": ",".join(issues) or None,
        "raw": raw,
    }, issues


def _finalize(entries, years, base_issues, circular_year=None):
    issues = list(base_issues)
    if len(years) > 1:
        issues.append("MULTIPLE_YEARS")
        for entry in entries:
            entry["ambiguous"] = True
            entry["issue"] = ",".join(filter(None, (entry["issue"], "MULTIPLE_YEARS")))
    year = circular_year if circular_year is not None else (
        years[0] if len(years) == 1 else None if years else next(
            (date.fromisoformat(entry["date"]).year for entry in entries if entry["date"]), None
        )
    )
    seen = set()
    for entry in entries:
        if entry["date"] is None:
            continue
        if entry["date"] in seen:
            entry["ambiguous"] = True
            entry["issue"] = ",".join(filter(None, (entry["issue"], "DUPLICATE_DATE")))
            issues.append("DUPLICATE_DATE")
        seen.add(entry["date"])
        parsed = date.fromisoformat(entry["date"])
        if parsed.weekday() >= 5:
            issues.append("WEEKEND_HOLIDAY")
        if year is not None and parsed.year != year:
            entry["ambiguous"] = True
            entry["issue"] = ",".join(filter(None, (entry["issue"], "DATE_OUTSIDE_CIRCULAR_YEAR")))
            issues.append("DATE_OUTSIDE_CIRCULAR_YEAR")
    return CalendarParse(year, "NFO", entries, tuple(dict.fromkeys(issues)))


def parse_holiday_pdf(data: bytes) -> CalendarParse:
    _check_size(data)
    if not data.startswith(b"%PDF-"):
        raise CalendarImportError("FILE_TYPE_UNSUPPORTED", "Expected a PDF calendar")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        raise CalendarImportError("PDF_INVALID", "PDF could not be read") from None
    if not text.strip():
        return CalendarParse(None, "UNKNOWN", [], ("SCANNED_OR_UNREADABLE", "SEGMENT_UNCONFIRMED"))
    segment = _segment(text)
    years = _years(text)
    issues = [] if segment == "NFO" else ["SEGMENT_UNCONFIRMED"]
    if not years:
        issues.append("YEAR_UNCONFIRMED")
    entries = []
    lines = text.splitlines()
    first_date_line = next(
        (index for index, line in enumerate(lines) if _DATE.search(line)), len(lines)
    )
    heading_years = _years("\n".join(lines[:first_date_line]))
    circular_year = heading_years[0] if len(heading_years) == 1 else None
    for line in lines:
        match = _DATE.search(line)
        if match:
            entry, row_issues = _entry_date_row(line.strip(), match.group(), circular_year)
            entries.append(entry)
            issues.extend(row_issues)
    result = _finalize(entries, years, issues, circular_year)
    return CalendarParse(result.year, segment, result.entries, result.issues)


def parse_holiday_csv(data: bytes) -> CalendarParse:
    _check_size(data)
    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except UnicodeDecodeError:
        raise CalendarImportError("FILE_TYPE_UNSUPPORTED", "CSV must be UTF-8 text") from None
    fields = {field.strip().lower() for field in (reader.fieldnames or [])}
    if fields != {"date", "name"}:
        raise CalendarImportError("FILE_TYPE_UNSUPPORTED", "CSV requires date,name columns")
    entries = []
    issues = []
    years = []
    for row in reader:
        raw_date = (row.get("date") or "").strip()
        raw_name = (row.get("name") or "").strip()
        try:
            parsed = date.fromisoformat(raw_date)
            if parsed.isoformat() != raw_date:
                raise ValueError
        except ValueError:
            entries.append({
                "date": None, "weekday": None, "name": raw_name, "ambiguous": True,
                "issue": "DATE_INVALID", "raw": raw_date,
            })
            issues.append("DATE_INVALID")
            continue
        years.append(parsed.year)
        entries.append({
            "date": raw_date,
            "weekday": parsed.strftime("%A"),
            "name": raw_name,
            "ambiguous": False,
            "issue": None,
            "raw": f"{raw_date},{raw_name}",
        })
    result = _finalize(entries, sorted(set(years)), issues)
    return CalendarParse(result.year, "NFO", result.entries, result.issues)


def recompute_entries(entries, year):
    normalized = []
    for value in entries:
        if not isinstance(value, dict):
            raise CalendarImportError("ENTRIES_INVALID", "Each calendar entry must be an object")
        entry = dict(value)
        parsed = None
        try:
            parsed = date.fromisoformat(str(entry.get("date")))
        except ValueError:
            pass
        issues = []
        if parsed is None:
            issues.append("DATE_INVALID")
        else:
            if parsed.year != int(year):
                issues.append("DATE_OUTSIDE_CIRCULAR_YEAR")
            expected = parsed.strftime("%A")
            if entry.get("weekday") and str(entry["weekday"]).casefold() != expected.casefold():
                issues.append("WEEKDAY_MISMATCH")
            entry["weekday"] = expected
            if parsed.weekday() >= 5:
                issues.append("WEEKEND_HOLIDAY")
            entry["date"] = parsed.isoformat()
        normalized.append({
            "date": entry.get("date"),
            "weekday": entry.get("weekday"),
            "name": str(entry.get("name", "")),
            "ambiguous": any(issue != "WEEKEND_HOLIDAY" for issue in issues),
            "issue": ",".join(issues) or None,
            "raw": str(entry.get("raw", "")),
        })
    seen = set()
    all_issues = []
    for entry in normalized:
        if entry["date"] in seen:
            entry["ambiguous"] = True
            entry["issue"] = ",".join(filter(None, (entry["issue"], "DUPLICATE_DATE")))
            all_issues.append("DUPLICATE_DATE")
        seen.add(entry["date"])
        if entry["issue"]:
            all_issues.extend(entry["issue"].split(","))
        if entry["date"] and date.fromisoformat(entry["date"]).weekday() >= 5:
            all_issues.append("WEEKEND_HOLIDAY")
    return normalized, tuple(dict.fromkeys(all_issues))
