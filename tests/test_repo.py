import subprocess


def test_ingest_script_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", "scripts/ingest_all.sh"], capture_output=True, text=True,
                         check=True).stdout
    assert out.startswith("100755"), out
