#!/bin/bash
# =============================================================================
# Lambda Package Builder (Docker-based for x86_64 compatibility)
#
# This script MUST be used to build Lambda packages to ensure:
# - Correct architecture (x86_64, not ARM)
# - All dependencies included
# - Reproducible builds
# =============================================================================

set -e

LAMBDA_NAME=$(basename "$(dirname "$(pwd)")")

echo "Building Lambda package: $LAMBDA_NAME"
echo "Architecture: linux/amd64 (x86_64)"
echo ""

# Clean old package
rm -rf package
mkdir package

# Build in Lambda Docker environment (x86_64)
docker run --rm \
  --platform linux/amd64 \
  --entrypoint bash \
  -v "$(pwd):/workspace" \
  -w /workspace \
  public.ecr.aws/lambda/python:3.12 \
  -c "
    echo 'Installing dependencies...'
    pip install -r requirements.txt -t package/ --upgrade --quiet
    echo '✓ Dependencies installed'
  "

# Copy source code
echo "Copying source code..."
cp -r src package/
echo "✓ Source copied"

# Copy shared layer
echo "Copying shared layer..."
cp -r ../../lambda-layer/python/shared package/
echo "✓ Shared layer copied"

# Copy test script
echo "Copying test script..."
cp ../../test-lambda-imports.py package/
echo "✓ Test script copied"

# Copy config file (SRE platform specific)
echo "Copying incident config..."
cp incident_config.json package/
echo "✓ Config copied"

# Show package size
PACKAGE_SIZE=$(du -sh package | cut -f1)
echo ""
echo "✅ Package built successfully"
echo "   Size: $PACKAGE_SIZE"
echo ""
echo "Next step: Run validation"
echo "  ./scripts/pre-deploy-validation.sh $LAMBDA_NAME"
