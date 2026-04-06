#!/bin/bash
# =============================================================================
# Pre-Deployment Validation Script
#
# This script MUST pass before any Lambda deployment.
# It enforces lessons learned from past deployment failures.
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() { echo -e "${BLUE}=====================================${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}=====================================${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

LAMBDA_NAME=${1:-""}
if [ -z "$LAMBDA_NAME" ]; then
    print_error "Usage: $0 <lambda-name>"
    echo "Example: $0 calculator"
    exit 1
fi

LAMBDA_DIR="backend/lambdas/$LAMBDA_NAME"
PACKAGE_DIR="$LAMBDA_DIR/package"

print_header "Pre-Deployment Validation: $LAMBDA_NAME"

VALIDATION_FAILED=false

# =============================================================================
# LESSON 1: Check memory for past mistakes
# =============================================================================
print_info "Validation 1: Checking lessons-learnt memory..."

MEMORY_DIR="$HOME/.claude/projects/-Users-rameshnagarajan/memory"
if [ -f "$MEMORY_DIR/deployment_local_testing_requirement_2026-04-04.md" ]; then
    print_success "Local testing requirement documented"
fi

if [ -f "$MEMORY_DIR/deployment_lambda_packaging_lesson.md" ]; then
    print_success "Lambda packaging lesson documented"
fi

if [ -f "$MEMORY_DIR/observability_custom_metrics_iam_2026-04-04.md" ]; then
    print_success "Observability IAM lesson documented"
fi

# =============================================================================
# LESSON 2: Package must have dependencies
# =============================================================================
print_info "Validation 2: Checking package has dependencies..."

if [ ! -d "$PACKAGE_DIR" ]; then
    print_error "Package directory does not exist: $PACKAGE_DIR"
    VALIDATION_FAILED=true
else
    # Check for pydantic (required by all Lambdas)
    if [ -d "$PACKAGE_DIR/pydantic" ]; then
        print_success "pydantic dependency found"
    else
        print_error "pydantic dependency MISSING - package not built correctly"
        VALIDATION_FAILED=true
    fi

    # Check for boto3 (required for custom metrics)
    if [ -d "$PACKAGE_DIR/boto3" ]; then
        print_success "boto3 dependency found"
    else
        print_error "boto3 dependency MISSING - custom metrics will fail"
        VALIDATION_FAILED=true
    fi

    # Check for opentelemetry
    if [ -d "$PACKAGE_DIR/opentelemetry" ]; then
        print_success "opentelemetry dependency found"
    else
        print_error "opentelemetry dependency MISSING - observability will fail"
        VALIDATION_FAILED=true
    fi

    # Check for shared layer
    if [ -d "$PACKAGE_DIR/shared" ]; then
        print_success "shared layer found"
    else
        print_error "shared layer MISSING - middleware will fail"
        VALIDATION_FAILED=true
    fi

    # Check for src
    if [ -d "$PACKAGE_DIR/src" ]; then
        print_success "src code found"
    else
        print_error "src code MISSING"
        VALIDATION_FAILED=true
    fi
fi

# =============================================================================
# LESSON 3: Package size must be reasonable
# =============================================================================
print_info "Validation 3: Checking package size..."

if [ -d "$PACKAGE_DIR" ]; then
    PACKAGE_SIZE=$(du -sm "$PACKAGE_DIR" | cut -f1)

    if [ "$PACKAGE_SIZE" -lt 10 ]; then
        print_error "Package size is ${PACKAGE_SIZE}MB - too small (likely missing dependencies)"
        print_info "Expected: >10MB with dependencies"
        VALIDATION_FAILED=true
    elif [ "$PACKAGE_SIZE" -gt 250 ]; then
        print_error "Package size is ${PACKAGE_SIZE}MB - too large (may exceed Lambda limit)"
        print_info "Lambda limit: 250MB unzipped"
        VALIDATION_FAILED=true
    else
        print_success "Package size: ${PACKAGE_SIZE}MB (reasonable)"
    fi
fi

# =============================================================================
# LESSON 4: Local Docker test must pass
# =============================================================================
print_info "Validation 4: Running local Docker import test..."

if ! command -v docker &> /dev/null; then
    print_error "Docker not installed - cannot run local tests"
    VALIDATION_FAILED=true
else
    TEST_SCRIPT="$PACKAGE_DIR/test-lambda-imports.py"

    if [ ! -f "$TEST_SCRIPT" ]; then
        print_error "Test script not found: $TEST_SCRIPT"
        print_info "Copy test-lambda-imports.py to package directory"
        VALIDATION_FAILED=true
    else
        print_info "Running import test in Lambda Docker..."

        if docker run --rm --entrypoint python3 \
            -v "$(pwd)/$PACKAGE_DIR:/var/task" \
            public.ecr.aws/lambda/python:3.12 \
            /var/task/test-lambda-imports.py &>/tmp/pre-deploy-test.log; then
            print_success "All imports validated in Lambda environment"
            cat /tmp/pre-deploy-test.log | grep "✓"
        else
            print_error "Import test FAILED"
            echo ""
            echo "Test output:"
            cat /tmp/pre-deploy-test.log
            echo ""
            VALIDATION_FAILED=true
        fi
    fi
fi

# =============================================================================
# LESSON 5: Architecture must be x86_64
# =============================================================================
print_info "Validation 5: Checking package architecture..."

if [ -d "$PACKAGE_DIR/pydantic_core" ]; then
    # Check if pydantic_core has x86_64 .so files
    SO_FILES=$(find "$PACKAGE_DIR/pydantic_core" -name "*.so" 2>/dev/null)

    if [ -n "$SO_FILES" ]; then
        # Check architecture of .so files
        ARCH_CHECK=$(file $SO_FILES | head -1)

        if echo "$ARCH_CHECK" | grep -q "x86-64\|x86_64"; then
            print_success "Package built for x86_64 architecture"
        elif echo "$ARCH_CHECK" | grep -q "arm64\|aarch64"; then
            print_error "Package built for ARM architecture - Lambda requires x86_64"
            print_info "Rebuild with: docker run --platform linux/amd64 ..."
            VALIDATION_FAILED=true
        else
            print_info "Architecture: $ARCH_CHECK"
        fi
    fi
fi

# =============================================================================
# LESSON 6: requirements.txt must use HTTP exporter
# =============================================================================
print_info "Validation 6: Checking OpenTelemetry exporter..."

REQUIREMENTS_FILE="$LAMBDA_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    if grep -q "opentelemetry-exporter-otlp-proto-grpc" "$REQUIREMENTS_FILE"; then
        print_error "Using gRPC exporter - this causes binary compatibility issues"
        print_info "Use: opentelemetry-exporter-otlp-proto-http instead"
        VALIDATION_FAILED=true
    elif grep -q "opentelemetry-exporter-otlp-proto-http" "$REQUIREMENTS_FILE"; then
        print_success "Using HTTP exporter (no binary dependencies)"
    else
        print_info "No OTLP exporter specified in requirements.txt"
    fi
fi

# =============================================================================
# Summary
# =============================================================================
print_header "Validation Summary"

if [ "$VALIDATION_FAILED" = true ]; then
    echo ""
    print_error "❌ PRE-DEPLOYMENT VALIDATION FAILED"
    echo ""
    echo "Fix the issues above before deploying."
    echo "This validation prevents repeating past deployment failures."
    echo ""
    exit 1
else
    echo ""
    print_success "✅ ALL VALIDATIONS PASSED"
    echo ""
    print_info "Safe to deploy: ./scripts/deploy.sh dev $LAMBDA_NAME"
    echo ""
    exit 0
fi
