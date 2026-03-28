# CI/CD Enforcement Gates Pattern

## Purpose
This pattern defines the **mandatory automated enforcement gates** that MUST run in the CI/CD pipeline. These gates transform the Markdown `skills/` from "optional suggestions" into **hard technical blockers**. 

A pull request CANNOT merge into the main branch unless every automated gate passes.

---

## 1. The Automation Pipeline Workflow

When a developer opens a Pull Request to `main` or `develop`, the following pipeline triggers sequentially:

### Gate 1: Code Security & Dependencies (Fast Fail)
Runs instantly to catch glaring security flaws.
- **Dependency Audit**: Runs `pip audit` or `npm audit`. Fails if CVE vulnerabilities are detected in the `requirements.txt`.
- **Secret Scanning**: Scans the diff for Hardcoded Secrets (AWS Keys, Anthropic Keys).
- **Static Analysis Format**: Runs `flake8` and `mypy --strict`. Fails PR on any dynamic typing violations.

### Gate 2: The Automated AI Code Reviewer
This is the primary architectural enforcement gate. 
- A pipeline script invokes the the `Code Review` AI Skill defined in `definitions/code-review.md`. 
- The AI scans the Pull Request diff. 
- **Blocker Rule**: If the Code Review AI skill outputs ANY findings marked as **Critical** or **High** Severity (e.g., Business Logic in Handler, Missing OpenTelemetry Spans, Insufficient IAM Least Privilege), the pipeline returns an `exit 1` code, blocking the merge and posting the AI's feedback as a PR comment.

### Gate 3: Test Coverage & Verification
- **Unit Tests**: Executes `pytest` across all `tests/` directories.
- **Coverage Gate**: Validates metrics against `coverage.xml`. The PR is automatically blocked if line coverage drops below **80%**.

### Gate 4: Infrastructure Validation (CDK)
- Runs `cdk synth`. Fails if OpenTelemetry Layers/Role synthesis fails. 
- Runs `cdk-nag` (AwsSolutions checks). The PR is blocked if CloudFormation stacks violate AWS foundational security rules (e.g., S3 buckets without encryption, IAM wildcard permissions `*`).

---

## 2. Dealing with Blocked Pipelines

If a developer's code is blocked by Gate 2 (Code Review AI) or Gate 4 (CDK Nag) due to a perceived "false positive" or an intentional architectural exception:

1. **The Exception Rule**: Developers MUST document the exception under "Technical Risk or Architectural Exceptions" in the `PULL_REQUEST_TEMPLATE.md`.
2. **The Override**: Only a Principal Engineer / Architect can manually override the pipeline block and force-merge the PR. The override MUST be explicitly recorded in the code review system.

---

## 3. Why this Matters
Without Gate 2 running the AI Code Reviewer in the loop, developers will suffer from OpenTelemetry Boilerplate Fatigue and revert to writing massive, monolithic REST APIs inside single functions. The CI/CD pipeline is the objective enforcer of the `skills/` repository.
