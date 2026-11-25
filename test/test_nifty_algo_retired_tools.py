"""Historical patchers retain provenance but cannot modify current sources."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ("apply_nifty_safety_fixes.py", "apply_nifty_report_recovery.py"))
def test_retired_patcher_refuses_apply_before_reading_or_writing(tmp_path, name):
    root = Path(__file__).resolve().parents[1]
    sentinel = tmp_path / "user-change.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(root / name), "--apply"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "RETIRED" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["user-change.txt"]
