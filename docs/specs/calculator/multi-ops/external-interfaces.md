# Calculator Multi-Operator Enhancement - External Interfaces

**Date**: 2026-03-28

---

### IF-001: Subtraction API Endpoint
**Type**: Software
**Description**: API Consumer sends subtraction requests
**Source/Target**: API Consumer -> Calculator Lambda
**Data**: JSON request `{"a": float, "b": float}` -> JSON response `{a, b, operation, result, timestamp}`
**Protocol**: HTTPS POST /calculator/subtract

### IF-002: Multiplication API Endpoint
**Type**: Software
**Description**: API Consumer sends multiplication requests
**Source/Target**: API Consumer -> Calculator Lambda
**Data**: JSON request `{"a": float, "b": float}` -> JSON response `{a, b, operation, result, timestamp}`
**Protocol**: HTTPS POST /calculator/multiply

### IF-003: Division API Endpoint
**Type**: Software
**Description**: API Consumer sends division requests
**Source/Target**: API Consumer -> Calculator Lambda
**Data**: JSON request `{"a": float, "b": float}` -> JSON response `{a, b, operation, result, timestamp}`
**Protocol**: HTTPS POST /calculator/divide

### IF-004: Observability Pipeline (Unchanged)
**Type**: Software
**Description**: All new operations emit traces, metrics, and logs
**Source/Target**: Calculator Lambda -> CloudWatch / X-Ray
**Data**: OpenTelemetry spans, counters, histograms, structured JSON logs
**Protocol**: OTLP via ADOT Lambda Layer
