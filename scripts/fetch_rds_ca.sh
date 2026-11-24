#!/usr/bin/env bash
# RDS 공식 CA 번들을 Lambda 패키지 위치로 받고 검사한다. sam build 전에 실행한다.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
OUT="src/nanjung/rds-global-bundle.pem"
curl -fsSL --proto '=https' "$URL" -o "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
python scripts/predeploy_check.py
