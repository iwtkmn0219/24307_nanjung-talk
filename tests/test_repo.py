import subprocess


def test_ingest_script_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", "scripts/ingest_all.sh"], capture_output=True, text=True,
                         check=True).stdout
    assert out.startswith("100755"), out


import os
import shutil
from pathlib import Path

import pytest

GIT_BASH = next((p for p in [r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")] if p and Path(p).exists()), None)


@pytest.mark.skipif(GIT_BASH is None, reason="bash 없음")
def test_ingest_all_fails_when_nothing_matches(tmp_path):
    env = {**os.environ, "INGEST_FUNCTION": "fn", "RAW_DIR": str(tmp_path).replace("\\", "/")}
    r = subprocess.run([GIT_BASH, "scripts/ingest_all.sh", "9999"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode != 0 and "0개" in r.stderr


def test_ingest_all_uses_mktemp():
    s = Path("scripts/ingest_all.sh").read_text(encoding="utf-8")
    assert "mktemp" in s and "/tmp/ingest_out.json" not in s
