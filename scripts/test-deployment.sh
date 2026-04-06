#!/bin/bash
# =============================================================================
# VirtualAssist Connect - Deployment Simulation Test
#
# Tests all deployed Lambda functions and validates deployment health
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() { echo -e "${BLUE}=====================================${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}=====================================${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

ENVIRONMENT=${1:-dev}
RESULTS_FILE="/tmp/deployment-test-results-$(date +%Y%m%d-%H%M%S).json"

print_header "Deployment Simulation Test - $ENVIRONMENT"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    print_info "Test $TESTS_TOTAL: $test_name"

    if eval "$test_command"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        print_success "PASSED"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        print_error "FAILED"
        return 1
    fi
}

# Initialize results
echo "{" > "$RESULTS_FILE"
echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"," >> "$RESULTS_FILE"
echo "  \"environment\": \"$ENVIRONMENT\"," >> "$RESULTS_FILE"
echo "  \"tests\": [" >> "$RESULTS_FILE"

print_header "1. Lambda Function Health Checks"

# Test Calculator Lambda
print_info "Testing calculator-api-${ENVIRONMENT}..."
run_test "Calculator Lambda exists" "aws lambda get-function --function-name calculator-api-${ENVIRONMENT} &>/dev/null"

if [ $? -eq 0 ]; then
    # Get configuration
    CALC_CONFIG=$(aws lambda get-function-configuration --function-name calculator-api-${ENVIRONMENT} 2>/dev/null)
    RUNTIME=$(echo "$CALC_CONFIG" | jq -r '.Runtime')
    MEMORY=$(echo "$CALC_CONFIG" | jq -r '.MemorySize')
    TIMEOUT=$(echo "$CALC_CONFIG" | jq -r '.Timeout')

    echo "  Runtime: $RUNTIME, Memory: ${MEMORY}MB, Timeout: ${TIMEOUT}s"

    # Check ADOT layer
    ADOT_LAYER=$(echo "$CALC_CONFIG" | jq -r '.Layers[] | select(.Arn | contains("aws-otel-python")) | .Arn')
    if [[ "$ADOT_LAYER" == *"1-32-0:2"* ]]; then
        print_success "ADOT Layer: 1-32-0:2"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        print_warning "ADOT Layer: $ADOT_LAYER (expected 1-32-0:2)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
fi

# Test Hello World Lambda
print_info "Testing hello-world-api-${ENVIRONMENT}..."
run_test "Hello World Lambda exists" "aws lambda get-function --function-name hello-world-api-${ENVIRONMENT} &>/dev/null"

# Test SRE Platform Lambdas
for lambda_name in detection triage escalation; do
    print_info "Testing incident-${lambda_name}-${ENVIRONMENT}..."
    run_test "SRE ${lambda_name} Lambda exists" "aws lambda get-function --function-name incident-${lambda_name}-${ENVIRONMENT} &>/dev/null"
done

print_header "2. Lambda Function Invocation Tests"

# Test Calculator - Addition
print_info "Testing Calculator: 15 + 27 = ?"
CALC_PAYLOAD='{"httpMethod":"POST","path":"/calculator/add","body":"{\"a\":15,\"b\":27}"}'
aws lambda invoke \
    --function-name calculator-api-${ENVIRONMENT} \
    --payload "$CALC_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/calc-add-response.json &>/dev/null

CALC_RESULT=$(cat /tmp/calc-add-response.json 2>/dev/null | jq -r '.body' 2>/dev/null | jq -r '.result' 2>/dev/null)
if [ "$CALC_RESULT" = "42.0" ]; then
    print_success "Calculator ADD: 15 + 27 = 42 ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Calculator ADD failed (expected 42, got $CALC_RESULT)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Test Calculator - Subtraction
print_info "Testing Calculator: 100 - 42 = ?"
CALC_PAYLOAD='{"httpMethod":"POST","path":"/calculator/subtract","body":"{\"a\":100,\"b\":42}"}'
aws lambda invoke \
    --function-name calculator-api-${ENVIRONMENT} \
    --payload "$CALC_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/calc-sub-response.json &>/dev/null

CALC_RESULT=$(cat /tmp/calc-sub-response.json 2>/dev/null | jq -r '.body' 2>/dev/null | jq -r '.result' 2>/dev/null)
if [ "$CALC_RESULT" = "58.0" ]; then
    print_success "Calculator SUBTRACT: 100 - 42 = 58 ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Calculator SUBTRACT failed (expected 58, got $CALC_RESULT)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Test Calculator - Multiplication
print_info "Testing Calculator: 7 * 6 = ?"
CALC_PAYLOAD='{"httpMethod":"POST","path":"/calculator/multiply","body":"{\"a\":7,\"b\":6}"}'
aws lambda invoke \
    --function-name calculator-api-${ENVIRONMENT} \
    --payload "$CALC_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/calc-mul-response.json &>/dev/null

CALC_RESULT=$(cat /tmp/calc-mul-response.json 2>/dev/null | jq -r '.body' 2>/dev/null | jq -r '.result' 2>/dev/null)
if [ "$CALC_RESULT" = "42.0" ]; then
    print_success "Calculator MULTIPLY: 7 * 6 = 42 ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Calculator MULTIPLY failed (expected 42, got $CALC_RESULT)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Test Calculator - Division
print_info "Testing Calculator: 84 / 2 = ?"
CALC_PAYLOAD='{"httpMethod":"POST","path":"/calculator/divide","body":"{\"a\":84,\"b\":2}"}'
aws lambda invoke \
    --function-name calculator-api-${ENVIRONMENT} \
    --payload "$CALC_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/calc-div-response.json &>/dev/null

CALC_RESULT=$(cat /tmp/calc-div-response.json 2>/dev/null | jq -r '.body' 2>/dev/null | jq -r '.result' 2>/dev/null)
if [ "$CALC_RESULT" = "42.0" ]; then
    print_success "Calculator DIVIDE: 84 / 2 = 42 ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Calculator DIVIDE failed (expected 42, got $CALC_RESULT)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Test Calculator - Division by Zero (error handling)
print_info "Testing Calculator: Error handling (divide by zero)"
CALC_PAYLOAD='{"httpMethod":"POST","path":"/calculator/divide","body":"{\"a\":42,\"b\":0}"}'
aws lambda invoke \
    --function-name calculator-api-${ENVIRONMENT} \
    --payload "$CALC_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/calc-error-response.json &>/dev/null

STATUS_CODE=$(cat /tmp/calc-error-response.json 2>/dev/null | jq -r '.statusCode' 2>/dev/null)
if [ "$STATUS_CODE" = "400" ]; then
    print_success "Calculator ERROR HANDLING: Division by zero returns 400 ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_warning "Calculator ERROR HANDLING: Expected 400, got $STATUS_CODE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Test Hello World Lambda
print_info "Testing Hello World Lambda..."
HELLO_PAYLOAD='{"httpMethod":"GET","path":"/hello"}'
aws lambda invoke \
    --function-name hello-world-api-${ENVIRONMENT} \
    --payload "$HELLO_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/hello-response.json &>/dev/null

HELLO_STATUS=$(cat /tmp/hello-response.json 2>/dev/null | jq -r '.statusCode' 2>/dev/null)
if [ "$HELLO_STATUS" = "200" ]; then
    print_success "Hello World: Returns 200 OK ✓"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Hello World failed (expected 200, got $HELLO_STATUS)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

print_header "3. CloudWatch Logs Validation"

# Check recent logs for calculator
print_info "Checking CloudWatch logs for calculator-api-${ENVIRONMENT}..."
LOG_STREAM=$(aws logs describe-log-streams \
    --log-group-name "/aws/lambda/calculator-api-${ENVIRONMENT}" \
    --order-by LastEventTime \
    --descending \
    --max-items 1 \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null)

if [ -n "$LOG_STREAM" ] && [ "$LOG_STREAM" != "None" ]; then
    print_success "CloudWatch logs available for calculator"

    # Check for errors in recent logs
    ERROR_COUNT=$(aws logs filter-log-events \
        --log-group-name "/aws/lambda/calculator-api-${ENVIRONMENT}" \
        --start-time $(($(date +%s) - 300))000 \
        --filter-pattern "ERROR" \
        --query 'length(events)' \
        --output text 2>/dev/null)

    if [ "$ERROR_COUNT" = "0" ]; then
        print_success "No errors in recent logs"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        print_warning "Found $ERROR_COUNT errors in recent logs"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
else
    print_warning "No recent logs found (may be normal for new deployment)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

print_header "4. API Gateway Endpoints"

# Get API Gateway endpoints from CloudFormation
CALC_API=$(aws cloudformation describe-stacks \
    --stack-name CalculatorStack-${ENVIRONMENT} \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text 2>/dev/null)

HELLO_API=$(aws cloudformation describe-stacks \
    --stack-name HelloWorldStack-${ENVIRONMENT} \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text 2>/dev/null)

if [ -n "$CALC_API" ]; then
    print_success "Calculator API: $CALC_API"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Calculator API endpoint not found"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

if [ -n "$HELLO_API" ]; then
    print_success "Hello World API: $HELLO_API"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_error "Hello World API endpoint not found"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

print_header "5. Observability Stack Validation"

# Check X-Ray traces (may not exist immediately after deployment)
print_info "Checking for X-Ray traces..."
TRACE_COUNT=$(aws xray get-trace-summaries \
    --start-time $(date -u -v-5M +%s 2>/dev/null || date -u --date='5 minutes ago' +%s 2>/dev/null || echo $(($(date +%s) - 300))) \
    --end-time $(date -u +%s) \
    --query 'length(TraceSummaries)' \
    --output text 2>/dev/null || echo "0")

if [ "$TRACE_COUNT" != "0" ] && [ "$TRACE_COUNT" != "None" ]; then
    print_success "X-Ray traces available ($TRACE_COUNT traces found)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_warning "No X-Ray traces found (may be normal for new deployment)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

print_header "6. Infrastructure Validation"

# Check CloudFormation stacks
for stack in AuthStack CalculatorStack HelloWorldStack IncidentManagerStack; do
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${stack}-${ENVIRONMENT}" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null)

    if [[ "$STACK_STATUS" == *"COMPLETE"* ]]; then
        print_success "${stack}: $STACK_STATUS"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        print_error "${stack}: $STACK_STATUS"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
done

# Cleanup temp files
rm -f /tmp/calc-*.json /tmp/hello-response.json

# Finalize results
echo "  ]," >> "$RESULTS_FILE"
echo "  \"summary\": {" >> "$RESULTS_FILE"
echo "    \"total\": $TESTS_TOTAL," >> "$RESULTS_FILE"
echo "    \"passed\": $TESTS_PASSED," >> "$RESULTS_FILE"
echo "    \"failed\": $TESTS_FAILED," >> "$RESULTS_FILE"
echo "    \"success_rate\": \"$(awk "BEGIN {printf \"%.1f\", ($TESTS_PASSED/$TESTS_TOTAL)*100}")%\"" >> "$RESULTS_FILE"
echo "  }" >> "$RESULTS_FILE"
echo "}" >> "$RESULTS_FILE"

# Print summary
print_header "Test Summary"
echo ""
echo "  Total Tests:  $TESTS_TOTAL"
echo "  Passed:       ${GREEN}$TESTS_PASSED${NC}"
echo "  Failed:       ${RED}$TESTS_FAILED${NC}"
echo "  Success Rate: $(awk "BEGIN {printf \"%.1f\", ($TESTS_PASSED/$TESTS_TOTAL)*100}")%"
echo ""
print_info "Detailed results saved to: $RESULTS_FILE"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    print_header "✅ ALL TESTS PASSED"
    exit 0
else
    print_header "⚠️  SOME TESTS FAILED"
    exit 1
fi
