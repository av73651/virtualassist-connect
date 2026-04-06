#!/bin/bash
# Migration script: incident-manager/jira-credentials → sre-platform/jira-credentials
# This script copies the existing Jira credentials to the new secret name

set -e

REGION="${AWS_REGION:-us-west-2}"
OLD_SECRET="incident-manager/jira-credentials"
NEW_SECRET="sre-platform/jira-credentials"

echo "=== AWS Secrets Manager Migration ==="
echo "Region: $REGION"
echo "Old secret: $OLD_SECRET"
echo "New secret: $NEW_SECRET"
echo ""

# Check if old secret exists
echo "Checking if old secret exists..."
if ! aws secretsmanager describe-secret --secret-id "$OLD_SECRET" --region "$REGION" &>/dev/null; then
    echo "ERROR: Old secret '$OLD_SECRET' does not exist in region $REGION"
    echo "Please create the secret first or verify the region is correct."
    exit 1
fi

echo "✓ Old secret exists"
echo ""

# Retrieve old secret value
echo "Retrieving old secret value..."
OLD_SECRET_VALUE=$(aws secretsmanager get-secret-value \
    --secret-id "$OLD_SECRET" \
    --region "$REGION" \
    --query 'SecretString' \
    --output text)

if [ -z "$OLD_SECRET_VALUE" ]; then
    echo "ERROR: Could not retrieve old secret value"
    exit 1
fi

echo "✓ Old secret value retrieved"
echo ""

# Check if new secret already exists
echo "Checking if new secret already exists..."
if aws secretsmanager describe-secret --secret-id "$NEW_SECRET" --region "$REGION" &>/dev/null 2>&1; then
    echo "WARNING: New secret '$NEW_SECRET' already exists!"
    echo "Do you want to update it with the value from '$OLD_SECRET'? (yes/no)"
    read -r response
    if [ "$response" != "yes" ]; then
        echo "Aborted. No changes made."
        exit 0
    fi

    # Update existing secret
    echo "Updating existing secret..."
    aws secretsmanager update-secret \
        --secret-id "$NEW_SECRET" \
        --secret-string "$OLD_SECRET_VALUE" \
        --region "$REGION"

    echo "✓ Secret updated successfully"
else
    # Create new secret
    echo "Creating new secret..."
    aws secretsmanager create-secret \
        --name "$NEW_SECRET" \
        --description "Jira API credentials for SRE platform incident management" \
        --secret-string "$OLD_SECRET_VALUE" \
        --region "$REGION" \
        --tags Key=Platform,Value=SRE Key=Environment,Value=dev

    echo "✓ New secret created successfully"
fi

echo ""
echo "=== Migration Complete ==="
echo ""
echo "Next steps:"
echo "1. Verify the new secret works:"
echo "   aws secretsmanager get-secret-value --secret-id '$NEW_SECRET' --region '$REGION'"
echo ""
echo "2. Deploy updated Lambda functions that reference the new secret name"
echo ""
echo "3. After verifying everything works, optionally delete the old secret:"
echo "   aws secretsmanager delete-secret --secret-id '$OLD_SECRET' --region '$REGION' --recovery-window-in-days 7"
echo ""
echo "Note: The old secret will be kept for 7 days recovery window (AWS minimum)"
