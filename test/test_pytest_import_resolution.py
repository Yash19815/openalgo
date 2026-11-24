"""Exercise collection in an application folder named like the installed SDK.

These synthetic modules load no application or worker runtime. The legacy bare
helper import and packaged NIFTY import must both survive SDK imports in either
collection order, including a checkout whose parent has a package marker.
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


@pytest.mark.parametrize("reverse", [False, True])
def test_sdk_and_both_helper_import_styles_collect(tmp_path, reverse):
    root = Path(__file__).resolve().parents[1]
    assert not (root / "__init__.py").exists()
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["pytest"]["ini_options"]["pythonpath"] == [".", "test"]
    checkout = tmp_path / "openalgo"
    tests = checkout / "test"
    tests.mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = [".", "test"]\n', encoding="utf-8"
    )
    (tests / "import_support.py").write_text("VALUE = 7\n", encoding="utf-8")
    (tests / "test_legacy.py").write_text(
        "from import_support import VALUE\nfrom openalgo import api\n"
        "def test_legacy():\n    assert VALUE == 7 and callable(api)\n",
        encoding="utf-8",
    )
    (tests / "test_packaged.py").write_text(
        "from openalgo import api\nfrom test.import_support import VALUE\n"
        "def test_packaged():\n    assert VALUE == 7 and callable(api)\n",
        encoding="utf-8",
    )
    paths = ["test/test_legacy.py", "test/test_packaged.py"]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *(reversed(paths) if reverse else paths),
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=checkout,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
