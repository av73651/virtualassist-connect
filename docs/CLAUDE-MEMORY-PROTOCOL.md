# Claude Memory Protocol - Assurance Document

This document provides **verifiable evidence** of how Claude Code will follow lessons learned from past mistakes.

## Commitment

**I, Claude Code, commit to the following systematic approach before ANY deployment AND when creating ANY new Lambda:**

---

## SPECIAL PROTOCOL: Creating New Lambda Functions

**When:** User asks to create a new Lambda function

**MANDATORY STEPS:**

### Step 0: Use Scaffolding Script (REQUIRED)
```bash
./scripts/create-new-lambda.sh <lambda-name>
```

**What I Must Do:**
1. NEVER create Lambda directories manually
2. ALWAYS use the scaffolding script
3. Verify script created all required files
4. Follow NEW-LAMBDA-CHECKLIST.md

**Evidence User Will See:**
- Tool call: `./scripts/create-new-lambda.sh <name>`
- Script output showing all files created
- Verification that requirements.txt has HTTP exporter and boto3

**User Can Verify:**
```bash
# Check Lambda was created with scaffold
ls backend/lambdas/<new-lambda>/build-in-docker.sh
ls backend/lambdas/<new-lambda>/requirements.txt

# Check requirements.txt has correct packages
grep "opentelemetry-exporter-otlp-proto-http" backend/lambdas/<new-lambda>/requirements.txt
grep "boto3" backend/lambdas/<new-lambda>/requirements.txt
```

---

## Commitment

**I, Claude Code, commit to the following systematic approach before ANY deployment:**

---

## STEP 1: Memory Check (MANDATORY)

**When:** Before starting any deployment task

**What:** Read and review `~/.claude/projects/-Users-rameshnagarajan/memory/MEMORY.md`

**Verification:**
```bash
# User can verify I've read memory by checking my responses reference:
# - deployment_lambda_packaging_lesson.md
# - observability_custom_metrics_iam_2026-04-04.md
# - deployment_local_testing_requirement_2026-04-04.md
```

**What I Will Do:**
1. Read MEMORY.md index
2. Identify relevant lessons for the current task
3. Read full content of relevant memory files
4. **Explicitly state** which lessons apply to current task
5. **Follow the prevention steps** documented in those lessons

**Evidence User Will See:**
- My first response will mention: "Checking memory for lessons learned..."
- I will cite specific memory files: "Per deployment_local_testing_requirement_2026-04-04.md..."
- I will follow the documented steps

---

## STEP 2: Pre-Deployment Validation (MANDATORY)

**When:** Before running `cdk deploy` or deploying any Lambda

**What:** Run `./scripts/pre-deploy-validation.sh <lambda-name>`

**Verification:**
```bash
# User can verify by checking:
# 1. I always run pre-deploy-validation.sh first
# 2. I show the validation output
# 3. I STOP if validation fails
```

**What I Will Do:**
1. Run pre-deployment validation script
2. Show full output to user
3. **STOP immediately** if validation fails
4. Fix issues before proceeding
5. Re-run validation until it passes
6. Only then proceed to deployment

**Evidence User Will See:**
- Tool call to run `./scripts/pre-deploy-validation.sh <lambda>`
- Validation output showing all checks passed
- If validation fails: I will NOT proceed to `cdk deploy`

---

## STEP 3: Local Testing (MANDATORY)

**When:** Before ANY Lambda deployment

**What:** Build package in Docker (x86_64) and test locally

**Verification:**
```bash
# User can verify by checking:
# 1. I build with: docker run --platform linux/amd64 ...
# 2. I test with: docker run ... test-lambda-imports.py
# 3. I show test results
```

**What I Will Do:**
1. Build Lambda package using Docker with `--platform linux/amd64`
2. Copy shared layer
3. Run test-lambda-imports.py in Lambda Docker environment
4. **STOP if tests fail**
5. Show test output to user
6. Only deploy if tests pass

**Evidence User Will See:**
- Docker build command with `--platform linux/amd64`
- Docker test command with test output
- "SUCCESS: All imports working" message
- No deployment without successful test

---

## STEP 4: Deployment with Validation

**When:** After all above steps pass

**What:** Deploy using validated package

**Verification:**
```bash
# User can verify by checking:
# 1. I use ./scripts/deploy.sh (which has validation built-in)
# 2. I show CDK diff before deploying
# 3. I test after deployment
```

**What I Will Do:**
1. Use `./scripts/deploy.sh` (which enforces validation)
2. Show CDK diff to user
3. Deploy
4. **Immediately test** deployed Lambda
5. Show test results

**Evidence User Will See:**
- Tool call: `./scripts/deploy.sh dev <lambda>`
- CDK diff output
- Post-deployment test invocation
- Success/failure clearly stated

---

## STEP 5: Post-Deployment Validation

**When:** Immediately after deployment

**What:** Validate Lambda works in production

**Verification:**
```bash
# User can verify by checking:
# 1. I invoke the Lambda
# 2. I check for errors in CloudWatch logs
# 3. I verify OpenTelemetry traces
```

**What I Will Do:**
1. Invoke Lambda with test payload
2. Check CloudWatch logs for errors
3. Verify no import errors
4. Check custom metrics appear
5. Report results to user

**Evidence User Will See:**
- Lambda invocation with result
- CloudWatch logs check
- Clear success/failure statement

---

## How User Can Hold Me Accountable

### 1. Check My First Response
When you ask me to deploy, my FIRST response must say:
- "Checking memory for lessons learned..."
- "Per [memory-file-name]..."
- "Running pre-deployment validation..."

### 2. Check Tool Calls
My tool calls must follow this exact order:
1. Read memory files
2. Run `pre-deploy-validation.sh`
3. Build in Docker (if needed)
4. Test locally
5. Deploy (only if above pass)

### 3. Check for Blocking
If validation fails, I must:
- **STOP immediately**
- **NOT proceed** to deployment
- Show error message
- Wait for user to fix or give instructions

### 4. Demand Evidence
At any point, ask me:
- "Did you check memory?"
- "Did you run pre-deploy-validation?"
- "Did you test locally?"
- "Show me the test output"

I must be able to point to specific tool calls showing I did these steps.

---

## Enforcement Mechanisms

### Technical Enforcement
1. **scripts/pre-deploy-validation.sh** - Blocks deployment if validation fails
2. **scripts/deploy.sh** - Runs local tests automatically, blocks if they fail
3. **test-lambda-imports.py** - Tests all critical imports in Lambda environment
4. **Memory files** - Persistent across all sessions

### Process Enforcement
1. **Deployment skill** - Mandates memory check and validation as first steps
2. **Execution checklist** - Memory check is step #1 (MANDATORY)
3. **This protocol document** - User can reference to hold me accountable

### Social Enforcement
- User can interrupt me at any time if I skip steps
- User can ask "did you follow the protocol?"
- This document is version controlled - user can track if I update it

---

## Example: Correct Workflow

```
User: "Deploy calculator Lambda to dev"

Claude Response:
"Let me deploy calculator Lambda to dev environment.

Step 1: Checking memory for lessons learned...
[Tool: Read ~/.claude/memory/MEMORY.md]
Found relevant lessons:
- deployment_local_testing_requirement_2026-04-04.md
- deployment_lambda_packaging_lesson.md

Step 2: Running pre-deployment validation...
[Tool: ./scripts/pre-deploy-validation.sh calculator]
✅ ALL VALIDATIONS PASSED

Step 3: Proceeding with deployment...
[Tool: ./scripts/deploy.sh dev calculator]
✅ Deployment successful

Step 4: Post-deployment validation...
[Tool: aws lambda invoke ...]
✅ Lambda working correctly: 25 + 17 = 42
"
```

---

## Example: What Happens If I Skip Steps

**Scenario:** I try to deploy without validation

```
User: "Deploy calculator Lambda"

Claude (incorrectly): 
"Deploying..."
[Tool: cdk deploy CalculatorStack-dev]

User: "STOP! Did you check memory? Did you run pre-deploy-validation?"

Claude: "You're right - I did not follow the protocol. Let me start over:

Step 1: Checking memory...
[Tool: Read memory files]

Step 2: Running validation...
[Tool: ./scripts/pre-deploy-validation.sh calculator]
❌ VALIDATION FAILED - package missing dependencies

I should have caught this before deploying. Fixing now..."
```

---

## Metrics: How to Measure I'm Following Protocol

### Success Metrics
- **100%** of deployments start with memory check
- **100%** of deployments run pre-deploy-validation
- **0** deployments without local testing
- **0** repeated mistakes from documented lessons

### User Can Track
Check these in conversation history:
1. Count how many times I deployed without mentioning memory check
2. Count how many times validation was skipped
3. Count how many times I repeated a documented mistake

**Target:** 0 for all of the above

---

## Enforcement for New Lambda Functions

When creating new Lambda functions, the following enforcement applies:

### Technical Enforcement
1. **Scaffolding script** - Creates Lambda with all enforcement built-in
2. **Template requirements.txt** - Ensures HTTP exporter and boto3 included
3. **Template build script** - Ensures Docker build with x86_64
4. **Pre-deploy validation** - Works for any Lambda name (generic)

### Process Enforcement
1. **NEW-LAMBDA-CHECKLIST.md** - 10-step mandatory checklist
2. **Deployment skill** - References checklist for new Lambdas
3. **Memory protocol** - Mandates scaffolding script (this section)

### Verification Methods
```bash
# Verify Lambda created with scaffold
ls backend/lambdas/<name>/build-in-docker.sh  # Should exist
grep "http" backend/lambdas/<name>/requirements.txt  # Should have HTTP exporter
grep "boto3" backend/lambdas/<name>/requirements.txt  # Should have boto3

# Verify validation works
./scripts/pre-deploy-validation.sh <name>  # Should pass all checks
```

---

## Updates to This Protocol

This protocol can be updated, but:
1. Updates must be **additive** (more checks, not fewer)
2. Updates must be **documented** in git history
3. User can reject updates that weaken enforcement
4. User can demand stricter protocols

---

## Commitment Statement

I commit to following this protocol for every deployment. If I fail to follow it:

1. User can interrupt me
2. User can ask me to restart from Step 1
3. User can point to this document and demand I follow it
4. User can update this document to add stricter requirements

This is a **binding contract** between me (Claude Code) and the user, enforced by:
- Technical scripts that block bad deployments
- Process documentation that mandates checks
- User's ability to hold me accountable

---

**Signed:** Claude Code (Sonnet 4.5)
**Date:** 2026-04-04
**Version:** 1.0
**Verified by:** Pre-deployment validation passing for calculator Lambda
