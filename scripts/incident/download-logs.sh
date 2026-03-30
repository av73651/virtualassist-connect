#!/usr/bin/env bash
# Download CloudWatch logs for a Lambda function and summarize errors.
#
# Usage:
#   ./scripts/incident/download-logs.sh --stage dev --minutes 30
#   ./scripts/incident/download-logs.sh --stage prod --minutes 60 --service calculator
#   ./scripts/incident/download-logs.sh --stage prod --start "2026-03-30T10:00:00Z" --end "2026-03-30T11:00:00Z"

set -euo pipefail

# Defaults
STAGE=""
SERVICE="calculator"
MINUTES=""
START_TIME=""
END_TIME=""
OUTPUT_DIR="./incident-logs"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"

usage() {
    echo "Usage: $0 --stage <dev|prod> [--minutes N | --start ISO --end ISO] [--service NAME] [--region REGION]"
    echo ""
    echo "Options:"
    echo "  --stage      Required. Environment stage (dev, prod)"
    echo "  --minutes    Pull logs from last N minutes (default: 30)"
    echo "  --start      Start time in ISO 8601 (e.g., 2026-03-30T10:00:00Z)"
    echo "  --end        End time in ISO 8601 (e.g., 2026-03-30T11:00:00Z)"
    echo "  --service    Service name (default: calculator)"
    echo "  --region     AWS region (default: us-west-2)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --stage)    STAGE="$2"; shift 2 ;;
        --minutes)  MINUTES="$2"; shift 2 ;;
        --start)    START_TIME="$2"; shift 2 ;;
        --end)      END_TIME="$2"; shift 2 ;;
        --service)  SERVICE="$2"; shift 2 ;;
        --region)   REGION="$2"; shift 2 ;;
        *)          usage ;;
    esac
done

[[ -z "$STAGE" ]] && { echo "ERROR: --stage is required"; usage; }

LOG_GROUP="/aws/lambda/${SERVICE}-api-${STAGE}"

# Calculate time range
if [[ -n "$START_TIME" && -n "$END_TIME" ]]; then
    START_MS=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$START_TIME" "+%s" 2>/dev/null || date -d "$START_TIME" "+%s")000
    END_MS=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$END_TIME" "+%s" 2>/dev/null || date -d "$END_TIME" "+%s")000
else
    MINUTES="${MINUTES:-30}"
    END_MS=$(($(date +%s) * 1000))
    START_MS=$(( END_MS - (MINUTES * 60 * 1000) ))
fi

echo "=== CloudWatch Log Download ==="
echo "Log group:  $LOG_GROUP"
echo "Region:     $REGION"
echo "Time range: $(date -r $((START_MS / 1000)) 2>/dev/null || date -d @$((START_MS / 1000))) → $(date -r $((END_MS / 1000)) 2>/dev/null || date -d @$((END_MS / 1000)))"
echo ""

# Create output directory
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUT_DIR="${OUTPUT_DIR}/${SERVICE}-${STAGE}-${TIMESTAMP}"
mkdir -p "$OUT_DIR"

RAW_FILE="${OUT_DIR}/raw-logs.json"
ERRORS_FILE="${OUT_DIR}/errors.json"
SUMMARY_FILE="${OUT_DIR}/summary.txt"

# Download logs
echo "Downloading logs..."
aws logs filter-log-events \
    --log-group-name "$LOG_GROUP" \
    --start-time "$START_MS" \
    --end-time "$END_MS" \
    --region "$REGION" \
    --output json > "$RAW_FILE" 2>/dev/null

EVENT_COUNT=$(python3 -c "import json; d=json.load(open('$RAW_FILE')); print(len(d.get('events',[])))")
echo "Downloaded $EVENT_COUNT log events → $RAW_FILE"

# Extract and summarize errors
echo ""
echo "=== Error Summary ==="

python3 << 'PYEOF' - "$RAW_FILE" "$ERRORS_FILE" "$SUMMARY_FILE"
import json
import sys
from collections import Counter

raw_file, errors_file, summary_file = sys.argv[1], sys.argv[2], sys.argv[3]

with open(raw_file) as f:
    data = json.load(f)

events = data.get("events", [])
errors = []
error_types = Counter()
error_by_operation = Counter()
total_requests = 0
error_count = 0

for event in events:
    msg = event.get("message", "")
    try:
        log = json.loads(msg)
    except (json.JSONDecodeError, TypeError):
        continue

    if log.get("message", "").startswith("Starting"):
        total_requests += 1

    level = log.get("level", "")
    if level == "ERROR":
        error_count += 1
        errors.append(log)
        etype = log.get("error_type", "Unknown")
        operation = log.get("operation", "unknown")
        error_types[etype] += 1
        error_by_operation[f"{operation} → {etype}"] += 1

# Write errors file
with open(errors_file, "w") as f:
    json.dump(errors, f, indent=2, default=str)

# Build summary
lines = []
lines.append(f"Total log events:  {len(events)}")
lines.append(f"Total requests:    {total_requests}")
lines.append(f"Total errors:      {error_count}")
if total_requests > 0:
    lines.append(f"Error rate:        {error_count/total_requests*100:.1f}%")
lines.append("")

if error_types:
    lines.append("Errors by type:")
    for etype, count in error_types.most_common():
        lines.append(f"  {etype}: {count}")
    lines.append("")

if error_by_operation:
    lines.append("Errors by operation:")
    for key, count in error_by_operation.most_common():
        lines.append(f"  {key}: {count}")

summary = "\n".join(lines)
print(summary)

with open(summary_file, "w") as f:
    f.write(summary + "\n")

PYEOF

echo ""
echo "Files saved to: $OUT_DIR/"
echo "  raw-logs.json  — All log events"
echo "  errors.json    — Error events only"
echo "  summary.txt    — Error summary"
