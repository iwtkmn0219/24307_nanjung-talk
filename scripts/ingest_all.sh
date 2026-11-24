#!/usr/bin/env bash
# 적재 Lambda를 월 문서마다 순서대로 호출한다.
# 사용: scripts/ingest_all.sh [data_id 접미사 glob]   예) scripts/ingest_all.sh 0080_010_00[1-7]
# 환경변수: INGEST_FUNCTION(필수), RAW_DIR(기본 data/raw)
set -euo pipefail
: "${INGEST_FUNCTION:?INGEST_FUNCTION 환경변수에 적재 Lambda 이름을 넣으시오}"
RAW_DIR="${RAW_DIR:-data/raw}"
PATTERN="${1:-}"
total=0
shopt -s nullglob
for f in "$RAW_DIR"/ITKC_MO_0232A_${PATTERN}*.html; do
  id="$(basename "$f" .html)"
  aws lambda invoke --function-name "$INGEST_FUNCTION" \
    --cli-binary-format raw-in-base64-out --cli-read-timeout 960 \
    --payload "{\"action\":\"ingest\",\"key\":\"raw/$id.html\"}" /tmp/ingest_out.json >/dev/null
  if grep -q '"errorMessage"' /tmp/ingest_out.json; then
    echo "FAIL $id: $(cat /tmp/ingest_out.json)" >&2; exit 1
  fi
  n="$(sed -n 's/.*"count": *\([0-9]*\).*/\1/p' /tmp/ingest_out.json)"
  total=$((total + n))
  echo "$id $n (누계 $total)"
done
echo "합계 $total"
