# Phase 2: Design & Architecture

## Objective
Create comprehensive technical design and architecture for the system based on validated requirements.

## Process

### 1. System Architecture
- Define high-level architecture
- Choose architectural patterns (microservices, serverless, etc.)
- Identify AWS services needed
- Design data flow and integration points

### 2. Component Design

**Backend Design:**
- Lambda function structure and responsibilities
- API Gateway endpoints and methods
- Data models and schemas
- External service integrations
- Error handling strategy

**Frontend Design:**
- Angular application structure
- Component hierarchy
- State management approach
- Routing design
- UI/UX wireframes

**Infrastructure Design:**
- CDK stack organization
- Resource naming conventions
- Environment strategy (dev, staging, prod)
- IAM roles and permissions
- Monitoring and logging setup

### 3. API Design
- RESTful endpoints specification
- Request/response formats
- Authentication/authorization flow
- Error response standards
- Rate limiting strategy

### 4. Data Design
- Data models and relationships
- Storage solutions (DynamoDB, S3, etc.)
- Caching strategy
- Data validation rules

### 5. Security Design
- Authentication mechanism (Cognito, API keys, etc.)
- Authorization model
- Secrets management
- Data encryption (at rest and in transit)
- Security best practices

## Documentation

Location: `docs/specs/`

Required documents:
- `design.md`: Service-specific design (NOT platform architecture)
- `api-design.md`: Complete API specification
- `data-models.md`: Data structures and relationships
- `security-design.md`: Security design
- `implementation-plan.md`: File-by-file implementation blueprint

**Important**: Platform architecture is defined in `skills/definitions/technology-standards.md` and `skills/patterns/`. Service design documents how THIS service implements those standards.

## AI Skills to Use
- `architecture-designer`: Generate architecture diagrams and patterns
- `api-spec-generator`: Create OpenAPI/Swagger specifications
- `design-reviewer`: Validate design against best practices

## Design Review Checklist
- [ ] Architecture supports all requirements
- [ ] Scalable and maintainable
- [ ] Follows AWS Well-Architected Framework
- [ ] Security by design
- [ ] Cost-effective
- [ ] Monitoring and observability built-in
- [ ] Disaster recovery considered

## Outputs
- ✅ System design documentation (design.md)
- ✅ API specifications
- ✅ Data model definitions
- ✅ Security design
- ✅ Infrastructure design
- ✅ Design review sign-off

**Note**: Architecture (technology standards and patterns) is defined once for the platform in `skills/`. Design is service-specific and created per service.

## 🚦 APPROVAL GATE - STOP HERE

⚠️ **CRITICAL**: After completing design documents:
1. Run design-review skill
2. Generate docs/reviews/design-review-report.md
3. Present report to developer
4. **🛑 STOP - Do NOT proceed to Phase 3**
5. **⏸️ WAIT for explicit approval**

Only proceed to Phase 3 after developer says "approved" or "proceed"

See **WORKFLOW-GATES.md** for complete gate protocol.

## Next Phase
→ [Phase 3: Task Elaboration](03-task-elaboration.md) - **ONLY AFTER APPROVAL**
