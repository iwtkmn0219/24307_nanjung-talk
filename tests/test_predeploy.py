import certifi
import pytest

from predeploy_check import CA_PATH, check_ca


def test_missing_bundle_fails(tmp_path):
    with pytest.raises(SystemExit, match="없음"):
        check_ca(tmp_path / "none.pem")


def test_unparsable_bundle_fails(tmp_path):
    bad = tmp_path / "bad.pem"
    bad.write_text("not a cert")
    with pytest.raises(SystemExit, match="읽을 수 없음"):
        check_ca(bad)


def test_valid_bundle_passes():
    assert check_ca(certifi.where()) > 0


def test_ca_path_matches_template_env():
    from pathlib import Path
    tpl = Path("template.yaml").read_text(encoding="utf-8")
    assert "DB_SSL_CA: /var/task/nanjung/rds-global-bundle.pem" in tpl
    assert CA_PATH.as_posix().endswith("src/nanjung/rds-global-bundle.pem")
