#!/usr/bin/env bash
# Health check for calculator API endpoints.
#
# Usage:
#   ./scripts/incident/health-check.sh --stage dev
#   ./scripts/incident/health-check.sh --stage prod --endpoint https://xyz.execute-api.us-west-2.amazonaws.com/prod
#   ./scripts/incident/health-check.sh --stage dev --auth-token <JWT>

set -euo pipefail

STAGE=""
ENDPOINT=""
AUTH_TOKEN=""
VERBOSE=false

usage() {
    echo "Usage: $0 --stage <dev|prod> [--endpoint URL] [--auth-token TOKEN] [--verbose]"
    echo ""
    echo "Options:"
    echo "  --stage       Required. Environment stage"
    echo "  --endpoint    API base URL (auto-detected from CloudFormation if omitted)"
    echo "  --auth-token  Cognito JWT token for authenticated requests"
    echo "  --verbose     Show response bodies"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --stage)      STAGE="$2"; shift 2 ;;
        --endpoint)   ENDPOINT="$2"; shift 2 ;;
        --auth-token) AUTH_TOKEN="$2"; shift 2 ;;
        --verbose)    VERBOSE=true; shift ;;
        *)            usage ;;
    esac
done

[[ -z "$STAGE" ]] && { echo "ERROR: --stage is required"; usage; }

# Auto-detect endpoint from CloudFormation
if [[ -z "$ENDPOINT" ]]; then
    echo "Detecting API endpoint from CloudFormation..."
    ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "CalculatorStack-${STAGE}" \
        --query "Stacks[0].Outputs[?OutputKey=='CalculatorApiEndpoint'].OutputValue" \
        --output text 2>/dev/null || echo "")

    if [[ -z "$ENDPOINT" || "$ENDPOINT" == "None" ]]; then
        echo "ERROR: Could not detect endpoint. Provide --endpoint manually."
        exit 1
    fi
fi

ENDPOINT="${ENDPOINT%/}"
BASE="${ENDPOINT}/calculator"

echo "=== Calculator API Health Check ==="
echo "Stage:    $STAGE"
echo "Endpoint: $ENDPOINT"
echo "Auth:     $([ -n "$AUTH_TOKEN" ] && echo "Yes" || echo "No (unauthenticated)")"
echo ""

# Build auth header
AUTH_HEADER=""
if [[ -n "$AUTH_TOKEN" ]]; then
    AUTH_HEADER="-H \"Authorization: Bearer ${AUTH_TOKEN}\""
fi

PASS=0
FAIL=0
TOTAL=0

check_endpoint() {
    local method="$1"
    local url="$2"
    local payload="$3"
    local expected_status="$4"
    local description="$5"

    TOTAL=$((TOTAL + 1))

    local curl_cmd="curl -s -w '\n%{http_code}' -X $method"
    [[ -n "$AUTH_HEADER" ]] && curl_cmd="$curl_cmd -H 'Authorization: Bearer ${AUTH_TOKEN}'"
    [[ -n "$payload" ]] && curl_cmd="$curl_cmd -H 'Content-Type: application/json' -d '$payload'"
    curl_cmd="$curl_cmd '$url'"

    local response
    response=$(eval "$curl_cmd" 2>/dev/null || echo -e "\n000")

    local body status_code
    status_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed '$d')

    if [[ "$status_code" == "$expected_status" ]]; then
        echo "  PASS  $description (HTTP $status_code)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $description (expected $expected_status, got $status_code)"
        FAIL=$((FAIL + 1))
    fi

    if [[ "$VERBOSE" == "true" && -n "$body" ]]; then
        echo "        Response: $body"
    fi
}

echo "--- Endpoint Health ---"

# Addition
check_endpoint POST "${BASE}/add" '{"a":2,"b":3}' "200" "POST /calculator/add (2+3=5)"

# Subtraction
check_endpoint POST "${BASE}/subtract" '{"a":10,"b":3}' "200" "POST /calculator/subtract (10-3=7)"

# Multiplication
check_endpoint POST "${BASE}/multiply" '{"a":4,"b":5}' "200" "POST /calculator/multiply (4*5=20)"

# Division
check_endpoint POST "${BASE}/divide" '{"a":10,"b":2}' "200" "POST /calculator/divide (10/2=5)"

echo ""
echo "--- Error Handling ---"

# Validation error
check_endpoint POST "${BASE}/add" '{"a":"bad"}' "400" "POST /calculator/add (invalid input → 400)"

# Division by zero
check_endpoint POST "${BASE}/divide" '{"a":10,"b":0}' "400" "POST /calculator/divide (div by zero → 400)"

# Missing fields
check_endpoint POST "${BASE}/add" '{"a":5}' "400" "POST /calculator/add (missing field → 400)"

echo ""
echo "=== Results: ${PASS}/${TOTAL} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
    echo "STATUS: UNHEALTHY"
    exit 1
else
    echo "STATUS: HEALTHY"
    exit 0
fi
