# =============================================================================
# sre-platform Lambda — CI Test Image
#
# PURPOSE: Provides a reproducible environment for running pytest in CI.
#          Deployment uses ZIP packages, NOT this image.
#
# This Lambda contains three handlers (detection, triage, escalation).
# The specific handler is configured via CDK/Terraform at deploy time,
# not via docker CMD.
#
# BUILD from project root:
#   docker build -f backend/lambdas/sre-platform/Dockerfile \
#     -t lambda-sre-platform-ci .
# =============================================================================
FROM public.ecr.aws/lambda/python:3.12

# ── Dependencies ──────────────────────────────────────────────────────────────
COPY backend/lambdas/sre-platform/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# ── Shared Lambda layer ───────────────────────────────────────────────────────
# Mirrors the Lambda Layer attached in AWS so 'from shared.*' imports work.
COPY backend/lambda-layer/python/ ${LAMBDA_TASK_ROOT}/

# ── Application source ────────────────────────────────────────────────────────
COPY backend/lambdas/sre-platform/src/ ${LAMBDA_TASK_ROOT}/src/
COPY backend/lambdas/sre-platform/incident_config.json ${LAMBDA_TASK_ROOT}/

# ── Tests (copied so pytest can be run inside the container) ──────────────────
COPY backend/lambdas/sre-platform/tests/ ${LAMBDA_TASK_ROOT}/tests/
COPY backend/lambdas/sre-platform/conftest.py ${LAMBDA_TASK_ROOT}/

# ── Default handler — detection (override per Lambda function in AWS) ─────────
CMD ["src.handlers.detection_handler.lambda_handler"]
