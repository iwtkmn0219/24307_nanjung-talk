"""sam build 전에 실행: Lambda 패키지에 RDS CA 번들이 있고 읽히는지 검사한다.

사용: python scripts/predeploy_check.py   (실패하면 종료 코드 1)
번들 받기: bash scripts/fetch_rds_ca.sh
"""
from __future__ import annotations

import ssl
import sys
from pathlib import Path

CA_PATH = Path(__file__).resolve().parent.parent / "src" / "nanjung" / "rds-global-bundle.pem"


def check_ca(path: Path | str = CA_PATH) -> int:
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"RDS CA 번들 없음: {path} — bash scripts/fetch_rds_ca.sh 를 먼저 실행하시오")
    try:
        ctx = ssl.create_default_context(cafile=str(path))
    except (ssl.SSLError, OSError, ValueError) as e:
        raise SystemExit(f"RDS CA 번들을 읽을 수 없음: {path} ({e})") from None
    n = len(ctx.get_ca_certs())
    if n == 0:
        raise SystemExit(f"RDS CA 번들을 읽을 수 없음: {path} (인증서 0개)")
    return n


if __name__ == "__main__":
    print(f"OK: RDS CA 인증서 {check_ca()}개")
