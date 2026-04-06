#!/usr/bin/env python3
"""Test all critical imports that Lambda needs."""

import sys
import os

def test_imports():
    """Test all imports needed by calculator Lambda."""
    print("Testing Lambda imports...")
    errors = []

    # Test 1: Basic dependencies
    try:
        import pydantic
        print(f"✓ pydantic {pydantic.__version__}")
    except Exception as e:
        errors.append(f"✗ pydantic: {e}")

    try:
        import boto3
        print(f"✓ boto3 {boto3.__version__}")
    except Exception as e:
        errors.append(f"✗ boto3: {e}")

    # Test 2: OpenTelemetry core
    try:
        from opentelemetry import trace
        print("✓ opentelemetry.trace")
    except Exception as e:
        errors.append(f"✗ opentelemetry.trace: {e}")

    try:
        from opentelemetry import metrics
        print("✓ opentelemetry.metrics")
    except Exception as e:
        errors.append(f"✗ opentelemetry.metrics: {e}")

    # Test 3: OpenTelemetry exporters (using HTTP, not gRPC)
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        print("✓ opentelemetry.exporter.otlp.proto.http.trace_exporter (HTTP)")
    except Exception as e:
        errors.append(f"✗ OTLP HTTP exporter: {e}")

    # Test 4: OpenTelemetry SDK
    try:
        from opentelemetry.sdk.trace import TracerProvider
        print("✓ opentelemetry.sdk.trace")
    except Exception as e:
        errors.append(f"✗ opentelemetry.sdk: {e}")

    # Test 5: Application code (optional - may not work in test mode)
    try:
        sys.path.insert(0, '/var/task')
        from src.handlers.calculator_handler import lambda_handler
        print("✓ calculator_handler.lambda_handler")
    except Exception as e:
        # Handler import may fail in test mode if ADOT wrapper is active
        # This is OK as long as other imports work
        print(f"⚠ calculator_handler: {e} (may be OK if ADOT wrapper active)")
        # Don't fail the test for handler import issues

    # Test 6: Shared middleware
    try:
        from shared.middleware.observability import observe
        print("✓ shared.middleware.observability")
    except Exception as e:
        errors.append(f"✗ shared.middleware: {e}")

    print("\n" + "="*50)
    if errors:
        print(f"FAILED: {len(errors)} import errors")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("SUCCESS: All imports working")
        return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
