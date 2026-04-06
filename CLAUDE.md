# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**VirtualAssist Connect** is an AWS serverless platform using a micro-Lambda architecture with strict clean architecture principles. The project follows a gated AI-driven development workflow with mandatory approval gates at each stage.

## Critical: Workflow Approval Gates

⚠️ **MANDATORY**: This project uses 6 approval gates defined in `WORKFLOW-GATES.md`. You MUST:
1. Complete each stage's work
2. Generate the review report
3. Present the report
4. **STOP and WAIT** for explicit developer approval
5. Only proceed after receiving "approved" or similar confirmation

Never skip gates or proceed automatically to the next stage. See `WORKFLOW-GATES.md` for complete gate protocol.

## Architecture

### Layer Architecture (Mandatory)

All Lambda functions follow **hexagonal/clean architecture** with strict layer separation:

```
Request → Handler → Service → Repository → Database
            ↓          ↓           ↓
          DTO     Domain Model  DB Model
```

**Layer Responsibilities**:
- **Handlers** (`src/handlers/`): Parse requests, route, format responses. NO business logic.
- **Services** (`src/services/`): Business logic ONLY. No HTTP/DB parsing.
- **Repositories** (`src/repositories/`): Data access ONLY.
- **Domain** (`src/domain/`): Business entities and domain logic.
- **DTOs** (`src/dto/`): Request/response schemas using Pydantic.

**Shared Code** (`backend/lambda-layer/python/shared/`):
- `middleware/`: AOP decorators (`@api_gateway_handler`, `@observe`, `@require_auth`)
- `config/`: Logging configuration, AWS clients
- `exceptions/`: Custom business exceptions

See `skills/patterns/layer-architecture.md` for complete specifications.

### Technology Stack

**Approved technologies** (defined in `skills/definitions/technology-standards.md`):
- **Compute**: AWS Lambda (Python 3.12)
- **API**: API Gateway (REST)
- **Data**: DynamoDB, S3
- **Events**: EventBridge, SQS
- **AI**: Amazon Bedrock (Claude models)
- **Observability**: OpenTelemetry (ADOT Lambda Layer), CloudWatch, X-Ray
- **IaC**: AWS CDK (Python)
- **Security**: Cognito, IAM, Secrets Manager

## Project Structure

```
virtualassist-connect/
├── backend/
│   ├── lambda-layer/python/shared/    # Shared middleware & utilities
│   │   ├── middleware/                # @api_gateway_handler, @observe decorators
│   │   ├── config/                    # Logging, AWS clients
│   │   └── exceptions/                # Custom exceptions
│   └── lambdas/                       # Individual Lambda functions
│       ├── hello-world/
│       ├── calculator/
│       └── sre-platform/
│           └── src/
│               ├── handlers/          # Entry points only
│               ├── services/          # Business logic
│               ├── repositories/      # Data access
│               ├── domain/            # Business entities
│               └── dto/               # Request/response schemas
├── infra/                             # AWS CDK infrastructure
│   ├── app.py                         # CDK entry point
│   ├── stacks/                        # CDK stack definitions
│   │   ├── auth_stack.py
│   │   ├── hello_world_stack.py
│   │   ├── calculator_stack.py
│   │   └── sre_platform_stack.py
│   └── config.json                    # Environment configs (dev/staging/prod)
├── skills/                            # AI skill definitions & patterns
│   ├── definitions/                   # Actionable AI skills
│   │   ├── requirements-analysis.md
│   │   ├── technology-standards.md
│   │   ├── system-design.md
│   │   ├── code-generation-app.md
│   │   ├── code-generation-cdk.md
│   │   ├── code-review.md
│   │   ├── test-generation.md
│   │   └── documentation-generation.md
│   └── patterns/                      # Architectural patterns
│       ├── layer-architecture.md
│       ├── api-routing-strategy.md
│       ├── opentelemetry-template.md
│       ├── iam-least-privilege.md
│       └── observability-requirements.md
├── docs/
│   ├── specs/{service}/               # Requirements & design per service
│   │   ├── {service}-requirements.md
│   │   ├── {service}-app-design.md
│   │   ├── {service}-infra-design.md
│   │   ├── implementation-plan.md
│   │   └── reviews/                   # Generated review reports
│   └── workflows/                     # Development process phases
├── tasks/                             # Task breakdown and backlog
├── scripts/                           # Utility scripts
├── ci/                                # CI/CD documentation
├── Jenkinsfile                        # Jenkins CI pipeline
└── WORKFLOW-GATES.md                  # CRITICAL: Approval gate protocol
```

## Deployment

### Jenkins Pipeline Trigger

**Trigger Jenkins build from command line:**
```bash
# Trigger build for current branch
./scripts/jenkins-trigger.sh

# Trigger build for specific branch
./scripts/jenkins-trigger.sh feature/calculator-enhancements
```

**Setup Jenkins credentials** (one-time):
```bash
# Create credentials file
cat > ~/.jenkins-credentials << EOF
JENKINS_URL=http://your-jenkins-url:8080
JENKINS_USER=your-username
JENKINS_TOKEN=your-api-token
EOF
```

### CDK Deployment Script

**Deploy using automated script:**
```bash
# Deploy all stacks to dev
./scripts/deploy.sh dev

# Deploy specific Lambda to dev
./scripts/deploy.sh dev calculator

# Deploy to production (requires confirmation)
./scripts/deploy.sh prod
```

**Script features:**
- ✅ Validates prerequisites (AWS CLI, CDK, credentials)
- ✅ Checks/rebuilds Lambda packages if needed
- ✅ Shows CDK diff before deployment
- ✅ Requires explicit confirmation for prod
- ✅ Post-deployment validation
- ✅ Deployment summary with next steps

### Manual CDK Deployment

```bash
cd infra
cdk deploy --all --context env=dev       # Deploy all to dev
cdk deploy CalculatorStack-dev --context env=dev  # Deploy specific stack
cdk diff --all --context env=dev         # Preview changes
```

## Common Development Tasks

### Running Tests

**Per Lambda** (from Lambda directory):
```bash
cd backend/lambdas/calculator
pytest tests/                          # All tests
pytest tests/unit/                     # Unit tests only
pytest tests/integration/              # Integration tests only
pytest --cov=src --cov-report=html     # With coverage
pytest tests/unit/test_calculator_service.py  # Single test file
```

**Requirements**:
- Minimum 80% code coverage (enforced by `pytest.ini`)
- Tests must trace to acceptance criteria (e.g., `test_user_creation_ac_001`)

**Markers**:
- `@pytest.mark.integration`: Requires `API_ENDPOINT` env var

### Running Linter

```bash
cd backend/lambdas/calculator
flake8 src/
```

**Config**: `.flake8` at project root (max-line-length: 120)

### Building Docker Images (CI)

All Docker builds MUST run from **project root**:
```bash
# From repository root
docker build -f backend/lambdas/hello-world/Dockerfile -t lambda-hello-world-ci .
docker build -f backend/lambdas/calculator/Dockerfile -t lambda-calculator-ci .
docker build -f backend/lambdas/sre-platform/Dockerfile -t lambda-sre-platform-ci .
```

**Run tests in Docker** (mirrors Jenkins):
```bash
docker run --rm \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID=test \
  -e AWS_SECRET_ACCESS_KEY=test \
  lambda-calculator-ci \
  bash -c "cd \${LAMBDA_TASK_ROOT} && pytest tests/ -m 'not integration'"
```

### CDK Deployment

**Deploy infrastructure**:
```bash
cd infra
cdk deploy --context env=dev       # Deploy to dev
cdk deploy --context env=staging   # Deploy to staging
cdk diff --context env=dev         # Show changes before deploy
cdk synth --context env=dev        # Generate CloudFormation
```

**Environment configs**: `infra/config.json` (dev/staging/prod)

## Development Workflow

The project follows a **6-stage gated workflow**:

1. **Requirements Analysis** (`/requirements-analysis`)
   - Generate `docs/specs/{service}/{service}-requirements.md`
   - Gate 1: Requirements Review → WAIT for approval

2. **System Design** (`/system-design`)
   - Generate app design, infra design, implementation plan
   - Gate 2: Design Review → WAIT for approval (MOST CRITICAL)

3. **Task Breakdown** (`/task-elaboration`)
   - Create task files in `tasks/backlog/`
   - Gate 3: Task Review → WAIT for approval

4. **Implementation** (per task)
   - Generate code following layer architecture
   - Run code review
   - Generate tests (≥80% coverage)
   - Run test review
   - Gate 4: Code + Test Review (per task) → WAIT for approval

5. **Integration Testing**
   - Deploy to dev/staging
   - Run integration tests
   - Gate 5: Integration Review → WAIT for approval

6. **Documentation**
   - Generate API docs, deployment guides, runbooks
   - Gate 6: Documentation Review → WAIT for approval

**See**: `docs/workflows/` for detailed phase instructions.

## AI Skills

This project defines AI skills in `skills/`:

**Available Skills** (use with `/` prefix):
- `/requirements-analysis`: Extract requirements from natural language
- `/system-design`: Create app/infra design from requirements
- `/code-generation-app`: Generate Lambda handlers/services/DTOs
- `/code-generation-cdk`: Generate CDK infrastructure stacks
- `/code-review`: Review code for architecture/security/observability compliance
- `/test-generation`: Generate comprehensive test suites
- `/documentation-generation`: Generate code-derived documentation
- `/deployment`: Manage deployments via Jenkins or CDK (see `skills/definitions/deployment.md`)

**Key Patterns**:
- `layer-architecture.md`: Mandatory clean architecture structure
- `api-routing-strategy.md`: Micro-Lambda REST routing (one Lambda per route)
- `opentelemetry-template.md`: Native OpenTelemetry instrumentation
- `observability-requirements.md`: Logging, metrics, tracing standards
- `iam-least-privilege.md`: IAM policy patterns

## Key Architectural Constraints

1. **No Business Logic in Handlers**: Handlers only parse, route, and format responses
2. **Mandatory Observability**: Every Lambda must include OpenTelemetry tracing via `@observe` decorator
3. **Structured Logging**: Use `logging_config.py` with trace_id injection
4. **Error Handling via AOP**: Use decorators; no try/catch in handlers
5. **Micro-Lambda Pattern**: One Lambda function per API endpoint
6. **Least-Privilege IAM**: Generate specific IAM policies per Lambda (no wildcards)
7. **No Hardcoded Secrets**: All secrets via Secrets Manager/SSM Parameter Store
8. **Test Coverage ≥ 80%**: Enforced by pytest configuration

## CI/CD Pipeline (Jenkins)

**Strategy**: Docker for reproducible CI, ZIP packages for deployment

**Pipeline Stages**:
1. Checkout
2. Build CI Images (parallel, from project root)
3. Lint (flake8)
4. Test (pytest with coverage)
5. Package ZIP (src + shared layer)
6. Archive artifacts

**Adding New Lambda**:
1. Create `backend/lambdas/{name}/Dockerfile`
2. Add `{name}` to `LAMBDAS` variable in `Jenkinsfile`
3. Pipeline auto-discovers and processes it

**See**: `ci/README.md` for CI/CD details.

## PR Requirements

All PRs must satisfy checklist in `.github/PULL_REQUEST_TEMPLATE.md`:

- [ ] Read `technology-standards.md` constraints
- [ ] Feature satisfies documented Acceptance Criteria
- [ ] Used Micro-Lambda routing pattern
- [ ] Handler contains zero business logic
- [ ] Service layer contains zero HTTP/API Gateway/Database parsing
- [ ] OpenTelemetry `trace_id` extracted and injected into logs
- [ ] No hardcoded secrets
- [ ] ≥80% test coverage
- [ ] Tests trace back to ACs (e.g., `test_user_creation_ac_001`)
- [ ] Code passed through `/code-review` skill

## Environment Variables

**Local Testing**:
- `AWS_DEFAULT_REGION=us-east-1`
- `AWS_ACCESS_KEY_ID=test` (for moto)
- `AWS_SECRET_ACCESS_KEY=test` (for moto)

**Integration Tests**:
- `API_ENDPOINT`: API Gateway endpoint URL

## Dependencies

**Per Lambda** (`requirements.txt`):
- `pydantic>=2.6.0`: DTO validation
- `opentelemetry-api`, `opentelemetry-sdk`: Observability
- `opentelemetry-instrumentation`, `opentelemetry-exporter-otlp`: OTLP export
- `opentelemetry-sdk-extension-aws`: X-Ray integration
- `pytest`, `pytest-cov`, `pytest-mock`: Testing
- `moto[dynamodb,s3]`: AWS mocking

**Infrastructure** (`infra/requirements.txt`):
- `aws-cdk-lib==2.133.0`
- `constructs>=10.0.0,<11.0.0`

## Special Notes

1. **Shared Layer Import**: All Lambdas import shared code as `from shared.middleware import ...`
   - In AWS: Attached as Lambda Layer
   - In Docker CI: Copied directly into image
   - In local tests: Added to `sys.path` via `conftest.py`

2. **Design vs Architecture**:
   - Platform **architecture** is defined ONCE in `skills/patterns/`
   - Service **design** is created per service in `docs/specs/{service}/`
   - Never create `architecture.md` at service level

3. **No Speculation in Documentation**: Document only what exists in code/config/infra

4. **Incident Simulation**: `scripts/incident/simulations/` contains error injection scripts for SRE testing

## Quick Start for New Features

1. Start with `/requirements-analysis` skill to generate requirements
2. Run `/system-design` skill to create app/infra design and implementation plan
3. **WAIT** for design approval (Gate 2) - DO NOT proceed without explicit approval
4. Generate tasks for implementation
5. For each task:
   - Generate code using `/code-generation-app`
   - Run `/code-review`
   - Generate tests using `/test-generation`
   - Run `/test-review`
   - Execute tests: `pytest --cov=src --cov-fail-under=80`
   - **WAIT** for approval before next task
6. Generate CDK infrastructure using `/code-generation-cdk`
7. Deploy: `cd infra && cdk deploy --context env=dev`
8. Run integration tests
9. Generate documentation using `/documentation-generation`

Remember: **STOP at each gate and WAIT for explicit approval** before proceeding.
