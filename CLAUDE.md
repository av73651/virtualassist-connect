# Repository Operating Manual for AI Development

## Project Overview

**virtualassist-connect** is an AI-powered virtual assistant platform built on AWS serverless technologies. It follows a structured 6-phase SDLC with mandatory approval gates, enterprise observability, and clean hexagonal architecture.

**Tech Stack**: Python 3.12 | AWS Lambda | AWS CDK | API Gateway | DynamoDB | Cognito | OpenTelemetry | Pydantic | Amazon Bedrock (Claude)

---

# 1. Core Principles

1. Never commit directly to the `main` branch.
2. All work must occur in feature or fix branches.
3. Commit history must be readable and meaningful.
4. Code must always build successfully.
5. Secrets, credentials, and environment files must never be committed.
6. Follow the SDLC workflow: Requirements → Design (approval gate) → Implementation → Final Review.
7. All code must conform to the platform architecture defined in `skills/definitions/technology-standards.md`.

---

# 2. Standard Git Workflow

Before starting work:

```
git pull origin main
```

Create a branch:

```
git checkout -b <type>/<short-description>
```

Branch naming convention:

```
feature/policy-retrieval-api
feature/bedrock-integration
bugfix/session-timeout
refactor/prompt-builder
```

During development, make small commits with logical changes:

```
git add <specific-files>
git commit -m "feat: add policy retrieval API"
```

Push and open a Pull Request:

```
git push origin <branch-name>
```

---

# 3. Commit Message Standard (Conventional Commits)

Format:

```
<type>: <short description>
```

Allowed types:

| Type       | Usage                                    |
|------------|------------------------------------------|
| `feat`     | New functionality                        |
| `fix`      | Bug fix                                  |
| `refactor` | Code improvement without behavior change |
| `docs`     | Documentation changes                    |
| `test`     | Tests added or modified                  |
| `chore`    | Maintenance tasks                        |
| `infra`    | CDK / infrastructure changes             |

Good examples:

```
feat: add policy retrieval Lambda handler
fix: resolve DynamoDB pagination bug in policy repository
refactor: simplify prompt template builder service
infra: add CloudWatch alarms for policy Lambda
test: add unit tests for policy service layer
```

Bad examples (not allowed):

```
update
changes
fix stuff
final code
```

---

# 4. Safe Git Rules

AI agents must NEVER run destructive commands unless explicitly instructed by a human:

```
git reset --hard
git push --force
git rebase -i main
```

If history modification is required, request human approval first.

---

# 5. Pull Request Rules

Every change must be merged through a Pull Request.

PR description must include:

```
## Summary
<what was done and why>

## Changes
- <list of files/modules modified>

## Testing
- <what was tested and results>
- Coverage: X%

## Architecture Impact
- <any changes to layers, patterns, or infrastructure>
```

---

# 6. Repository Architecture

## Directory Structure

```
backend/
    lambdas/
        <service-name>/
            src/
                domain/          # Pure business logic, domain objects
                dto/             # Pydantic request/response models
                handlers/        # Lambda entry points (thin)
                services/        # Business logic orchestration
                repositories/    # Data access (DynamoDB, S3)
            tests/
                unit/            # Unit tests per layer
                integration/     # API flow tests
            requirements.txt
    shared/
        middleware/
            api_gateway.py       # @api_gateway_handler decorator
            observability.py     # @observe decorator (tracing, metrics, logging)
        config/
            logging_config.py    # Structured JSON logging setup

frontend/                        # Angular application

infra/
    app.py                       # CDK app entry point
    config.json                  # Environment configs (dev/prod)
    stacks/                      # CDK stack definitions

docs/
    specs/
        <service-name>/          # Per-service specifications
            requirements.md
            app-design.md
            infra-design.md
            implementation-plan.md
            test-plan.md
            reviews/             # Review reports per gate

skills/
    definitions/                 # AI skill definitions (13 skills)
    patterns/                    # Architectural patterns and standards

tasks/
    backlog/                     # Task tracking
```

## Layer Rules

| Layer        | Responsibility                          | Dependencies Allowed            |
|--------------|----------------------------------------|--------------------------------|
| `handlers/`  | Parse API Gateway events, validate DTOs, format responses | services, dto |
| `services/`  | Business logic orchestration           | domain, repositories           |
| `domain/`    | Pure domain objects, business rules    | None (no external deps)        |
| `dto/`       | Pydantic request/response validation   | None                           |
| `repositories/` | Data access (DynamoDB, S3)          | domain                         |

**Key rules:**
- Business logic must live in `services/`, never in handlers
- Handlers must remain thin -- parse, delegate, respond
- Database access must go through repository classes
- Domain objects must have no external dependencies
- Prompts for LLM/Bedrock must be stored in `prompts/` directory

## Shared Middleware

All Lambda handlers must use the shared decorators:

- `@api_gateway_handler` -- wraps HTTP handling, error conversion, response formatting
- `@observe` -- AOP decorator for distributed tracing, metrics (counter + histogram), structured logging

---

# 7. Approved Technology Stack

Only use technologies approved in `skills/definitions/technology-standards.md`:

| Category      | Approved Technology                              |
|---------------|--------------------------------------------------|
| Compute       | AWS Lambda (Python 3.12)                         |
| API           | API Gateway (REST)                               |
| Data          | DynamoDB, S3                                     |
| Messaging     | EventBridge, SQS                                 |
| AI/ML         | Amazon Bedrock (Claude)                          |
| Observability | OpenTelemetry, CloudWatch, X-Ray                 |
| IaC           | AWS CDK (Python)                                 |
| Auth          | Cognito, IAM, Secrets Manager                    |
| Validation    | Pydantic 2.x                                     |
| Testing       | pytest, moto (AWS mocking)                       |

Do not introduce unapproved technologies without human approval.

---

# 8. SDLC Workflow and Approval Gates

All feature work follows a streamlined workflow with two approval gates.

## Phases

| Phase | Description | Gate |
|-------|-------------|------|
| 1. Requirements | Analyze requirements, define acceptance criteria | Requirements Review |
| 2. Design | App design, infra design, architecture decisions | **Design Review (CRITICAL)** |
| 3. Implementation | Execute task categories below autonomously | Final Review |

**Gate protocol**: Complete work -> Present summary to developer -> STOP -> Wait for explicit "approved" before proceeding.

## Post-Design Task Categories

After design approval, work is organized into these task categories executed sequentially:

| # | Category | Scope | Examples |
|---|----------|-------|---------|
| 1 | **Application Development** | Domain, services, handlers, DTOs | Factory methods, service methods, routing, middleware changes |
| 2 | **Unit Testing** | Tests per layer with coverage target | test_domain.py, test_services.py, test_handlers.py, test_dto.py |
| 3 | **Infrastructure Development** | CDK stacks, API Gateway, IAM, CloudWatch | New routes, alarms, dashboard widgets, Lambda config |
| 4 | **Integration Testing** | End-to-end API tests against deployed infra | test_api_integration.py with real endpoints |
| 5 | **Deployment & Verification** | Package, deploy, smoke test in AWS | Lambda packaging, `cdk deploy`, endpoint verification |
| 6 | **Documentation** | Traceability, review reports | Update traceability matrix, implementation report |

AI proceeds through all task categories autonomously after design approval. No intermediate gates between categories.

---

# 9. Security Rules

Never commit:

- `.env`, `.env.local`
- AWS credentials or API keys
- Tokens or private certificates
- `cdk.context.json` with account details

The `.gitignore` must block these files. Verify before every commit.

---

# 10. Testing Requirements

**Framework**: pytest 7.4.3 with pytest-cov, pytest-mock, moto

**Coverage target**: 80% minimum per Lambda

**Test structure per Lambda**:

```
tests/
    unit/
        test_domain.py
        test_services.py
        test_handlers.py
        test_dto.py
    integration/
        test_api.py
    conftest.py              # Shared fixtures
```

Before committing, ensure:

- All tests pass (`pytest`)
- Coverage meets 80% threshold
- No secrets in committed files
- Lint checks pass

---

# 11. Observability Requirements

All services must implement:

- **Tracing**: OpenTelemetry spans via `@observe` decorator
- **Metrics**: Request counters and duration histograms (automatic via `@observe`)
- **Logging**: Structured JSON logging via `shared/config/logging_config.py`
- **Infrastructure**: CloudWatch dashboards and alarms in CDK stacks
- **Context propagation**: X-Ray trace IDs via ADOT Lambda Layer

Never log secrets, tokens, or PII.

---

# 12. CDK Infrastructure Standards

Each Lambda service gets its own CDK stack in `infra/stacks/`:

- Lambda function with environment-specific config from `infra/config.json`
- API Gateway REST API with Cognito authorizer
- WAF rules for API protection
- CloudWatch dashboard and alarms
- IAM roles following least-privilege principle

Shared resources (Cognito) live in `infra/stacks/auth_stack.py`.

---

# 13. AI Agent Task Execution Workflow

When implementing a new service or feature, follow this sequence:

1. Pull latest: `git pull origin main`
2. Create branch: `git checkout -b feature/<service-name>`
3. **Requirements**: Analyze and define acceptance criteria → present for approval
4. **Design**: App design + infra design → present for approval (CRITICAL GATE)
5. **Implementation** (autonomous after design approval):
   - Application development (domain → services → handlers → DTOs)
   - Unit testing (all layers, 80%+ coverage)
   - Infrastructure development (CDK stack changes)
   - Integration testing
   - Deploy to dev and verify (`cdk deploy`, smoke tests)
   - Documentation (traceability, review report)
6. Present final review → commit, push, create PR

---

# 14. Code Quality Expectations

AI-generated code must:

- Follow the hexagonal layer architecture strictly
- Use Pydantic DTOs for all request/response validation
- Apply `@api_gateway_handler` and `@observe` decorators
- Use frozen dataclasses for domain objects
- Use factory methods for domain object creation
- Include structured logging (no print statements)
- Include error handling with proper HTTP status codes
- Follow existing patterns in `hello-world` and `calculator` Lambdas as reference implementations

---

# 15. When AI Is Unsure

If architectural uncertainty exists:

1. Do not guess.
2. Reference `skills/patterns/` for established patterns.
3. Reference existing implementations (`hello-world`, `calculator`) for examples.
4. If still unclear, provide multiple design options and ask for human approval.

---

# 16. Key Reference Paths

| What | Where |
|------|-------|
| SDLC workflow phases | `docs/workflows/01-06` |
| Approval gates | `WORKFLOW-GATES.md` |
| Technology standards | `skills/definitions/technology-standards.md` |
| Architectural patterns | `skills/patterns/` |
| AI skill definitions | `skills/definitions/` |
| Reference Lambda (simple) | `backend/lambdas/hello-world/` |
| Reference Lambda (with logic) | `backend/lambdas/calculator/` |
| Shared middleware | `backend/shared/middleware/` |
| CDK infra config | `infra/config.json` |
| Environment template | `.env.example` |
