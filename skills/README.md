# AI Skills for Development

This directory contains AI skill definitions that assist with the AI-driven development lifecycle.

⚠️ **IMPORTANT**: This workflow has **6 MANDATORY APPROVAL GATES** where AI must STOP and WAIT for developer approval before proceeding. See **WORKFLOW-GATES.md** in project root for complete instructions.

## Skill Workflow Sequence

Skills operate in the following sequence to ensure architectural consistency:

```
1. Requirements Analysis
   ↓
2. Technology Standards ← Defines platform architecture and approved technologies
   ↓
3. System Design (uses constraints from Technology Standards)
   ↓
4. Code Generation (implements using approved stack)
   ↓
5. Code Review (verifies standards compliance)
   ↓
6. Test Generation
   ↓
7. Documentation Generation
```

**Technology Standards acts as architectural constraints for all downstream skills.**

---

## Available Skills

### 1. Requirements Analysis
**File**: `definitions/requirements-analysis.md`
**Purpose**: Extract and structure requirements from natural language into design-ready artifacts
**Use in**: Phase 1 (Requirements Gathering)

**Capabilities**:
- Persona identification
- User needs analysis
- Functional requirements definition
- Technical requirements extraction
- Business rules identification
- Domain model extraction
- Workflow and process flow diagrams
- Acceptance criteria generation

---

### 2. Technology Standards ⭐
**File**: `definitions/technology-standards.md`
**Purpose**: Define approved technology baseline and platform architecture constraints
**Use in**: After Requirements, before System Design

**Capabilities**:
- Defines serverless-first AWS architecture
- Specifies approved technology stack
- Establishes design patterns
- Enforces observability standards
- Sets security defaults
- Provides technology usage rules

**Approved Stack**:
- Compute: AWS Lambda (Python 3.12)
- API: Amazon API Gateway
- Data: DynamoDB + S3
- Messaging: EventBridge + SQS
- AI: Amazon Bedrock (Claude)
- Observability: OpenTelemetry + CloudWatch + X-Ray
- IaC: AWS CDK (Python)
- Security: Cognito + IAM + Secrets Manager

**Integration**: All other skills MUST follow these technology constraints.

---

### 3. Code Generation
**File**: `definitions/code-generation.md`
**Purpose**: Generate production-ready code following architectural standards
**Use in**: Phase 4 (Task Execution)

**Capabilities**:
- Generate Lambda handlers with proper layer separation
- Create Angular components (standalone)
- Generate CDK infrastructure stacks
- Implement observability (OpenTelemetry)
- Apply security best practices
- Generate unit tests

**Constraints**: MUST use technologies from Technology Standards skill.

---

### 4. Code Review
**File**: `definitions/code-review.md`
**Purpose**: Enterprise-grade automated code review
**Use in**: Phase 4 (Task Execution), Phase 5 (Testing)

**Capabilities**:
- Architecture compliance review (handlers/services/repositories)
- Aspect enforcement (logging, auth, metrics, tracing)
- Observability validation
- Security review (secrets, IAM, input validation)
- Infrastructure review (encryption, tagging, least privilege)
- API design consistency
- Code simplicity analysis
- Test quality assessment
- Performance review

**Review Dimensions**: 81+ specific checkpoints across 9 categories

**Constraints**: Verifies adherence to Technology Standards.

---

### 5. Test Generation
**File**: `definitions/test-generation.md`
**Purpose**: Generate comprehensive test suites
**Use in**: Phase 4 (Task Execution), Phase 5 (Testing)

**Capabilities**:
- Unit test generation (pytest for Python, Jasmine for Angular)
- Integration test scenarios
- E2E test workflows
- Test data and fixtures
- Mock generation

**Standards**:
- >80% code coverage target
- Arrange-Act-Assert pattern
- Test independence
- Proper mocking

---

### 6. Documentation Generation
**File**: `definitions/documentation-generation.md`
**Purpose**: Create accurate, code-derived documentation
**Use in**: All phases

**Capabilities**:
- API documentation from handlers/DTOs
- Code docstrings (Python, TypeScript)
- Setup guides from dependencies
- Deployment guides from CDK
- Infrastructure docs from CDK stacks
- Operations guides (logging, metrics, tracing)
- Runbooks for troubleshooting
- Mermaid diagrams (code-derived only)

**Principle**: Document ONLY what exists in code/config/infrastructure. No speculation.

**Constraints**: Must reflect Technology Standards in all documentation.

---

## Development Patterns

In addition to actionable skills, this repository defines standard architectural and development patterns in `patterns/`:
- **`api-routing-strategy.md`**: Micro-Lambda REST routing rules.
- **`aspect-oriented-programming.md`**: Enforces strict separation of cross-cutting concerns using Python decorators.
- **`ci-cd-enforcement.md`**: Automated quality and strict CI/CD gates.
- **`development-best-practices.md`**: Enforces strict typing, clean architecture, and test-driven traceability.
- **`dynamodb-configuration.md`**: Standardized data access patterns.
- **`error-response-format.md`**: Consistent API error payloads.
- **`iam-least-privilege.md`**: Standardized AWS policy generation.
- **`opentelemetry-template.md`**: Native OpenTelemetry observability pattern.
- **`layer-architecture.md`**: Hexagonal/Clean Architecture blueprints.
- **`observability-requirements.md`**: Core system-wide telemetry standards.
- **`scaffolding-strategy.md`**: Relegating boilerplate generation strictly to AI tools.

---

## How to Use Skills

### Step 1: Requirements Analysis
Start with understanding user needs and system requirements.
```bash
cat definitions/requirements-analysis.md
```

### Step 2: Technology Standards
Review platform architecture and approved technologies.
```bash
cat definitions/technology-standards.md
```
This establishes the technology constraints for design and implementation.

### Step 3: System Design
Design the system within technology constraints.
(System Design skill to be created - uses Technology Standards)

### Step 4: Code Generation
Generate code using approved stack.
```bash
cat definitions/code-generation.md
```

### Step 5: Code Review
Review generated code for compliance.
```bash
cat definitions/code-review.md
```

### Step 6: Test Generation
Create comprehensive test suite.
```bash
cat definitions/test-generation.md
```

### Step 7: Documentation
Document the implementation.
```bash
cat definitions/documentation-generation.md
```

---

## Skill Integration

### Technology Standards as Foundation

The **Technology Standards** skill is unique - it acts as **architectural constraints** for all other skills:

```
Technology Standards (defines WHAT technologies to use)
        ↓
System Design (designs HOW using approved technologies)
        ↓
Code Generation (implements using approved stack)
        ↓
Code Review (verifies standards compliance)
        ↓
Documentation (reflects standard architecture)
```

### Cross-Skill Enforcement

**Code Generation** must:
- Generate Lambda handlers (not EC2, containers)
- Use DynamoDB for data (not unapproved databases)
- Include Lambda Powertools instrumentation
- Use Bedrock for AI capabilities
- Generate CDK for infrastructure

**Code Review** must flag:
- Non-approved technologies
- Missing observability
- Security violations
- Architecture violations

**Documentation** must:
- Reflect approved stack in all docs
- Reference AWS services by name
- Document any approved deviations

---

## Skill Characteristics

Each skill definition contains:
- **Purpose**: What the skill does
- **Capabilities**: Specific features
- **Templates**: Code/documentation templates
- **Usage**: How to invoke the skill
- **Integration**: Which phases to use it in
- **Quality Checks**: Validation criteria
- **Constraints**: What the skill must follow

---

## Implementation Approaches

Skills can be implemented as:

1. **System Prompts**: Load skill definition as context for Claude
2. **Custom Agents**: Build specialized agents for each skill
3. **Tool Integrations**: Integrate with linters, analyzers, generators
4. **Workflow Automation**: Chain skills in CI/CD pipeline

---

## Quality Gates

Before proceeding to next phase:

**After Requirements Analysis**:
- [ ] Requirements complete and validated
- [ ] User needs clearly defined
- [ ] Acceptance criteria specified

**After Technology Standards Review**:
- [ ] Approved stack understood
- [ ] Technology constraints clear
- [ ] Alternative technologies justified (if any)

**After Code Generation**:
- [ ] Code follows architectural structure
- [ ] Observability included
- [ ] Security standards applied

**After Code Review**:
- [ ] All critical issues resolved
- [ ] Architecture compliance verified
- [ ] Standards adherence confirmed

**After Test Generation**:
- [ ] >80% code coverage
- [ ] Edge cases covered
- [ ] Tests passing

**After Documentation**:
- [ ] API documented
- [ ] Setup guide complete
- [ ] Operations runbooks created

---

## Adding New Skills

To add a new skill:

1. Create markdown file in `definitions/`
2. Follow enterprise specification format:
   - Directive and principles
   - Detailed capabilities with examples
   - Templates and patterns
   - Integration with other skills
   - Quality expectations
   - Execution checklist
3. Define integration points with existing skills
4. Update this README with skill position in workflow
5. Update related skills if constraints apply

---

## Skill Maintenance

**When to Update Skills**:
- New technology added to approved stack → Update Technology Standards
- New architecture pattern adopted → Update Code Generation, Code Review
- New security requirement → Update Code Generation, Code Review, Technology Standards
- New observability requirement → Update all technical skills

**Update Process**:
1. Identify affected skills
2. Update skill definitions
3. Update integration points
4. Communicate changes to team
5. Update training materials

---

## Platform Architecture Summary

For quick reference, the approved platform stack:

**Backend**:
- AWS Lambda (Python 3.12)
- API Gateway (REST)
- DynamoDB (data)
- EventBridge (events)
- SQS (queues)

**Frontend**:
- Angular 17+
- S3 + CloudFront

**AI**:
- Amazon Bedrock
- Claude models

**Observability**:
- OpenTelemetry (ADOT)
- CloudWatch
- X-Ray

**Infrastructure**:
- AWS CDK (Python)

**Security**:
- Cognito (auth)
- IAM (authorization)
- Secrets Manager

See `definitions/technology-standards.md` for complete specifications.

---

## Quick Start Example

**Scenario**: Build a user management API

1. **Requirements**: Define user CRUD operations, authentication needs
2. **Technology Standards**: Confirm using Lambda + API Gateway + DynamoDB + Cognito
3. **System Design**: Design API endpoints, data model, authentication flow
4. **Code Generation**: Generate handler, service, repository, DTO, CDK
5. **Code Review**: Verify architecture compliance, security, observability
6. **Test Generation**: Create unit tests for service and repository
7. **Documentation**: Generate API docs, setup guide, deployment guide

All steps following the approved technology stack and architectural patterns.

---

**For detailed specifications, see individual skill files in `definitions/`.**
