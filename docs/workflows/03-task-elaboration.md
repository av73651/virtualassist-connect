# Phase 3: Task Elaboration

## Objective
Break down design into concrete, implementable tasks with clear acceptance criteria and dependencies.

## Process

### 1. Epic Creation
Break requirements into epics (large bodies of work):
- User Management Epic
- AI Agent Integration Epic
- API Development Epic
- Frontend Development Epic
- Infrastructure Setup Epic
- Testing & Quality Assurance Epic

### 2. Story Breakdown
For each epic, create user stories:
- Keep stories small (completable in 1-3 days)
- Each story delivers value
- Stories are independent when possible
- Include acceptance criteria
- Assign MoSCoW priority (Must / Should / Could / Won't)

### 3. Task Decomposition
Break each story into technical tasks:

**Example Story**: "As a user, I want to authenticate via AWS Cognito"

**Tasks**:
1. Create shared Cognito User Pool in CDK (`infra/stacks/auth_stack.py`)
2. Add Cognito authorizer to API Gateway in service stack
3. Implement frontend login component
4. Add token management service
5. Write unit tests (`backend/lambdas/{name}/tests/unit/`)
6. Write integration tests (`backend/lambdas/{name}/tests/integration/`)
7. Update documentation (`docs/specs/{service-name}/`)

### 4. Task Specification

For each task, define:
- **Task ID**: Unique identifier
- **Title**: Clear, action-oriented
- **Description**: What needs to be done
- **Acceptance Criteria**: How to verify completion
- **Dependencies**: Required prior tasks
- **Estimated Effort**: T-shirt sizing (S, M, L, XL)
- **Skills Required**: Backend, frontend, infra
- **Files Affected**: List of files to create/modify
- **Test Plan Reference**: Link to test cases in `docs/specs/{service-name}/test-plan.md`

### 5. Dependency Mapping
- Identify task dependencies
- Create dependency graph
- Determine critical path
- Identify tasks that can be parallelized

### 6. Sprint Planning
- Group tasks into sprints/iterations
- Balance workload
- Prioritize by MoSCoW value and dependencies
- Set sprint goals

## Task Documentation

Location: `tasks/backlog/`

Task template:
```markdown
# Task ID: TASK-XXX

## Title
[Clear, actionable title]

## Description
[Detailed description of what needs to be done]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests pass
- [ ] Documentation updated

## Dependencies
- TASK-YYY must be completed first
- Requires API design spec from `docs/specs/{service-name}/api-design.md`

## Effort Estimate
[S | M | L | XL]

## Skills Required
- Backend (Python, Lambda)
- Frontend (Angular)
- Infrastructure (CDK)

## Files Affected
- `backend/lambdas/{name}/src/handlers/handler.py` (create)
- `infra/stacks/{name}_stack.py` (create)
- `frontend/src/app/services/auth.service.ts` (create)

## Test Coverage
- Unit tests: `backend/lambdas/{name}/tests/unit/`
- Integration tests: `backend/lambdas/{name}/tests/integration/`
- Test plan: `docs/specs/{service-name}/test-plan.md`

## Patterns to Follow
- `skills/patterns/layer-architecture.md` — Clean Architecture layers
- `skills/patterns/error-response-format.md` — Error response format
- `skills/patterns/observability-requirements.md` — OTel instrumentation
```

## AI Skills Used

| Skill | File | Purpose |
|-------|------|---------|
| Requirements Analysis | `skills/definitions/requirements-analysis.md` | Break epics into stories with acceptance criteria |
| System Design | `skills/definitions/system-design.md` | Inform task decomposition from design artifacts |

**Note**: No dedicated task-elaboration skill exists. This phase uses requirements-analysis and system-design skills to inform decomposition, plus manual engineering judgment for effort estimation and dependency mapping.

## Sprint Planning Template

```markdown
# Sprint X: [Sprint Goal]

**Duration**: [Start Date] - [End Date]

## Sprint Goal
[What we aim to achieve]

## Tasks
### Must (Critical Path)
- [ ] TASK-XXX: [Task title]
- [ ] TASK-YYY: [Task title]

### Should (High Value)
- [ ] TASK-ZZZ: [Task title]

### Could (If Time Permits)
- [ ] TASK-AAA: [Task title]

## Definition of Done
- All tests pass (unit + integration)
- Code reviewed via `skills/definitions/code-review.md`
- Documentation updated in `docs/specs/{service-name}/`
- Deployed to dev environment
```

## Outputs
- Complete backlog of tasks in `tasks/backlog/`
- Dependency graph
- Sprint plan with MoSCoW priorities
- Clear acceptance criteria for all tasks
- Effort estimates
- Test fixtures and data prepared (from shift-left test plan)

## Next Phase
-> [Phase 4: Task Execution](04-execution.md)
