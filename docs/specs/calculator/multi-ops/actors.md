# Calculator Multi-Operator Enhancement - Actors

**Date**: 2026-03-28

---

### Actor: API Consumer
**Type**: External System
**Interaction**: Sends HTTP POST requests to /calculator/{operation} endpoints with JSON payload containing two operands

### Actor: AWS API Gateway
**Type**: AWS Service
**Interaction**: Receives HTTP requests, routes to Lambda function based on resource path, returns responses

### Actor: AWS Lambda
**Type**: AWS Service
**Interaction**: Executes calculation logic for the requested operation, returns results

### Actor: CloudWatch
**Type**: AWS Service
**Interaction**: Receives logs, metrics, and traces for observability across all operations
