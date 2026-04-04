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

# Step 2: Check Lambda packages
print_info "Step 2: Checking Lambda packages..."

LAMBDAS=("hello-world" "calculator" "sre-platform")
if [ "$LAMBDA_NAME" != "all" ]; then
    LAMBDAS=("$LAMBDA_NAME")
fi

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
        print_success "Package found for $lambda"
    fi
done

if [ "$REBUILD_NEEDED" = true ]; then
    print_warning "Lambda packages need to be rebuilt"
    read -p "Rebuild packages now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Rebuilding Lambda packages using Jenkins Docker images..."
        print_warning "Note: This requires Docker to be running"

        for lambda in "${LAMBDAS[@]}"; do
            print_info "Building $lambda..."

            # Build Docker image
            docker build -f "backend/lambdas/$lambda/Dockerfile" -t "lambda-$lambda-ci:latest" . || {
                print_error "Failed to build Docker image for $lambda"
                exit 1
            }

            # Create package directory
            rm -rf "backend/lambdas/$lambda/package"
            mkdir -p "backend/lambdas/$lambda/package"

            # Run container to create package
            docker run --rm -v "$(pwd)/backend/lambdas/$lambda/package:/tmp/package" \
                "lambda-$lambda-ci:latest" \
                bash -c "
                    mkdir -p /tmp/build
                    cp -r \${LAMBDA_TASK_ROOT}/src /tmp/build/
                    cp -r /opt/python/shared /tmp/build/
                    cd /tmp/build
                    zip -r /tmp/package/deployment.zip . -x '*.pyc' '*/__pycache__/*'
                    cd /tmp/package
                    unzip -q deployment.zip
                    rm deployment.zip
                " || {
                print_error "Failed to package $lambda"
                exit 1
            }

            print_success "$lambda packaged successfully"
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
    STACK_NAME=$(echo "$LAMBDA_NAME" | sed 's/-\([a-z]\)/\U\1/g' | sed 's/^./\U&/')Stack-$ENVIRONMENT
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
    STACK_NAME=$(echo "$LAMBDA_NAME" | sed 's/-\([a-z]\)/\U\1/g' | sed 's/^./\U&/')Stack-$ENVIRONMENT
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
    STACK_NAME=$(echo "$lambda" | sed 's/-\([a-z]\)/\U\1/g' | sed 's/^./\U&/')Stack-$ENVIRONMENT

    print_info "Checking $lambda Lambda function..."
    FUNCTION_NAME="${lambda}-api-${ENVIRONMENT}"

    if aws lambda get-function --function-name "$FUNCTION_NAME" &> /dev/null; then
        print_success "$lambda Lambda function exists"

        # Get function configuration
        MEMORY=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query MemorySize --output text)
        TIMEOUT=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query Timeout --output text)
        RUNTIME=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query Runtime --output text)

        echo "  Memory: ${MEMORY}MB, Timeout: ${TIMEOUT}s, Runtime: $RUNTIME"
    else
        print_warning "$lambda Lambda function not found (might be event-driven)"
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
