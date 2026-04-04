#!/bin/bash
# =============================================================================
# VirtualAssist Connect - Deployment Script
#
# Usage:
#   ./scripts/deploy.sh <environment> [lambda-name]
#
# Examples:
#   ./scripts/deploy.sh dev                    # Deploy all stacks to dev
#   ./scripts/deploy.sh dev calculator         # Deploy only calculator to dev
#   ./scripts/deploy.sh prod                   # Deploy all stacks to prod
#
# Environments: dev, staging, prod
# Lambda names: hello-world, calculator, sre-platform
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=====================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Validate arguments
if [ $# -lt 1 ]; then
    print_error "Usage: $0 <environment> [lambda-name]"
    echo ""
    echo "Environments: dev, staging, prod"
    echo "Lambda names: hello-world, calculator, sre-platform"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Deploy all stacks to dev"
    echo "  $0 dev calculator         # Deploy only calculator to dev"
    echo "  $0 prod                   # Deploy all stacks to prod"
    exit 1
fi

ENVIRONMENT=$1
LAMBDA_NAME=${2:-"all"}

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT"
    echo "Valid environments: dev, staging, prod"
    exit 1
fi

# Validate lambda name if specified
if [ "$LAMBDA_NAME" != "all" ] && [[ ! "$LAMBDA_NAME" =~ ^(hello-world|calculator|sre-platform)$ ]]; then
    print_error "Invalid lambda name: $LAMBDA_NAME"
    echo "Valid lambda names: hello-world, calculator, sre-platform"
    exit 1
fi

# Navigate to project root
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

print_header "VirtualAssist Connect Deployment"
echo "Environment: $ENVIRONMENT"
echo "Target: $LAMBDA_NAME"
echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: Validate prerequisites
print_info "Step 1: Validating prerequisites..."

# CRITICAL: Check for lessons-learnt memory
MEMORY_FILE="$HOME/.claude/projects/-Users-rameshnagarajan/memory/deployment_local_testing_requirement_2026-04-04.md"
if [ -f "$MEMORY_FILE" ]; then
    print_info "✓ Lessons-learnt memory detected - enforcing local testing"
else
    print_warning "No lessons-learnt memory found - proceeding with caution"
fi

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install: https://aws.amazon.com/cli/"
    exit 1
fi
print_success "AWS CLI found"

# Check CDK CLI
if ! command -v cdk &> /dev/null; then
    print_error "CDK CLI not found. Please install: npm install -g aws-cdk"
    exit 1
fi
print_success "CDK CLI found"

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured. Run 'aws configure'"
    exit 1
fi
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
print_success "AWS credentials configured (Account: $AWS_ACCOUNT)"

# Verify config.json has environment
if ! jq -e ".${ENVIRONMENT}" infra/config.json &> /dev/null; then
    print_error "Environment '$ENVIRONMENT' not found in infra/config.json"
    exit 1
fi
print_success "Environment configuration found in config.json"

# Step 2: Run local validation tests (MANDATORY - prevent deployment failures)
print_info "Step 2: Running local Lambda validation tests..."

LAMBDAS=("hello-world" "calculator" "sre-platform")
if [ "$LAMBDA_NAME" != "all" ]; then
    LAMBDAS=("$LAMBDA_NAME")
fi

# Check if Docker is available for local testing
if ! command -v docker &> /dev/null; then
    print_error "Docker is required for local Lambda testing"
    echo "Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Run local import tests for each Lambda
TESTS_FAILED=false
for lambda in "${LAMBDAS[@]}"; do
    TEST_SCRIPT="backend/lambdas/$lambda/package/test-lambda-imports.py"

    if [ ! -f "$TEST_SCRIPT" ]; then
        print_warning "No test script found for $lambda - creating one..."
        cp test-lambda-imports.py "backend/lambdas/$lambda/package/" 2>/dev/null || {
            print_error "Cannot create test script for $lambda"
            TESTS_FAILED=true
            continue
        }
    fi

    print_info "Testing $lambda in Lambda Docker environment..."

    if docker run --rm --entrypoint python3 \
        -v "$(pwd)/backend/lambdas/$lambda/package:/var/task" \
        public.ecr.aws/lambda/python:3.12 \
        /var/task/test-lambda-imports.py &>/tmp/lambda-test-$lambda.log; then
        print_success "$lambda: All imports validated ✓"
    else
        print_error "$lambda: Import validation FAILED"
        echo "See log: /tmp/lambda-test-$lambda.log"
        cat /tmp/lambda-test-$lambda.log
        TESTS_FAILED=true
    fi
done

if [ "$TESTS_FAILED" = true ]; then
    print_error "Local validation tests FAILED"
    echo ""
    echo "❌ DEPLOYMENT BLOCKED - Local tests must pass before deploying"
    echo ""
    echo "Fix the issues and run tests again:"
    echo "  docker run --rm --entrypoint python3 \\"
    echo "    -v \$(pwd)/backend/lambdas/<lambda>/package:/var/task \\"
    echo "    public.ecr.aws/lambda/python:3.12 \\"
    echo "    /var/task/test-lambda-imports.py"
    exit 1
fi

print_success "All local validation tests PASSED"

# Step 3: Check Lambda packages
print_info "Step 3: Checking Lambda packages..."

REBUILD_NEEDED=false
for lambda in "${LAMBDAS[@]}"; do
    PACKAGE_DIR="backend/lambdas/$lambda/package"

    if [ ! -d "$PACKAGE_DIR" ]; then
        print_warning "Package directory missing for $lambda"
        REBUILD_NEEDED=true
    elif [ -z "$(ls -A $PACKAGE_DIR)" ]; then
        print_warning "Package directory empty for $lambda"
        REBUILD_NEEDED=true
    else
        # Validate package has dependencies (not just src/)
        if [ ! -d "$PACKAGE_DIR/pydantic" ] && [ ! -d "$PACKAGE_DIR/opentelemetry" ]; then
            print_warning "Package for $lambda missing dependencies (only has src/shared)"
            REBUILD_NEEDED=true
        else
            print_success "Package found for $lambda (with dependencies)"
        fi
    fi
done

if [ "$REBUILD_NEEDED" = true ]; then
    print_warning "Lambda packages need to be rebuilt"
    read -p "Rebuild packages now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Rebuilding Lambda packages with dependencies..."

        # Check if pip3 is available
        if ! command -v pip3 &> /dev/null; then
            print_error "pip3 not found. Please install Python 3 and pip."
            exit 1
        fi

        for lambda in "${LAMBDAS[@]}"; do
            print_info "Building $lambda..."

            # Create package directory
            rm -rf "backend/lambdas/$lambda/package"
            mkdir -p "backend/lambdas/$lambda/package"

            # Install dependencies for Lambda runtime (Python 3.12, Linux)
            print_info "  Installing dependencies..."
            pip3 install -r "backend/lambdas/$lambda/requirements.txt" \
                -t "backend/lambdas/$lambda/package/" \
                --platform manylinux2014_x86_64 \
                --only-binary=:all: \
                --python-version 3.12 \
                --implementation cp \
                --quiet || {
                print_error "Failed to install dependencies for $lambda"
                print_info "Tip: If this fails, use Docker instead: docker build -f backend/lambdas/$lambda/Dockerfile ..."
                exit 1
            }

            # Copy source code
            print_info "  Copying source code..."
            cp -r "backend/lambdas/$lambda/src" "backend/lambdas/$lambda/package/"

            # Copy shared layer
            print_info "  Copying shared layer..."
            cp -r "backend/lambda-layer/python/shared" "backend/lambdas/$lambda/package/"

            # Copy config files if they exist
            if [ -f "backend/lambdas/$lambda/incident_config.json" ]; then
                cp "backend/lambdas/$lambda/incident_config.json" "backend/lambdas/$lambda/package/"
            fi

            # Validate package
            if [ -d "backend/lambdas/$lambda/package/pydantic" ] || [ -d "backend/lambdas/$lambda/package/opentelemetry" ]; then
                PACKAGE_SIZE=$(du -sh "backend/lambdas/$lambda/package" | cut -f1)
                print_success "$lambda packaged successfully (${PACKAGE_SIZE})"
            else
                print_error "$lambda package validation failed - dependencies missing"
                exit 1
            fi
        done
    else
        print_error "Deployment cannot proceed without Lambda packages"
        exit 1
    fi
fi

# Step 3: Production confirmation
if [ "$ENVIRONMENT" = "prod" ]; then
    print_warning "⚠️  PRODUCTION DEPLOYMENT ⚠️"
    echo ""
    echo "You are about to deploy to PRODUCTION"
    echo "This will affect live users and systems"
    echo ""
    read -p "Are you absolutely sure? Type 'DEPLOY' to confirm: " CONFIRM

    if [ "$CONFIRM" != "DEPLOY" ]; then
        print_error "Production deployment cancelled"
        exit 1
    fi
    print_success "Production deployment confirmed"
fi

# Step 4: CDK Diff
print_info "Step 4: Previewing infrastructure changes..."
cd infra

print_info "Running CDK diff..."
if [ "$LAMBDA_NAME" = "all" ]; then
    cdk diff --all --context env="$ENVIRONMENT" || true
else
    # Convert lambda name to PascalCase stack name (e.g., "calculator" -> "CalculatorStack-dev")
    STACK_NAME="$(echo "$LAMBDA_NAME" | awk '{for(i=1;i<=NF;i++){sub(/./,toupper(substr($i,1,1)),$i)}}1' FS='-' OFS='')Stack-$ENVIRONMENT"
    cdk diff "$STACK_NAME" --context env="$ENVIRONMENT" || true
fi

echo ""
read -p "Proceed with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Deployment cancelled by user"
    exit 0
fi

# Step 5: CDK Deploy
print_header "Deploying to $ENVIRONMENT"

if [ "$LAMBDA_NAME" = "all" ]; then
    print_info "Deploying all stacks..."
    cdk deploy --all --context env="$ENVIRONMENT" --require-approval never || {
        print_error "Deployment failed"
        exit 1
    }
else
    # Convert lambda name to PascalCase stack name (e.g., "calculator" -> "CalculatorStack-dev")
    STACK_NAME="$(echo "$LAMBDA_NAME" | awk '{for(i=1;i<=NF;i++){sub(/./,toupper(substr($i,1,1)),$i)}}1' FS='-' OFS='')Stack-$ENVIRONMENT"
    print_info "Deploying $STACK_NAME..."
    cdk deploy "$STACK_NAME" --context env="$ENVIRONMENT" --require-approval never || {
        print_error "Deployment failed"
        exit 1
    }
fi

print_success "Deployment completed successfully"

# Step 6: Post-deployment validation
print_info "Step 6: Post-deployment validation..."

# Get API Gateway URL from CloudFormation outputs
for lambda in "${LAMBDAS[@]}"; do
    # Convert lambda name to PascalCase stack name (e.g., "calculator" -> "CalculatorStack-dev")
    STACK_NAME="$(echo "$lambda" | awk '{for(i=1;i<=NF;i++){sub(/./,toupper(substr($i,1,1)),$i)}}1' FS='-' OFS='')Stack-$ENVIRONMENT"

    print_info "Checking $lambda Lambda function..."
    FUNCTION_NAME="${lambda}-api-${ENVIRONMENT}"

    if aws lambda get-function --function-name "$FUNCTION_NAME" &> /dev/null; then
        print_success "$lambda Lambda function exists"

        # Get function configuration
        MEMORY=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query MemorySize --output text)
        TIMEOUT=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query Timeout --output text)
        RUNTIME=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query Runtime --output text)

        echo "  Memory: ${MEMORY}MB, Timeout: ${TIMEOUT}s, Runtime: $RUNTIME"

        # Verify ADOT layer
        ADOT_LAYER=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" \
            --query 'Layers[?contains(Arn, `aws-otel-python`)].Arn' --output text 2>/dev/null)

        if [[ "$ADOT_LAYER" == *"1-32-0"* ]]; then
            print_success "  ADOT Layer: 1-32-0:2 ✓"
        elif [ -n "$ADOT_LAYER" ]; then
            print_warning "  ADOT Layer: $ADOT_LAYER (expected 1-32-0:2)"
        fi

        # Test invocation (optional)
        if [ "$lambda" = "calculator" ]; then
            print_info "  Testing Lambda invocation..."
            TEST_RESULT=$(aws lambda invoke \
                --function-name "$FUNCTION_NAME" \
                --payload '{"httpMethod":"POST","path":"/calculator/add","body":"{\"a\":5,\"b\":3}"}' \
                --cli-binary-format raw-in-base64-out \
                /tmp/test-response.json 2>&1)

            if grep -q '"statusCode": 200' /tmp/test-response.json 2>/dev/null; then
                RESULT=$(cat /tmp/test-response.json | jq -r '.body' | jq -r '.result' 2>/dev/null)
                if [ "$RESULT" = "8.0" ]; then
                    print_success "  Lambda test: 5 + 3 = 8 ✓"
                else
                    print_warning "  Lambda test returned unexpected result"
                fi
            else
                print_warning "  Lambda test invocation returned non-200 status"
            fi
            rm -f /tmp/test-response.json
        fi
    else
        # Check event-driven Lambdas
        FUNCTION_NAME_ALT="incident-${lambda//-/-}-${ENVIRONMENT}"
        if aws lambda get-function --function-name "$FUNCTION_NAME_ALT" &> /dev/null 2>&1; then
            print_success "$lambda Lambda function exists ($FUNCTION_NAME_ALT)"
        else
            print_warning "$lambda Lambda function not found"
        fi
    fi
done

# Step 7: Summary
print_header "Deployment Summary"
print_success "Environment: $ENVIRONMENT"
print_success "Target: $LAMBDA_NAME"
print_success "AWS Account: $AWS_ACCOUNT"
print_success "Region: $(aws configure get region)"
echo ""
print_info "Next steps:"
echo "  1. Check CloudWatch Logs: aws logs tail /aws/lambda/<function-name> --follow"
echo "  2. Test API endpoints: curl <api-gateway-url>"
echo "  3. Check X-Ray traces: AWS Console -> X-Ray -> Traces"
echo "  4. Monitor CloudWatch alarms"
echo ""
print_success "Deployment complete!"
