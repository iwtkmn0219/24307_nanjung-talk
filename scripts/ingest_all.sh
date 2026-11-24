#!/usr/bin/env bash
# 적재 Lambda를 월 문서마다 순서대로 호출한다.
# 사용: bash scripts/ingest_all.sh [data_id 접미사 glob]   예) bash scripts/ingest_all.sh '0080_010_00[1-7]'
# 환경변수: INGEST_FUNCTION(필수), RAW_DIR(기본 data/raw)
set -euo pipefail
: "${INGEST_FUNCTION:?INGEST_FUNCTION 환경변수에 적재 Lambda 이름을 넣으시오}"
RAW_DIR="${RAW_DIR:-data/raw}"
PATTERN="${1:-}"
shopt -s nullglob
files=("$RAW_DIR"/ITKC_MO_0232A_${PATTERN}*.html)
if [ "${#files[@]}" -eq 0 ]; then
  echo "매칭된 파일 0개: $RAW_DIR/ITKC_MO_0232A_${PATTERN}*.html" >&2
  exit 2
fi
out="$(mktemp)"
trap 'rm -f "$out"' EXIT
total=0
for f in "${files[@]}"; do
  id="$(basename "$f" .html)"
  aws lambda invoke --function-name "$INGEST_FUNCTION" \
    --cli-binary-format raw-in-base64-out --cli-read-timeout 960 \
    --payload "{\"action\":\"ingest\",\"key\":\"raw/$id.html\"}" "$out" >/dev/null
  if grep -q '"errorMessage"' "$out"; then
    echo "FAIL $id: $(cat "$out")" >&2; exit 1
  fi
  n="$(sed -n 's/.*"count": *\([0-9]*\).*/\1/p' "$out")"
  if [ -z "$n" ]; then
    echo "FAIL $id: count 없음: $(cat "$out")" >&2; exit 1
  fi
  total=$((total + n))
  echo "$id $n (누계 $total)"
done
echo "합계 $total (문서 ${#files[@]}개)"
