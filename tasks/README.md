# Task Management

This directory tracks all project tasks throughout the development lifecycle.

## Directory Structure

- **backlog/**: Tasks waiting to be started
- **in_progress/**: Tasks currently being worked on
- **completed/**: Finished tasks

## Task Workflow

```
backlog/ → in_progress/ → completed/
```

## Task File Template

Create task files using this template:

```markdown
# Task ID: TASK-XXX

## Title
[Clear, actionable title]

## Description
[Detailed description of what needs to be done]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Code reviewed

## Dependencies
- TASK-YYY must be completed first
- Requires design document: docs/specs/architecture.md

## Effort Estimate
[S | M | L | XL]

## Skills Required
- Backend (Python, Lambda)
- Frontend (Angular)
- Infrastructure (CDK)
- AI Integration

## Files to Create/Modify
- `/backend/lambdas/api/handler.py` (modify)
- `/infra/stacks/api_stack.py` (create)

## Implementation Notes
[Technical considerations, patterns to follow, gotchas]

## Status
- Created: YYYY-MM-DD
- Started: YYYY-MM-DD
- Completed: YYYY-MM-DD
```

## Task Naming Convention

`TASK-[AREA]-[NUMBER]`

Examples:
- `TASK-BE-001`: Backend task
- `TASK-FE-001`: Frontend task
- `TASK-INFRA-001`: Infrastructure task
- `TASK-AI-001`: AI integration task

## Task Management Process

1. **Create Task**: During Phase 3 (Task Elaboration)
2. **Prioritize**: Assign to sprint/iteration
3. **Start Work**: Move to `in_progress/`
4. **Complete**: Move to `completed/` when all acceptance criteria met
5. **Review**: Archive old completed tasks periodically

## Current Sprint

Create sprint files:
- `sprint-1.md`
- `sprint-2.md`

Track sprint progress and goals.
