# =============================================================================
# calculator Lambda — CI Test Image
#
# PURPOSE: Provides a reproducible environment for running pytest in CI.
#          Deployment uses ZIP packages, NOT this image.
#
# BUILD from project root:
#   docker build -f backend/lambdas/calculator/Dockerfile \
#     -t lambda-calculator-ci .
# =============================================================================
FROM public.ecr.aws/lambda/python:3.12

# ── Dependencies ──────────────────────────────────────────────────────────────
COPY backend/lambdas/calculator/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# ── Shared Lambda layer ───────────────────────────────────────────────────────
# Mirrors the Lambda Layer attached in AWS so 'from shared.*' imports work.
COPY backend/lambda-layer/python/ ${LAMBDA_TASK_ROOT}/

# ── Application source ────────────────────────────────────────────────────────
COPY backend/lambdas/calculator/src/ ${LAMBDA_TASK_ROOT}/src/

# ── Tests (copied so pytest can be run inside the container) ──────────────────
COPY backend/lambdas/calculator/tests/ ${LAMBDA_TASK_ROOT}/tests/
COPY backend/lambdas/calculator/pytest.ini ${LAMBDA_TASK_ROOT}/

# ── Default handler (overridden in CI to run pytest) ─────────────────────────
CMD ["src.handlers.calculator_handler.lambda_handler"]
