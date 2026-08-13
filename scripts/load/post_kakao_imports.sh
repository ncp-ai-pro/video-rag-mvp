#!/usr/bin/env bash
# Repeatedly submit a synthetic Kakao export to the local/staging import API.
# Default analyze=false keeps the fixture from triggering external YouTube work.
set -euo pipefail

: "${BASE_URL:=http://127.0.0.1:8000}"
: "${FOLDER_ID:?Set FOLDER_ID to the target folder ID.}"
: "${IMPORT_FILE:=/tmp/kakao-youtube-load.txt}"
: "${REQUESTS:=10}"
: "${CONCURRENCY:=1}"
: "${ANALYZE:=false}"
: "${PRIORITY:=bulk}"
: "${COOKIE_JAR:=/tmp/video-rag-load.cookies}"
: "${OUTPUT_DIR:=/tmp/video-rag-kakao-import-results}"

if [[ ! -f "$IMPORT_FILE" ]]; then
  echo "IMPORT_FILE does not exist: $IMPORT_FILE" >&2
  exit 2
fi
if [[ ! "$REQUESTS" =~ ^[1-9][0-9]*$ ]] || [[ ! "$CONCURRENCY" =~ ^[1-9][0-9]*$ ]]; then
  echo "REQUESTS and CONCURRENCY must be positive integers" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

# The endpoint creates an anonymous workspace/session when no cookie exists.
# Preserve its Set-Cookie response so every request targets the same workspace.
curl --fail-with-body --silent --show-error --cookie "$COOKIE_JAR" --cookie-jar "$COOKIE_JAR" \
  "$BASE_URL/auth/me" >/dev/null

submit_one() {
  local number="$1" response_file="$OUTPUT_DIR/import-${number}.json"
  curl --fail-with-body --silent --show-error \
    --cookie "$COOKIE_JAR" \
    -X POST "$BASE_URL/folders/$FOLDER_ID/imports/kakao" \
    -F "file=@$IMPORT_FILE;type=text/plain" \
    -F "analyze=$ANALYZE" \
    -F "priority=$PRIORITY" >"$response_file"
  printf 'request=%s response=%s\n' "$number" "$response_file"
}

export BASE_URL FOLDER_ID IMPORT_FILE ANALYZE PRIORITY COOKIE_JAR OUTPUT_DIR
export -f submit_one

if (( CONCURRENCY == 1 )); then
  for number in $(seq 1 "$REQUESTS"); do submit_one "$number"; done
else
  # Cookie jar writes are not safe concurrently. Seed it above; workers only read it.
  seq 1 "$REQUESTS" | xargs -P "$CONCURRENCY" -n 1 bash -c 'submit_one "$0"'
fi

echo "completed=$REQUESTS responses=$OUTPUT_DIR"
