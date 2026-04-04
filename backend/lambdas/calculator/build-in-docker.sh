#!/bin/bash
# Build Lambda package inside Docker to ensure compatibility

set -e

echo "Building Lambda package in Docker..."

docker run --rm \
  --entrypoint bash \
  -v "$(pwd):/workspace" \
  -w /workspace \
  public.ecr.aws/lambda/python:3.12 \
  -c "
    pip install -r requirements.txt -t package/ --upgrade
    cp -r src package/
    cp -r ../../lambda-layer/python/shared package/
    echo 'Package built successfully'
  "

echo "✓ Package built in Docker"
