#!/bin/bash
# =============================================================================
# New Lambda Scaffolding Script
#
# Creates a new Lambda function with all enforcement mechanisms built-in:
# - Correct requirements.txt (HTTP exporter, boto3)
# - Build script (Docker-based, x86_64)
# - Test script template
# - Standard directory structure
# - Pre-configured for observability
#
# Usage: ./scripts/create-new-lambda.sh <lambda-name>
# Example: ./scripts/create-new-lambda.sh payment-processor
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Validate input
if [ $# -lt 1 ]; then
    print_error "Usage: $0 <lambda-name>"
    echo ""
    echo "Example: $0 payment-processor"
    echo ""
    exit 1
fi

LAMBDA_NAME=$1
LAMBDA_DIR="backend/lambdas/$LAMBDA_NAME"

# Check if Lambda already exists
if [ -d "$LAMBDA_DIR" ]; then
    print_error "Lambda already exists: $LAMBDA_DIR"
    exit 1
fi

print_info "Creating new Lambda: $LAMBDA_NAME"
echo ""

# Create directory structure
mkdir -p "$LAMBDA_DIR"/{src/{handlers,services,repositories,domain,dto},tests/{unit,integration},package}
print_success "Created directory structure"

# Copy requirements.txt from template
cp templates/lambda-template/requirements.txt "$LAMBDA_DIR/"
print_success "Copied requirements.txt (with HTTP exporter, boto3)"

# Copy build script from template
cp templates/lambda-template/build-in-docker.sh "$LAMBDA_DIR/"
chmod +x "$LAMBDA_DIR/build-in-docker.sh"
print_success "Copied build-in-docker.sh (x86_64 enforcement)"

# Create handler template
cat > "$LAMBDA_DIR/src/handlers/${LAMBDA_NAME//-/_}_handler.py" << 'EOF'
"""Lambda Handler.

Handler layer responsibilities:
- Parse and validate API Gateway events
- Convert domain objects to DTOs
- Format HTTP responses
- NO business logic here
"""

import json
import logging
from typing import Any

from shared.middleware.api_gateway import api_gateway_handler
from shared.middleware.observability import observe

logger = logging.getLogger(__name__)


@api_gateway_handler
def lambda_handler(event: dict, context: Any, trace_id: str) -> dict:
    """Lambda entry point.

    Args:
        event: API Gateway proxy event
        context: Lambda context
        trace_id: X-Ray trace ID from middleware

    Returns:
        dict: Response payload (middleware handles HTTP formatting)
    """
    # TODO: Implement your handler logic

    return {
        "message": "Hello from new Lambda",
        "trace_id": trace_id
    }
EOF
print_success "Created handler template"

# Create service template
LAMBDA_CLASS_NAME=$(echo "$LAMBDA_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) sub(/./,toupper(substr($i,1,1)),$i)}1' | sed 's/ //g')
cat > "$LAMBDA_DIR/src/services/${LAMBDA_NAME//-/_}_service.py" << EOF
"""${LAMBDA_CLASS_NAME} Service.

Service layer responsibilities:
- Business logic ONLY
- No HTTP/API Gateway parsing
- No database parsing
- Domain model operations
"""

import logging
from shared.middleware.observability import observe

logger = logging.getLogger(__name__)


class ${LAMBDA_CLASS_NAME}Service:
    """${LAMBDA_CLASS_NAME} business logic."""

    @observe(operation="process_request", metric_prefix="${LAMBDA_NAME//-/_}")
    def process(self, data: dict) -> dict:
        """Process business logic.

        Args:
            data: Input data

        Returns:
            dict: Processing result
        """
        # TODO: Implement your business logic

        logger.info("Processing request", extra={"data": data})

        return {"status": "success"}
EOF
print_success "Created service template"

# Create basic unit test
cat > "$LAMBDA_DIR/tests/unit/test_${LAMBDA_NAME//-/_}_service.py" << EOF
"""Unit tests for ${LAMBDA_CLASS_NAME}Service."""

import pytest
from src.services.${LAMBDA_NAME//-/_}_service import ${LAMBDA_CLASS_NAME}Service


class Test${LAMBDA_CLASS_NAME}Service:
    """Test suite for ${LAMBDA_CLASS_NAME}Service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = ${LAMBDA_CLASS_NAME}Service()

    def test_process_success(self):
        """Test process method returns success."""
        result = self.service.process({"test": "data"})

        assert result["status"] == "success"
EOF
print_success "Created unit test template"

# Create pytest.ini
cat > "$LAMBDA_DIR/pytest.ini" << 'EOF'
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --cov=src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
markers =
    integration: Integration tests (require API_ENDPOINT env var)
EOF
print_success "Created pytest.ini (80% coverage requirement)"

# Create .flake8
cat > "$LAMBDA_DIR/.flake8" << 'EOF'
[flake8]
max-line-length = 120
exclude =
    .git,
    __pycache__,
    package,
    build,
    dist,
    .venv,
    venv
ignore = E203, W503
EOF
print_success "Created .flake8"

# Create Dockerfile (for Jenkins CI)
cat > "$LAMBDA_DIR/Dockerfile" << 'EOF'
FROM public.ecr.aws/lambda/python:3.12

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy source code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Copy shared layer
COPY ../../lambda-layer/python/shared ${LAMBDA_TASK_ROOT}/shared/

# Handler
CMD ["src.handlers.<handler-name>.lambda_handler"]
EOF

# Update handler name in Dockerfile
sed -i '' "s/<handler-name>/${LAMBDA_NAME//-/_}_handler/g" "$LAMBDA_DIR/Dockerfile"
print_success "Created Dockerfile (for Jenkins CI)"

# Create README
cat > "$LAMBDA_DIR/README.md" << EOF
# ${LAMBDA_NAME} Lambda Function

## Quick Start

### 1. Build Package (MANDATORY - use Docker)
\`\`\`bash
cd backend/lambdas/$LAMBDA_NAME
./build-in-docker.sh
\`\`\`

### 2. Run Tests
\`\`\`bash
pytest tests/
\`\`\`

### 3. Validate Before Deploying (MANDATORY)
\`\`\`bash
cd ../../..
./scripts/pre-deploy-validation.sh $LAMBDA_NAME
\`\`\`

### 4. Deploy
\`\`\`bash
./scripts/deploy.sh dev $LAMBDA_NAME
\`\`\`

## Architecture

\`\`\`
src/
├── handlers/        # API Gateway entry points (NO business logic)
├── services/        # Business logic ONLY
├── repositories/    # Data access ONLY
├── domain/          # Domain models
└── dto/             # Request/response schemas
\`\`\`

## Testing

- **Unit tests**: \`pytest tests/unit/\`
- **Coverage**: Must be ≥80%
- **Linting**: \`flake8 src/\`

## Key Requirements

1. ✅ Build with \`build-in-docker.sh\` (ensures x86_64 architecture)
2. ✅ Run \`pre-deploy-validation.sh\` before deploying
3. ✅ Use \`@observe\` decorator for observability
4. ✅ Use \`@api_gateway_handler\` for API endpoints
5. ✅ Follow layer architecture (handler → service → repository)
6. ✅ 80% test coverage required

## Observability

- **Custom Metrics**: Automatically emitted by \`@observe\` decorator
- **Tracing**: OpenTelemetry with ADOT Layer
- **Logging**: Structured JSON logs with trace_id

## Deployment

See \`skills/definitions/deployment.md\` for full deployment process.
EOF
print_success "Created README.md"

# Summary
echo ""
echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}Lambda Created Successfully${NC}"
echo -e "${BLUE}=====================================${NC}"
echo ""
echo "Lambda: $LAMBDA_NAME"
echo "Location: $LAMBDA_DIR"
echo ""
echo "Next Steps:"
echo ""
echo "1. Implement your business logic:"
echo "   - Edit src/services/${LAMBDA_NAME//-/_}_service.py"
echo "   - Edit src/handlers/${LAMBDA_NAME//-/_}_handler.py"
echo ""
echo "2. Build package (MANDATORY):"
echo "   cd $LAMBDA_DIR"
echo "   ./build-in-docker.sh"
echo ""
echo "3. Run tests:"
echo "   pytest tests/"
echo ""
echo "4. Validate (MANDATORY):"
echo "   ./scripts/pre-deploy-validation.sh $LAMBDA_NAME"
echo ""
echo "5. Deploy:"
echo "   ./scripts/deploy.sh dev $LAMBDA_NAME"
echo ""
print_success "Lambda scaffolding complete!"
echo ""
echo "All enforcement mechanisms are built-in:"
echo "  ✓ Correct requirements.txt (HTTP exporter, boto3)"
echo "  ✓ Docker build script (x86_64)"
echo "  ✓ Test structure (80% coverage)"
echo "  ✓ Observability decorators"
echo "  ✓ Layer architecture"
echo ""
