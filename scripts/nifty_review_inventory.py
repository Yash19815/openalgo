"""Tracked-file NIFTY review inventory. Never follows filesystem junctions."""

import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = {
    "services/nifty_algo/config.py",
    "services/nifty_algo/confidence.py",
    "services/nifty_algo/confidence_comparison.py",
    "services/nifty_algo/indicators.py",
    "services/nifty_algo/signal_engine.py",
    "services/nifty_algo/session_policy.py",
    "services/nifty_algo/depth_quote.py",
    "services/nifty_algo/fees.py",
    "services/nifty_algo/feed_diagnostics.py",
    "services/nifty_algo/report_policy.py",
    "services/nifty_algo/assessment.py",
    "services/nifty_algo/calendar.py",
    "services/nifty_algo/selection_scoring.py",
    "frontend/src/features/nifty-algo/KeySettings.tsx",
    "frontend/src/features/nifty-algo/ExperimentsPanel.tsx",
}
PARTIAL_PREFIXES = (
    "services/nifty_algo/",
    "database/nifty_",
    "blueprints/nifty_",
    "frontend/src/features/nifty-algo/",
    "test/test_nifty_algo_",
    "broker/angel/streaming/",
    "websocket_proxy/",
)
SHARED = {
    "services/market_data_service.py",
    "services/websocket_client.py",
    "database/market_calendar_db.py",
    "database/master_contract_status_db.py",
    "database/engine_factory.py",
    "utils/db_sessions.py",
    "utils/email_utils.py",
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    "CLAUDE.md",
    "AGENTS.md",
    "apply_nifty_safety_fixes.py",
    "apply_nifty_report_recovery.py",
}


def main():
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode("utf-8")
        .split("\0")
    )
    rows = []
    for name in sorted(set(names)):
        if not name or not (
            name.startswith(PARTIAL_PREFIXES)
            or name in SHARED
            or name.startswith("docs/nifty-algo/")
            or name.startswith("frontend/e2e/")
            or name.startswith("scripts/nifty_")
            or name.startswith("frontend/dist/")
        ):
            continue
        if "/evidence/" in name or name.endswith("REVIEW_COVERAGE_2026-11.md"):
            continue  # Avoid self-referential content hashes of generated evidence.
        path = ROOT / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        status = (
            "FULLY_REVIEWED"
            if name in FULL
            else "PARTIALLY_REVIEWED"
            if name.startswith(PARTIAL_PREFIXES) or name in SHARED
            else "NOT_REVIEWED"
        )
        if name.startswith("frontend/dist/"):
            status = "GENERATED_EXCLUDED"
        if name.startswith("docs/nifty-algo/"):
            status = "NOT_REVIEWED"  # Historical documents are not certified by this focused pass.
        imports, symbols = [], []
        if name.endswith(".py"):
            tree = ast.parse(raw.decode("utf-8-sig"), filename=name)
            imports = sorted(
                {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
                | {
                    alias.name
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Import)
                    for alias in n.names
                }
            )
            symbols = sorted(
                n.name
                for n in ast.walk(tree)
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            )
        rows.append(
            {
                "path": name,
                "status": status,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "imports": imports,
                "symbols": symbols,
            }
        )
    evidence = ROOT / "docs/nifty-algo/evidence/review-inventory.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "method": "git-index-and-untracked-list-no-filesystem-recursion",
                "counts": dict(Counter(r["status"] for r in rows)),
                "files": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NIFTY focused review coverage — 2026-11-25",
        "",
        "Coverage is incomplete for the repository as a whole. Passing tests do not certify unread code.",
        "FULLY_REVIEWED means full text was reviewed in this remediation session. PARTIALLY_REVIEWED means targeted functions/imports/callers were examined; it does not inherit the original Claude audit's coverage.",
        "Historical documentation and unchanged tests are not promoted to full review merely because they were searched or executed.",
        "Generated frontend distributions are excluded. Dependencies, virtual environments, caches, private DBs, uploaded calendars, secrets and temporary output are excluded from filesystem traversal.",
        "Inventory uses git's index, not a recursive glob, and cannot follow frontend/node_modules/openalgo back into the repository.",
        "",
        "The JSON records exact source hashes, Python imports and symbols for review reproducibility.",
        "",
        "| File | Review status |",
        "|---|---|",
    ]
    lines.extend(
        f"| `{r['path']}` | {r['status']} |" for r in rows if r["status"] != "GENERATED_EXCLUDED"
    )
    (ROOT / "docs/nifty-algo/REVIEW_COVERAGE_2026-11.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(Counter(r["status"] for r in rows), sort_keys=True))


if __name__ == "__main__":
    main()
