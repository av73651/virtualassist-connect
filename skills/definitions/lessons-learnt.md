# Lessons Learnt Skill - Continuous Learning from Failures

## Directive
This skill analyzes execution failures, root causes, and resolutions, then creates persistent memory records to prevent repeating the same mistakes in future sessions.

**Primary Goal**: Build institutional knowledge by documenting what went wrong, why it happened, and how to prevent it from happening again.

---

## 1. WHEN TO USE THIS SKILL

### Trigger Conditions
- ✅ After resolving a significant deployment failure
- ✅ After multiple iterations to fix the same issue
- ✅ When discovering a non-obvious solution
- ✅ After the user corrects your approach
- ✅ When a task takes >30 minutes due to mistakes
- ✅ When the same error pattern occurs multiple times

### DO NOT Use For
- ❌ Expected errors (e.g., test failures during development)
- ❌ User-requested changes (not mistakes)
- ❌ One-time environmental issues (network timeouts)
- ❌ Issues already documented in memory

---

## 2. FAILURE ANALYSIS FRAMEWORK

### Step 1: Incident Timeline
Document the sequence of events:
```
1. What was attempted?
2. What failed?
3. What was tried to fix it? (all attempts)
4. What finally worked?
5. How long did it take?
```

### Step 2: Root Cause Analysis
Identify the **true** root cause (not symptoms):
- **Technical Root Cause**: Missing dependency, wrong configuration, IAM permission
- **Process Root Cause**: Didn't validate before deploying, assumed incorrectly
- **Knowledge Gap**: Didn't understand how X works, missed documentation

### Step 3: Impact Assessment
- **Time Lost**: How many minutes/hours were wasted?
- **Deployment Failures**: How many failed deployments?
- **Iterations**: How many attempts to fix?
- **User Frustration**: Did the user express frustration?

### Step 4: Prevention Strategy
- What validation check would have caught this?
- What documentation should be created/updated?
- What tool/script enhancement is needed?
- What assumption should never be made again?

---

## 3. MEMORY CREATION PROCESS

### Memory File Structure
Create a memory file in `~/.claude/projects/-Users-rameshnagarajan/memory/`:

```markdown
---
name: {Short title describing the lesson}
description: {One-line summary for relevance matching}
type: feedback
---

## Rule: {What should be done differently}

**Why:** {Explanation of the problem and root cause}

**How to apply:** {When this rule applies and how to implement it}

---

## Incident Details

**Date:** {YYYY-MM-DD}
**Time Lost:** ~{X} minutes
**Iterations:** {N} attempts

**What Happened:**
{Detailed timeline of the failure}

**Root Cause:**
{True root cause, not symptoms}

**Solution:**
{What finally fixed it}

**Prevention:**
- [ ] Validation check: {specific check}
- [ ] Documentation: {what to update}
- [ ] Tool enhancement: {script/skill improvement}
- [ ] Never assume: {wrong assumption}

---

## Example Scenario

**Correct Approach:**
\`\`\`bash
# Step 1: Validate
{validation command}

# Step 2: Deploy
{deployment command}

# Step 3: Test
{test command}
\`\`\`

**Incorrect Approach (DO NOT DO):**
\`\`\`bash
# Deploying without validation
{what NOT to do}
\`\`\`
```

### Step-by-Step Memory Creation

1. **Analyze the failure** using the framework above
2. **Create memory file** with descriptive name: `{category}_{problem}_{date}.md`
3. **Update MEMORY.md index** with one-line pointer
4. **Update relevant skills** with troubleshooting section
5. **Update scripts** with validation checks (if applicable)
6. **Commit changes** with detailed commit message

---

## 4. RECENT LESSONS LEARNED (EXAMPLES)

### Example 1: Custom Metrics IAM Permission Failure (2026-04-04)

**Incident:** Custom CloudWatch metrics not appearing despite boto3 being installed

**Root Cause:** IAM policy had a condition `cloudwatch:namespace = CustomMetrics/*` which doesn't work with PutMetricData API because namespace isn't evaluated during IAM authorization.

**Time Lost:** ~60 minutes

**Solution:** 
1. Removed IAM condition from policy
2. Updated observability middleware to emit metrics with AND without dimensions
3. Added boto3 to requirements.txt

**Prevention:**
- ✅ Test IAM policies with actual API calls
- ✅ Never use IAM conditions on cloudwatch:PutMetricData
- ✅ Always emit custom metrics without dimensions for alarm aggregation

**Memory File:** `observability_custom_metrics_iam_2026-04-04.md`

---

### Example 2: Lambda Packaging Missing Dependencies (2026-04-04)

**Incident:** Lambda deployed successfully but failed at runtime with ImportError

**Root Cause:** Only copied `src/` and `shared/` directories without pip dependencies

**Time Lost:** ~30 minutes

**Solution:**
```bash
pip3 install -r requirements.txt -t package/ \\
  --platform manylinux2014_x86_64 \\
  --only-binary=:all: \\
  --python-version 3.12
cp -r src package/
cp -r shared package/
```

**Prevention:**
- ✅ Validate package contains dependencies before deploying
- ✅ Check package size (should be >10MB with dependencies)
- ✅ Test Lambda invocation immediately after deployment

**Memory File:** `deployment_lambda_packaging_lesson.md` (already exists)

---

## 5. SKILL EXECUTION CHECKLIST

When invoking this skill:

- [ ] **Collect failure timeline** - What happened, when, how many attempts?
- [ ] **Identify root cause** - Why did it fail? (technical + process)
- [ ] **Calculate impact** - Time lost, iterations, deployment failures
- [ ] **Define prevention** - What validation/check/documentation needed?
- [ ] **Create memory file** - Use template above with specific details
- [ ] **Update MEMORY.md** - Add one-line pointer to new memory
- [ ] **Update relevant skills** - Add troubleshooting section if applicable
- [ ] **Update scripts** - Add validation checks if applicable
- [ ] **Commit changes** - Detailed commit message explaining the lesson

---

## 6. MEMORY FILE NAMING CONVENTION

Format: `{category}_{specific_problem}_{date}.md`

**Categories:**
- `deployment_` - Deployment-related failures
- `observability_` - Monitoring/metrics/tracing issues
- `iam_` - IAM permission problems
- `build_` - Build/packaging errors
- `config_` - Configuration mistakes
- `integration_` - Integration test failures
- `process_` - Workflow/process improvements

**Examples:**
- `deployment_lambda_packaging_lesson.md`
- `observability_custom_metrics_iam_2026-04-04.md`
- `iam_cross_account_assume_role_2026-04-05.md`
- `build_python_version_mismatch_2026-04-03.md`

---

## 7. INTEGRATION WITH OTHER SKILLS

**Use After:**
- `/deployment` - If deployment failed multiple times
- `/code-review` - If review found repeated mistakes
- `/test-generation` - If tests revealed knowledge gaps

**Updates:**
- Update `/deployment` skill troubleshooting section
- Update `scripts/deploy.sh` with validation checks
- Update `docs/CONTINUOUS-LEARNING.md` with new lessons
- Update relevant architecture patterns if needed

---

## 8. SUCCESS METRICS

Track effectiveness of lessons-learnt:
- **Zero Repeats**: No mistake repeated after memory created
- **Time Savings**: Avoid 30-60 min troubleshooting per incident
- **Faster Resolution**: Issues resolved in <5 min vs 30+ min
- **Knowledge Transfer**: New Claude sessions learn from past mistakes

---

## 9. PROMPT TEMPLATE FOR INVOKING THIS SKILL

When user says: *"Analyze your learnings and create a memory so we avoid repeating this"*

**Response:**
1. Acknowledge the failure and apologize if appropriate
2. Provide incident timeline with root cause
3. Calculate time/impact metrics
4. Create memory file using template
5. Update MEMORY.md index
6. Update relevant skills/scripts
7. Commit all changes
8. Summarize what was learned and how it will prevent future issues

---

## 10. CONTINUOUS IMPROVEMENT

This skill itself should evolve:
- Add new failure categories as they're discovered
- Refine root cause analysis techniques
- Improve memory searchability
- Track which lessons are most frequently referenced
- Identify patterns across multiple incidents

---

**Remember:** The goal is not just to fix the current issue, but to ensure it NEVER happens again in any future session.
