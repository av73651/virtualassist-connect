# Phase 2: Design & Architecture

## Objective
Create comprehensive technical design and architecture for the system based on validated requirements.

## Process

### 1. System Architecture
- Define high-level architecture following `skills/definitions/technology-standards.md`
- AWS serverless-first: Lambda, API Gateway, DynamoDB, S3, EventBridge, SQS
- Clean/Hexagonal Architecture with strict layer separation
- Design data flow and integration points (HTTPS REST, EventBridge, SQS)

### 2. Component Design

**Backend Design:**
- Lambda function structure: handlers -> services -> repositories -> domain -> DTOs
- API Gateway endpoints and methods
- DynamoDB single-table design (PK/SK, GSIs, access patterns)
- External service integrations
- Error handling strategy (see `skills/patterns/error-response-format.md`)

**Frontend Design:**
- Angular application structure
- Component hierarchy
- State management approach
- Routing design
- UI/UX wireframes

**Infrastructure Design:**
- CDK stack organization (see `skills/definitions/code-generation-cdk.md`)
- Resource naming conventions
- Environment strategy (dev, prod)
- IAM roles and permissions (see `skills/patterns/iam-least-privilege.md`)
- Observability: OpenTelemetry via ADOT Lambda Layer (see `skills/patterns/opentelemetry-template.md`)

### 3. API Design
- RESTful endpoints specification
- Request/response formats using Pydantic DTOs
- Authentication: Cognito User Pool authorizer on all API Gateway endpoints
- Error response standards (see `skills/patterns/error-response-format.md`)
- Rate limiting via WAF WebACL + API Gateway throttling

### 4. Data Design
- DynamoDB single-table design with access patterns (see `skills/patterns/dynamodb-configuration.md`)
- S3 for object storage
- KMS encryption for enterprise compliance
- Data validation rules via Pydantic models

### 5. Security Design
- Authentication: AWS Cognito User Pool (mandatory on all endpoints)
- Authorization: Cognito groups + IAM least privilege
- Secrets management: AWS Secrets Manager / SSM Parameter Store
- Data encryption: KMS at rest, TLS in transit
- WAF with AWS Managed Rules

### 6. Shift-Left Test Planning
- Generate initial `docs/specs/{service-name}/test-plan.md` from acceptance criteria
- Map each acceptance criterion to planned test cases (traceability matrix)
- Identify test fixtures and data needed
- See `skills/definitions/test-generation.md` §1 (Shift-Left Test Strategy)

## Documentation

Location: `docs/specs/{service-name}/`

Required documents:
- `design.md` — Service-specific design (NOT platform architecture)
- `api-design.md` — Complete API specification
- `data-models.md` — DynamoDB table design, access patterns, GSIs
- `security-design.md` — Security design
- `implementation-plan.md` — File-by-file implementation blueprint
- `test-plan.md` — Shift-left test plan with traceability matrix

**Important**: Platform architecture is defined in `skills/definitions/technology-standards.md` and `skills/patterns/`. Service design documents how THIS service implements those standards.

## AI Skills Used

| Skill | File | Purpose |
|-------|------|---------|
| System Design | `skills/definitions/system-design.md` | Generate architecture and component designs |
| Technology Standards | `skills/definitions/technology-standards.md` | Enforce approved technology stack |
| Design Review | `skills/definitions/design-review.md` | Validate design against best practices |
| Test Generation | `skills/definitions/test-generation.md` | Generate shift-left test plan from acceptance criteria |

## Patterns Referenced
- `skills/patterns/layer-architecture.md` — Clean Architecture layer separation
- `skills/patterns/api-routing-strategy.md` — API Gateway routing patterns
- `skills/patterns/dynamodb-configuration.md` — DynamoDB single-table design
- `skills/patterns/error-response-format.md` — Standard error response format
- `skills/patterns/iam-least-privilege.md` — IAM role patterns
- `skills/patterns/observability-requirements.md` — Observability standards
- `skills/patterns/opentelemetry-template.md` — OTel instrumentation template
- `skills/patterns/scaffolding-strategy.md` — Project scaffolding

## Design Review Checklist
- [ ] Architecture supports all requirements
- [ ] Follows AWS serverless-first standards from technology-standards.md
- [ ] Clean Architecture layer separation enforced
- [ ] DynamoDB access patterns documented
- [ ] Cognito auth on all endpoints
- [ ] Observability: OTel tracing + metrics + structured logging
- [ ] WAF + rate limiting configured
- [ ] Cost-effective
- [ ] Disaster recovery considered
- [ ] Shift-left test plan generated from acceptance criteria

## Outputs
- `docs/specs/{service-name}/design.md` — System design
- `docs/specs/{service-name}/api-design.md` — API specifications
- `docs/specs/{service-name}/data-models.md` — Data model definitions
- `docs/specs/{service-name}/security-design.md` — Security design
- `docs/specs/{service-name}/implementation-plan.md` — Implementation plan
- `docs/specs/{service-name}/test-plan.md` — Shift-left test plan
- Design review sign-off

## APPROVAL GATE - STOP HERE

**CRITICAL**: After completing design documents:
1. Run design-review skill (`skills/definitions/design-review.md`)
2. Generate `docs/reviews/design-review-report.md`
3. Present report to developer
4. **STOP - Do NOT proceed to Phase 3**
5. **WAIT for explicit approval**

Only proceed to Phase 3 after developer says "approved" or "proceed"

See **WORKFLOW-GATES.md** for complete gate protocol.

## Next Phase
-> [Phase 3: Task Elaboration](03-task-elaboration.md) - **ONLY AFTER APPROVAL**
