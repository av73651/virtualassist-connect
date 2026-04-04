#!/bin/bash
# =============================================================================
# VirtualAssist Connect - Jenkins Build Trigger
#
# Usage:
#   ./scripts/jenkins-trigger.sh [branch-name]
#
# Examples:
#   ./scripts/jenkins-trigger.sh                           # Trigger current branch
#   ./scripts/jenkins-trigger.sh feature/calculator        # Trigger specific branch
#
# Prerequisites:
#   - Set environment variables:
#     export JENKINS_URL="http://your-jenkins-url:8080"
#     export JENKINS_USER="your-username"
#     export JENKINS_TOKEN="your-api-token"
#
#   OR create ~/.jenkins-credentials file:
#     JENKINS_URL=http://your-jenkins-url:8080
#     JENKINS_USER=your-username
#     JENKINS_TOKEN=your-api-token
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

# Navigate to project root
cd "$(dirname "$0")/.."

print_header "Jenkins Build Trigger"

# Load credentials from file if exists
CREDENTIALS_FILE="$HOME/.jenkins-credentials"
if [ -f "$CREDENTIALS_FILE" ]; then
    print_info "Loading Jenkins credentials from $CREDENTIALS_FILE"
    source "$CREDENTIALS_FILE"
fi

# Check required environment variables
if [ -z "$JENKINS_URL" ] || [ -z "$JENKINS_USER" ] || [ -z "$JENKINS_TOKEN" ]; then
    print_error "Jenkins credentials not configured"
    echo ""
    echo "Please set environment variables:"
    echo "  export JENKINS_URL=\"http://your-jenkins-url:8080\""
    echo "  export JENKINS_USER=\"your-username\""
    echo "  export JENKINS_TOKEN=\"your-api-token\""
    echo ""
    echo "OR create ~/.jenkins-credentials file with:"
    echo "  JENKINS_URL=http://your-jenkins-url:8080"
    echo "  JENKINS_USER=your-username"
    echo "  JENKINS_TOKEN=your-api-token"
    echo ""
    echo "To get API token:"
    echo "  1. Go to Jenkins → Your Profile → Configure"
    echo "  2. Generate API Token"
    exit 1
fi

# Get branch name
if [ $# -eq 0 ]; then
    # Use current git branch
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    print_info "Using current branch: $BRANCH"
else
    BRANCH=$1
    print_info "Using specified branch: $BRANCH"
fi

# Verify branch exists
if ! git rev-parse --verify "$BRANCH" &> /dev/null; then
    print_error "Branch '$BRANCH' does not exist"
    exit 1
fi

# Get latest commit info
COMMIT=$(git rev-parse "$BRANCH")
COMMIT_MSG=$(git log -1 --pretty=%B "$BRANCH" | head -1)
AUTHOR=$(git log -1 --pretty=%an "$BRANCH")

print_info "Latest commit: ${COMMIT:0:8}"
print_info "Author: $AUTHOR"
print_info "Message: $COMMIT_MSG"
echo ""

# Confirm trigger
read -p "Trigger Jenkins build for branch '$BRANCH'? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Build cancelled"
    exit 0
fi

# Trigger Jenkins build
print_info "Triggering Jenkins build..."

JOB_NAME="virtualassist-connect"
BUILD_URL="${JENKINS_URL}/job/${JOB_NAME}/build"

# Use buildWithParameters if branch parameter exists, otherwise use build
RESPONSE=$(curl -X POST "${BUILD_URL}" \
  --user "${JENKINS_USER}:${JENKINS_TOKEN}" \
  --data-urlencode "BRANCH=${BRANCH}" \
  -w "\n%{http_code}" \
  -s)

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 200 ]; then
    print_success "Jenkins build triggered successfully!"

    # Extract queue item location from response headers
    QUEUE_URL="${JENKINS_URL}/queue/api/json"

    # Wait a moment for job to be queued
    sleep 2

    print_info "Checking build status..."

    # Get latest build number
    BUILD_NUMBER=$(curl -s "${JENKINS_URL}/job/${JOB_NAME}/lastBuild/buildNumber" \
      --user "${JENKINS_USER}:${JENKINS_TOKEN}")

    if [ ! -z "$BUILD_NUMBER" ]; then
        BUILD_URL="${JENKINS_URL}/job/${JOB_NAME}/${BUILD_NUMBER}"
        print_success "Build #${BUILD_NUMBER} started"
        print_info "Build URL: ${BUILD_URL}"
        print_info "Console: ${BUILD_URL}/console"

        # Offer to follow build
        echo ""
        read -p "Follow build output? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Following build output (Ctrl+C to stop)..."
            echo ""

            # Follow console output
            curl -s "${BUILD_URL}/logText/progressiveText" \
              --user "${JENKINS_USER}:${JENKINS_TOKEN}" \
              -H "Connection: keep-alive"

            # Check final status
            BUILD_STATUS=$(curl -s "${BUILD_URL}/api/json" \
              --user "${JENKINS_USER}:${JENKINS_TOKEN}" \
              | jq -r '.result')

            echo ""
            if [ "$BUILD_STATUS" = "SUCCESS" ]; then
                print_success "Build completed successfully!"

                # Show artifacts
                print_info "Checking for artifacts..."
                ARTIFACTS=$(curl -s "${BUILD_URL}/api/json" \
                  --user "${JENKINS_USER}:${JENKINS_TOKEN}" \
                  | jq -r '.artifacts[]?.fileName')

                if [ ! -z "$ARTIFACTS" ]; then
                    print_success "Artifacts available:"
                    echo "$ARTIFACTS" | while read artifact; do
                        echo "  - ${BUILD_URL}/artifact/dist/${artifact}"
                    done
                fi
            elif [ "$BUILD_STATUS" = "FAILURE" ]; then
                print_error "Build failed"
                exit 1
            else
                print_warning "Build status: $BUILD_STATUS"
            fi
        fi
    else
        print_warning "Could not retrieve build number, but build was triggered"
        print_info "Check Jenkins UI: ${JENKINS_URL}/job/${JOB_NAME}"
    fi

elif [ "$HTTP_CODE" -eq 403 ]; then
    print_error "Authentication failed (HTTP 403)"
    print_info "Please check your Jenkins credentials"
    exit 1
elif [ "$HTTP_CODE" -eq 404 ]; then
    print_error "Job not found (HTTP 404)"
    print_info "Please verify job name: $JOB_NAME"
    print_info "Jenkins URL: $JENKINS_URL"
    exit 1
else
    print_error "Failed to trigger build (HTTP $HTTP_CODE)"
    echo "Response: $RESPONSE"
    exit 1
fi

print_header "Build Trigger Complete"
print_info "Monitor build: ${JENKINS_URL}/job/${JOB_NAME}"
