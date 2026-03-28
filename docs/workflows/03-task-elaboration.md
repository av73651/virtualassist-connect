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

### 3. Task Decomposition
Break each story into technical tasks:

**Example Story**: "As a user, I want to authenticate via AWS Cognito"

**Tasks**:
1. Set up Cognito User Pool in CDK
2. Create Lambda authorizer function
3. Integrate API Gateway with authorizer
4. Implement frontend login component
5. Add token management service
6. Write unit tests
7. Write integration tests
8. Update documentation

### 4. Task Specification

For each task, define:
- **Task ID**: Unique identifier
- **Title**: Clear, action-oriented
- **Description**: What needs to be done
- **Acceptance Criteria**: How to verify completion
- **Dependencies**: Required prior tasks
- **Estimated Effort**: T-shirt sizing (S, M, L, XL)
- **Skills Required**: Backend, frontend, infra, AI
- **Files Affected**: List of files to create/modify

### 5. Dependency Mapping
- Identify task dependencies
- Create dependency graph
- Determine critical path
- Identify tasks that can be parallelized

### 6. Sprint Planning
- Group tasks into sprints/iterations
- Balance workload
- Prioritize by value and dependencies
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
- Requires API design spec

## Effort Estimate
[S | M | L | XL]

## Skills Required
- Backend (Python, Lambda)
- Frontend (Angular)
- Infrastructure (CDK)

## Files Affected
- `/backend/lambdas/auth/handler.py` (create)
- `/infra/stacks/auth_stack.py` (create)
- `/frontend/src/app/services/auth.service.ts` (create)

## Implementation Notes
[Any technical considerations, patterns to follow, etc.]
```

## AI Skills to Use
- `story-splitter`: Break epics into user stories
- `task-generator`: Generate technical tasks from stories
- `dependency-analyzer`: Identify task dependencies
- `effort-estimator`: Estimate task complexity

## Sprint Planning Template

```markdown
# Sprint X: [Sprint Goal]

**Duration**: [Start Date] - [End Date]

## Sprint Goal
[What we aim to achieve]

## Tasks
### High Priority
- [ ] TASK-XXX: [Task title]
- [ ] TASK-YYY: [Task title]

### Medium Priority
- [ ] TASK-ZZZ: [Task title]

### Low Priority (If time permits)
- [ ] TASK-AAA: [Task title]

## Definition of Done
- All tests pass
- Code reviewed
- Documentation updated
- Deployed to dev environment
```

## Outputs
- ✅ Complete backlog of tasks in `tasks/backlog/`
- ✅ Dependency graph
- ✅ Sprint plan
- ✅ Clear acceptance criteria for all tasks
- ✅ Effort estimates

## Next Phase
→ [Phase 4: Task Execution](04-execution.md)
