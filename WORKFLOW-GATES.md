# Workflow Approval Gates - CRITICAL INSTRUCTIONS

**Purpose**: This document defines MANDATORY approval gates that AI MUST respect during development.

⚠️ **CRITICAL**: AI must STOP at each gate and WAIT for explicit developer approval before proceeding.

---

## Gate Protocol

At each gate, AI must:
1. ✅ **Complete** the work for that stage
2. ✅ **Generate** the review report
3. ✅ **Present** the report to the developer
4. 🛑 **STOP** - Do NOT proceed further
5. ⏸️ **WAIT** for explicit developer approval
6. Only after **"APPROVED"** → Proceed to next stage

**Developer Approval Phrases**:
- ✅ "approved" / "approve" / "looks good" / "proceed" / "continue" / "next stage"
- ❌ "not approved" / "changes needed" / "fix X first" / "blocked"

---

## 🚦 Gate 1: Requirements Review

### After Stage 1 (Requirements Analysis)

**AI Completes**:
- `docs/specs/lambdas/{name}/{name}-requirements.md` created
- `docs/specs/lambdas/{name}/reviews/requirements-review-report.md` generated

**AI Must Present**:
```
📋 REQUIREMENTS REVIEW COMPLETE

Score: X/100
Status: PASS/CONDITIONAL/FAIL

Critical Issues: X
Major Issues: X
Minor Issues: X

Report Location: docs/specs/lambdas/{name}/reviews/requirements-review-report.md

🛑 WAITING FOR APPROVAL 🛑

Please review the report and respond:
- "approved" to proceed to Stage 2 (Design)
- "changes needed" to revise requirements
```

**AI Must STOP Here**: Do NOT start design work

**After Approval**: Proceed to Stage 2 (Design)

---

## 🚦 Gate 2: Design Review ⭐ MOST CRITICAL

### After Stage 2 (System Design)

**AI Completes**:
- `docs/specs/lambdas/{name}/{name}-app-design.md` created (Domain Design)
- `docs/specs/lambdas/{name}/implementation-plan.md` created
- `docs/specs/lambdas/{name}/{name}-infra-design.md` created (CDK & Infra Design)
- `docs/specs/lambdas/{name}/reviews/design-review-report.md` generated

**IMPORTANT - Architecture vs Design**:
- **Platform Architecture** (skills/): Defined ONCE for all services - approved technologies, patterns, standards
- **Service Design** (docs/specs/lambdas/{name}/*): Created PER SERVICE - specific endpoints, functions, DTOs, data flows
- Design Review validates that service design complies with platform architecture
- NEVER create `architecture.md` at service level - use `{name}-app-design.md` instead

**AI Must Present**:
```
🏗️ DESIGN REVIEW COMPLETE

Score: X/100
Status: PASS/CONDITIONAL/FAIL

Technology Standards Compliance: X/100
Architectural Patterns Compliance: X/100
Design Completeness: X/100
Design Quality: X/100

Critical Issues: X
Major Issues: X
Minor Issues: X

Report Location: docs/specs/lambdas/{name}/reviews/design-review-report.md

⚠️ This is the MOST CRITICAL gate - design defines the entire implementation ⚠️

🛑 WAITING FOR APPROVAL 🛑

Please review:
1. Service design (docs/specs/lambdas/{name}/{name}-app-design.md and {name}-infra-design.md)
2. Implementation plan (docs/specs/lambdas/{name}/implementation-plan.md)
3. Design review report (docs/specs/lambdas/{name}/reviews/design-review-report.md)

Respond:
- "approved" to proceed to Stage 3 (Task Breakdown)
- "changes needed" to revise design
- Ask questions if anything is unclear
```

**AI Must STOP Here**: Do NOT create tasks or generate code

**After Approval**: Proceed to Stage 3 (Task Breakdown)

---

## 🚦 Gate 3: Task Breakdown Review

### After Stage 3 (Task Elaboration)

**AI Completes**:
- Task files created in `tasks/backlog/`
- Task list presented

**AI Must Present**:
```
📝 TASK BREAKDOWN COMPLETE

Total Tasks: X
Estimated Effort: X hours/days

Tasks:
1. TASK-001: Description
2. TASK-002: Description
...

🛑 WAITING FOR APPROVAL 🛑

Please review the task breakdown and respond:
- "approved" to proceed to Stage 4 (Implementation)
- "adjust tasks" to modify breakdown
```

**AI Must STOP Here**: Do NOT start code generation

**After Approval**: Proceed to Stage 4 (Implementation of first task)

---

## 🚦 Gate 4: Code + Test Review (PER TASK)

### After Each Task Implementation

**AI Completes**:
- Code generated for task
- Code review performed
- Tests generated for task
- Test review performed
- All tests passing
- Coverage ≥ 80%

**AI Must Present**:
```
✅ TASK-XXX CODE + TEST REVIEW COMPLETE

Task: [Task Name]

Code Review Score: X/100
Test Review Score: X/100
Test Coverage: X%

Files Created:
- [list of files]

Tests: X passed, 0 failed
Coverage: X% (target: 80%)

Critical Issues: X
Major Issues: X
Minor Issues: X

Report Locations:
- docs/specs/lambdas/{name}/reviews/code-review-TASK-XXX-report.md
- docs/specs/lambdas/{name}/reviews/test-review-TASK-XXX-report.md

🛑 WAITING FOR APPROVAL 🛑

Please review:
1. Generated code
2. Code review report
3. Generated tests
4. Test review report
5. Test execution results

Respond:
- "approved" to mark task complete and proceed to next task
- "changes needed" to fix issues
- "run tests again" to re-run tests
```

**AI Must STOP Here**: Do NOT proceed to next task

**After Approval**:
- Mark task complete
- Proceed to next task (repeat Gate 4)
- OR if all tasks complete → Proceed to Stage 5 (Integration)

---

## 🚦 Gate 5: Integration Review

### After Stage 5 (Integration Testing)

**AI Completes**:
- All tasks implemented
- System deployed to dev/staging
- Integration tests executed
- `docs/specs/lambdas/{name}/reviews/integration-review-report.md` generated

**AI Must Present**:
```
🔗 INTEGRATION REVIEW COMPLETE

Overall Score: X/100
Status: PASS/CONDITIONAL/FAIL

API Integration: X/100
Lambda Integration: X/100
Data Layer: X/100
E2E Workflows: X/100
Observability: X/100
Performance: X/100
Security: X/100

Critical Issues: X
Major Issues: X

Environment: [dev/staging]
API Endpoint: [URL]

Report Location: docs/specs/lambdas/{name}/reviews/integration-review-report.md

🛑 WAITING FOR APPROVAL 🛑

Please:
1. Test the deployed system manually
2. Review integration test results
3. Check CloudWatch logs and X-Ray traces
4. Review the integration report

Respond:
- "approved" to proceed to Stage 6 (Documentation)
- "changes needed" to fix integration issues
```

**AI Must STOP Here**: Do NOT generate documentation or prepare deployment

**After Approval**: Proceed to Stage 6 (Documentation)

---

## 🚦 Gate 6: Documentation Review

### After Stage 6 (Documentation Generation)

**AI Completes**:
- API documentation generated
- Deployment guide generated
- Operations runbooks generated
- `docs/specs/lambdas/{name}/reviews/documentation-review-report.md` generated

**AI Must Present**:
```
📚 DOCUMENTATION REVIEW COMPLETE

Score: X/100
Status: PASS/CONDITIONAL/FAIL

API Documentation: X/100
Deployment Guide: X/100
Operations Runbooks: X/100

Critical Issues: X
Major Issues: X

Documentation Locations:
- docs/api/
- docs/deployment/
- docs/operations/

Report Location: docs/specs/lambdas/{name}/reviews/documentation-review-report.md

🛑 WAITING FOR APPROVAL 🛑

Please:
1. Verify API documentation matches implementation
2. Test deployment guide (follow steps)
3. Review operations runbooks

Respond:
- "approved" to prepare for production deployment
- "changes needed" to fix documentation issues
```

**AI Must STOP Here**: Do NOT deploy to production

**After Approval**: System ready for production deployment

---

## Emergency Stop Protocol

If at ANY point developer says:
- "stop"
- "wait"
- "hold on"
- "pause"
- "don't continue"

**AI MUST**:
1. Immediately stop current work
2. Save current progress
3. Wait for instructions

---

## Anti-Patterns to AVOID

❌ **NEVER do this**:
- Complete Stage 1 → Automatically start Stage 2 without approval
- Generate design → Immediately start coding
- Pass one review → Continue to next stage automatically
- Assume silence means approval
- Say "I'll proceed with..." without waiting for response

✅ **ALWAYS do this**:
- Complete work → Generate review → Present → STOP → Wait
- Explicitly ask "Please review and approve before I proceed"
- Wait for explicit "approved" before continuing
- If uncertain, ask for clarification

---

## Quick Reference: All 6 Gates

| Gate | After Stage | Review Type | Stop Point |
|------|-------------|-------------|------------|
| 🚦 1 | Requirements Analysis | requirements-review | Before design starts |
| 🚦 2 | System Design | design-review ⭐ | Before task breakdown |
| 🚦 3 | Task Breakdown | task-review | Before code generation |
| 🚦 4 | Each Task Implementation | code-review + test-review | Before next task |
| 🚦 5 | Integration Testing | integration-review | Before documentation |
| 🚦 6 | Documentation | documentation-review | Before production deploy |

---

## Example: Correct Workflow Execution

```
AI: [Generates requirements.md]
AI: [Runs requirements-review]
AI: [Presents review report]
AI: "🛑 WAITING FOR APPROVAL 🛑 - Please review requirements before I proceed to design"
AI: [STOPS - waits for response]

Developer: "approved"

AI: "✅ Proceeding to Stage 2: System Design"
AI: [Generates design.md, implementation-plan.md]
AI: [Runs design-review]
AI: [Presents review report]
AI: "🛑 WAITING FOR APPROVAL 🛑 - Please review design before I proceed to implementation"
AI: [STOPS - waits for response]

Developer: "I see an issue with the Lambda memory config - change to 1024MB"

AI: [Updates design]
AI: [Re-runs design-review]
AI: [Presents updated report]
AI: "🛑 WAITING FOR APPROVAL 🛑"
AI: [STOPS - waits for response]

Developer: "approved"

AI: "✅ Proceeding to Stage 3: Task Breakdown"
...
```

---

## Special Case: Hello World Example

For the current Hello World project, we are at:

**Current Status**: Stage 2 Design Review

**What AI has completed**:
- ✅ Stage 1: Requirements (docs/specs/lambdas/hello-world/hello-world-requirements.md)
- ✅ Requirements Review (docs/specs/lambdas/hello-world/reviews/requirements-review-report.md) - APPROVED
- ✅ Stage 2: Design (docs/specs/lambdas/hello-world/hello-world-app-design.md, docs/specs/lambdas/hello-world/hello-world-infra-design.md, implementation-plan.md)
- ⏳ Design Review (in progress - needs to be generated)

**What AI MUST do now**:
1. Generate docs/specs/lambdas/hello-world/reviews/design-review-report.md
2. Present the report
3. 🛑 STOP and WAIT for approval
4. Fix any issues if needed
5. Only after approval → Proceed to Stage 3

**What AI MUST NOT do**:
- ❌ Start creating task files
- ❌ Start generating code
- ❌ Continue with any implementation work

---

## Reminder for AI

Before taking ANY action that moves to a new stage, ask yourself:

**"Have I received explicit approval from the developer to proceed past the last gate?"**

If the answer is NO → STOP and present the review report

If the answer is YES → Proceed to next stage

---

**This document is MANDATORY. AI must follow these gates strictly.**
