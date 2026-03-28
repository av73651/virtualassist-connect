# Pull Request Template

## What does this PR do?
[Provide a brief description of the changes introduced by this PR. Include the context of WHY these changes are being made.]

## Traceability
- **Jira/Ticket ID**: 
- **Acceptance Criteria (ACs) Addressed**: 

---

## 🛑 DEVELOPER CHECKLIST (MANDATORY) 🛑

If you cannot check all of these boxes, your PR will be automatically rejected by the architectural review gates. **Do not skip these steps.**

### 1. Requirements & Design
- [ ] I have read the `technology-standards.md` constraints.
- [ ] This feature directly satisfies a documented Acceptance Criteria (AC).
- [ ] I have generated or updated the `System Design` diagrams/docs if this is a large architectural change.

### 2. Implementation Standards
- [ ] I used the Micro-Lambda routing pattern (`api-routing-strategy.md`).
- [ ] My Lambda Handler contains **zero** business logic (parsing/routing only).
- [ ] My Service layer contains **zero** HTTP, API Gateway, or Database parsing logic.
- [ ] I have used the `Code Generation` AI Skill to generate standard OpenTelemetry boilerplate.

### 3. Observability & Security 
- [ ] I have extracted the OpenTelemetry `trace_id` and injected it into my JSON logs.
- [ ] I have used Python's Context Manager (`with tracer.start_as_current_span`) for critical business logic paths.
- [ ] I am NOT validating JWTs or Tokens inside the Lambda (delegated to API Gateway Cognito Authorizer).
- [ ] I have NOT hardcoded any secrets (all references are to Secrets Manager/SSM).

### 4. Quality & Testing
- [ ] I have achieved >= 80% test coverage for this feature.
- [ ] Tests explicitly trace back to ACs (e.g., `test_user_creation_ac_001`).
- [ ] I have run my code through the `Code Review` AI Skill locally, and all Critical/High violations have been resolved.

---

## Technical Risk or Architectural Exceptions
[Are you doing something unusual? Are you breaking a `technology-standards.md` rule? Document the exact technical justification here, or the PR will be denied.]

---

## AI Generation Statement
Please describe the extent to which you used AI tools (Code Generation Skill, Copilot) to generate this code, and verify that you have manually reviewed the generated output:
> [Your response here]
