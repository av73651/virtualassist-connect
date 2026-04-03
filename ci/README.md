# CI/CD Pipeline — Docker + ZIP Strategy

## Overview

This project uses **Docker for reproducible CI, and ZIP packages for Lambda deployment**.

```
┌─────────────────────────────────────────────────────────────────┐
│  Jenkins Pipeline                                               │
│                                                                 │
│  Checkout → Build CI Images → Lint → Test → Package ZIP → Archive │
│                                                                 │
│  Docker used for:  Test isolation (reproducible environment)    │
│  ZIP used for:     Actual Lambda deployment in AWS              │
└─────────────────────────────────────────────────────────────────┘
```

## Why Docker for CI, ZIP for Deployment?

| | Docker Image | ZIP Package |
|---|---|---|
| **Lambda cold start** | ~400–800ms extra | ✅ Fastest |
| **Max size** | 10 GB | 250 MB (enough for us) |
| **Reproducible test env** | ✅ Yes | No |
| **Registry needed** | Yes (ECR) | ❌ No |
| **Our choice** | CI only | ✅ Deployment |

## Lambda Functions

| Lambda | Dockerfile | Handlers |
|---|---|---|
| `hello-world` | `backend/lambdas/hello-world/Dockerfile` | `hello_handler` |
| `calculator` | `backend/lambdas/calculator/Dockerfile` | `calculator_handler` |
| `sre-platform` | `backend/lambdas/sre-platform/Dockerfile` | `detection_handler`, `triage_handler`, `escalation_handler` |

## Shared Lambda Layer

The shared utilities (`shared/`) live in `backend/lambda-layer/python/shared/`.

- In **AWS**: attached as a Lambda Layer (configured in CDK/Terraform).
- In **Docker CI**: copied directly into the image via the Dockerfile.
- In **local tests**: `conftest.py` adds the path to `sys.path` automatically.

All three environments resolve `from shared.*` the same way.

## Building Images Locally

All images must be built from the **project root** (not from inside the Lambda directory):

```bash
# From the repository root
docker build -f backend/lambdas/hello-world/Dockerfile   -t lambda-hello-world-ci   .
docker build -f backend/lambdas/calculator/Dockerfile    -t lambda-calculator-ci    .
docker build -f backend/lambdas/sre-platform/Dockerfile  -t lambda-sre-platform-ci  .
```

## Running Tests Locally via Docker

```bash
# Run calculator tests in Docker (mirrors what Jenkins does)
docker run --rm \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID=test \
  -e AWS_SECRET_ACCESS_KEY=test \
  lambda-calculator-ci \
  bash -c "cd \${LAMBDA_TASK_ROOT} && pytest tests/ -m 'not integration'"
```

## Pipeline Stages

| Stage | What it does |
|---|---|
| **Checkout** | Pull source code |
| **Build CI Images** | `docker build` each Lambda from project root |
| **Lint** | `flake8 src/` inside container (max-line-length 120) |
| **Test** | `pytest` inside container, JUnit XML + coverage XML exported |
| **Package ZIP** | Create `dist/<lambda>/<lambda>-<build>.zip` (src + shared layer) |
| **Archive Artifacts** | Store ZIPs in Jenkins for downstream deployment stages |

## Adding a New Lambda

1. Create `backend/lambdas/<name>/Dockerfile` following the same pattern.
2. Add `<name>` to the `LAMBDAS` environment variable in `Jenkinsfile`.
3. That's it — the pipeline is data-driven.
