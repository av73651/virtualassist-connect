#!/usr/bin/env bash
# Look up a specific request by correlation ID or X-Ray trace ID.
#
# Usage:
#   ./scripts/incident/trace-lookup.sh --stage dev --correlation-id "Root=1-abc-def"
#   ./scripts/incident/trace-lookup.sh --stage prod --trace-id "1-abc-def"
#   ./scripts/incident/trace-lookup.sh --stage prod --request-id "aws-request-id"

set -euo pipefail

STAGE=""
CORRELATION_ID=""
TRACE_ID=""
REQUEST_ID=""
SERVICE="calculator"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"
MINUTES=60

usage() {
    echo "Usage: $0 --stage <dev|prod> [--correlation-id ID | --trace-id ID | --request-id ID]"
    echo ""
    echo "Options:"
    echo "  --stage           Required. Environment stage"
    echo "  --correlation-id  X-Trace-Id / correlation ID from response header or error body"
    echo "  --trace-id        X-Ray trace ID (for X-Ray console lookup)"
    echo "  --request-id      AWS request ID from Lambda context"
    echo "  --service         Service name (default: calculator)"
    echo "  --minutes         Search window in minutes (default: 60)"
    echo "  --region          AWS region (default: us-west-2)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --stage)           STAGE="$2"; shift 2 ;;
        --correlation-id)  CORRELATION_ID="$2"; shift 2 ;;
        --trace-id)        TRACE_ID="$2"; shift 2 ;;
        --request-id)      REQUEST_ID="$2"; shift 2 ;;
        --service)         SERVICE="$2"; shift 2 ;;
        --minutes)         MINUTES="$2"; shift 2 ;;
        --region)          REGION="$2"; shift 2 ;;
        *)                 usage ;;
    esac
done

[[ -z "$STAGE" ]] && { echo "ERROR: --stage is required"; usage; }

LOG_GROUP="/aws/lambda/${SERVICE}-api-${STAGE}"
END_MS=$(($(date +%s) * 1000))
START_MS=$(( END_MS - (MINUTES * 60 * 1000) ))

# Determine search filter
if [[ -n "$CORRELATION_ID" ]]; then
    FILTER="\"$CORRELATION_ID\""
    echo "=== Trace Lookup: correlation-id ==="
    echo "Searching for: $CORRELATION_ID"
elif [[ -n "$TRACE_ID" ]]; then
    FILTER="\"$TRACE_ID\""
    echo "=== Trace Lookup: trace-id ==="
    echo "Searching for: $TRACE_ID"

    # Also fetch X-Ray trace summary
    echo ""
    echo "--- X-Ray Trace ---"
    aws xray get-trace-summaries \
        --start-time "$((START_MS / 1000))" \
        --end-time "$((END_MS / 1000))" \
        --filter-expression "traceId = \"$TRACE_ID\"" \
        --region "$REGION" \
        --output json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
summaries = data.get('TraceSummaries', [])
if not summaries:
    print('  No X-Ray trace found for this ID')
else:
    for s in summaries:
        print(f'  Status:    {s.get(\"Http\", {}).get(\"HttpStatus\", \"N/A\")}')
        print(f'  Method:    {s.get(\"Http\", {}).get(\"HttpMethod\", \"N/A\")}')
        print(f'  URL:       {s.get(\"Http\", {}).get(\"HttpURL\", \"N/A\")}')
        print(f'  Duration:  {s.get(\"Duration\", \"N/A\")}s')
        print(f'  Has Error: {s.get(\"HasError\", False)}')
        print(f'  Has Fault: {s.get(\"HasFault\", False)}')
" 2>/dev/null || echo "  (X-Ray lookup failed — check permissions)"

elif [[ -n "$REQUEST_ID" ]]; then
    FILTER="\"$REQUEST_ID\""
    echo "=== Trace Lookup: request-id ==="
    echo "Searching for: $REQUEST_ID"
else
    echo "ERROR: Provide --correlation-id, --trace-id, or --request-id"
    usage
fi

echo "Log group:  $LOG_GROUP"
echo "Window:     last ${MINUTES} minutes"
echo ""

# Search CloudWatch logs
echo "--- CloudWatch Logs ---"
aws logs filter-log-events \
    --log-group-name "$LOG_GROUP" \
    --start-time "$START_MS" \
    --end-time "$END_MS" \
    --filter-pattern "$FILTER" \
    --region "$REGION" \
    --output json 2>/dev/null | python3 << 'PYEOF'
import json, sys

data = json.load(sys.stdin)
events = data.get("events", [])

if not events:
    print("  No matching log events found.")
    print("  Tips:")
    print("  - Increase --minutes window")
    print("  - Verify the ID is correct")
    print("  - Check the --stage matches where the request was made")
    sys.exit(0)

print(f"  Found {len(events)} log entries\n")

for event in events:
    ts = event.get("timestamp", 0)
    msg = event.get("message", "")
    try:
        log = json.loads(msg)
        level = log.get("level", "INFO")
        message = log.get("message", "")
        operation = log.get("operation", "")
        status = log.get("status", "")
        duration = log.get("duration_ms", "")
        error = log.get("error", "")
        error_type = log.get("error_type", "")

        line = f"  [{level}] {message}"
        if operation:
            line += f" | op={operation}"
        if status:
            line += f" | status={status}"
        if duration:
            line += f" | {duration}ms"
        if error_type:
            line += f" | {error_type}: {error}"
        print(line)
    except (json.JSONDecodeError, TypeError):
        # Non-JSON log line (Lambda platform logs)
        print(f"  [RAW] {msg.strip()[:200]}")

PYEOF
