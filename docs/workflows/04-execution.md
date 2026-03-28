# Phase 4: Task Execution (Implementation)

## Objective
Implement tasks following best practices with AI assistance while maintaining code quality.

## Process

### 1. Task Selection
- Pick task from sprint backlog
- Verify dependencies are complete
- Review task specification and acceptance criteria
- Move task to `tasks/in_progress/`

### 2. Implementation Setup
- Create feature branch: `git checkout -b feature/TASK-XXX`
- Review related design documents
- Identify files to create/modify
- Set up local development environment

### 3. AI-Assisted Development

**Use AI Skills:**
- `code-generator`: Generate boilerplate and implementation
- `code-reviewer`: Review code for issues
- `test-generator`: Create unit and integration tests
- `doc-generator`: Generate documentation

**Best Practices:**
- Follow Python PEP 8 style guide
- Use type hints in Python code
- Follow Angular style guide for frontend
- Write clean, readable, maintainable code
- Add comments only where necessary (code should be self-documenting)
- Handle errors gracefully
- Log important events

### 4. Code Development Standards

**Backend (Python):**
```python
# Use type hints
def process_request(user_id: str, data: dict) -> dict:
    """
    Process user request.

    Args:
        user_id: User identifier
        data: Request payload

    Returns:
        Processed response data
    """
    # Implementation
    pass

# Use dataclasses for models
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str
```

**Frontend (Angular):**
- Use TypeScript strict mode
- Follow component-service pattern
- Use RxJS observables for async operations
- Implement proper error handling
- Use Angular best practices

**Infrastructure (CDK):**
- Use constructs for reusability
- Follow naming conventions
- Add tags for resource management
- Document stack parameters
- Use environment-specific configs

### 5. Testing During Development
- Write unit tests alongside code (TDD when possible)
- Test edge cases and error conditions
- Run tests locally before committing
- Aim for >80% code coverage

### 6. Code Review Process
1. Self-review: Review your own code first
2. Use AI code reviewer skill
3. Run all tests
4. Check linting and formatting
5. Verify acceptance criteria met
6. Create pull request
7. Address review feedback

### 7. Documentation
Update relevant documentation:
- Inline code comments (when needed)
- API documentation
- README updates
- Architecture decision records (ADRs)

### 8. Commit Standards
Follow conventional commits:
```bash
feat: add user authentication handler
fix: resolve API Gateway CORS issue
docs: update API documentation
test: add integration tests for agents
refactor: simplify Lambda layer structure
```

## AI Skills to Use

### Code Generation
- `lambda-generator`: Create Lambda function templates
- `angular-component-generator`: Create Angular components
- `cdk-stack-generator`: Create CDK stack definitions

### Code Quality
- `code-reviewer`: Automated code review
- `security-scanner`: Check for security issues
- `performance-optimizer`: Identify performance improvements

### Testing
- `unit-test-generator`: Generate unit tests
- `integration-test-generator`: Generate integration tests
- `mock-generator`: Create test mocks

### Documentation
- `api-doc-generator`: Generate API documentation
- `readme-updater`: Update README files
- `comment-generator`: Add code comments

## Development Workflow

```
1. Pick task from backlog
2. Create feature branch
3. Use AI to generate initial code
4. Refine and customize code
5. Write tests
6. Run tests locally
7. Use AI code reviewer
8. Fix issues
9. Commit with conventional commit message
10. Push to remote
11. Create pull request
12. Address feedback
13. Merge to main
14. Move task to completed
15. Deploy to dev environment
```

## Quality Gates
Before marking task complete:
- [ ] All acceptance criteria met
- [ ] Unit tests written and passing
- [ ] Integration tests passing (if applicable)
- [ ] Code reviewed (self + AI)
- [ ] Documentation updated
- [ ] No linting errors
- [ ] Security scan passed
- [ ] Committed to version control

## Outputs
- ✅ Working code committed to repository
- ✅ Tests passing
- ✅ Documentation updated
- ✅ Task moved to `tasks/completed/`
- ✅ Ready for Phase 5 (Testing)

## Next Phase
→ [Phase 5: Testing](05-testing.md)
