#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/aws_setup.sh
#
# One-time AWS infrastructure setup for EU Regulatory Intelligence Agent.
# Run this ONCE from your local machine with AWS CLI configured.
#
# Prerequisites:
#   - AWS CLI installed and configured: aws configure
#   - IAM user with: AmazonEC2ContainerRegistryFullAccess, AmazonECS_FullAccess,
#                    SecretsManagerReadWrite
#   - Your .env file filled in
#
# Usage:
#   chmod +x scripts/aws_setup.sh
#   source .env && bash scripts/aws_setup.sh
#
# After running:
#   1. Update ecs-task-definition.json with your ACCOUNT_ID
#   2. Register the task definition: 
#      aws ecs register-task-definition --cli-input-json file://scripts/ecs-task-definition.json
#   3. Create the ECS service (see bottom of this script)
#   4. Add all secrets as GitHub repository secrets
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REGION="eu-north-1"
ECR_REPO="eu-reg-agent"
ECS_CLUSTER="eu-reg-agent"
ECS_SERVICE="eu-reg-agent-service"
LOG_GROUP="/ecs/eu-reg-agent"
SECRET_PREFIX="research-agent"

echo "═══════════════════════════════════════════════════════════"
echo "EU Regulatory Intelligence Agent — AWS Setup"
echo "Region: $REGION"
echo "═══════════════════════════════════════════════════════════"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $ACCOUNT_ID"

# ── 1. ECR Repository ────────────────────────────────────────────────────────
echo ""
echo "[1/5] Creating ECR repository..."
aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --region "$REGION" \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null && echo "  ✓ ECR repo created" || echo "  → Already exists"

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO"
echo "  ECR URI: $ECR_URI"

# ── 2. CloudWatch Log Group ───────────────────────────────────────────────────
echo ""
echo "[2/5] Creating CloudWatch log group..."
aws logs create-log-group \
  --log-group-name "$LOG_GROUP" \
  --region "$REGION" \
  2>/dev/null && echo "  ✓ Log group created" || echo "  → Already exists"

# Retain logs for 30 days
aws logs put-retention-policy \
  --log-group-name "$LOG_GROUP" \
  --retention-in-days 30 \
  --region "$REGION"
echo "  ✓ Log retention: 30 days"

# ── 3. Secrets Manager ───────────────────────────────────────────────────────
echo ""
echo "[3/5] Storing API keys in Secrets Manager..."

store_secret() {
  local name="$1"
  local value="$2"
  local full_name="$SECRET_PREFIX/$name"

  if aws secretsmanager describe-secret --secret-id "$full_name" --region "$REGION" &>/dev/null; then
    aws secretsmanager put-secret-value \
      --secret-id "$full_name" \
      --secret-string "$value" \
      --region "$REGION" > /dev/null
    echo "  ✓ Updated: $full_name"
  else
    aws secretsmanager create-secret \
      --name "$full_name" \
      --secret-string "$value" \
      --region "$REGION" > /dev/null
    echo "  ✓ Created: $full_name"
  fi
}

# These read from your sourced .env file
store_secret "anthropic-key"      "${ANTHROPIC_API_KEY:-MISSING}"
store_secret "openai-key"         "${OPENAI_API_KEY:-MISSING}"
store_secret "supabase-url"       "${SUPABASE_URL:-MISSING}"
store_secret "supabase-service-key" "${SUPABASE_SERVICE_KEY:-MISSING}"
store_secret "supabase-anon-key"  "${SUPABASE_ANON_KEY:-MISSING}"
store_secret "tavily-key"         "${TAVILY_API_KEY:-MISSING}"
store_secret "langchain-key"      "${LANGCHAIN_API_KEY:-MISSING}"

# ── 4. ECS Cluster ───────────────────────────────────────────────────────────
echo ""
echo "[4/5] Creating ECS cluster..."
aws ecs create-cluster \
  --cluster-name "$ECS_CLUSTER" \
  --capacity-providers FARGATE FARGATE_SPOT \
  --region "$REGION" \
  --settings name=containerInsights,value=enabled \
  > /dev/null 2>&1 && echo "  ✓ ECS cluster created" || echo "  → Already exists"

# ── 5. First Docker push (manual — needs ECR login) ──────────────────────────
echo ""
echo "[5/5] First image build and push..."
echo "  Run these commands to push your first image:"
echo ""
echo "  aws ecr get-login-password --region $REGION | \\"
echo "    docker login --username AWS --password-stdin $ECR_URI"
echo ""
echo "  docker build -t $ECR_URI:latest ."
echo "  docker push $ECR_URI:latest"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Setup complete. Next steps:"
echo ""
echo "1. Replace {ACCOUNT_ID} in scripts/ecs-task-definition.json with:"
echo "   $ACCOUNT_ID"
echo ""
echo "2. Register task definition:"
echo "   aws ecs register-task-definition \\"
echo "     --cli-input-json file://scripts/ecs-task-definition.json \\"
echo "     --region $REGION"
echo ""
echo "3. Build and push first image (commands above in step 5)"
echo ""
echo "4. Create ECS service:"
echo "   aws ecs create-service \\"
echo "     --cluster $ECS_CLUSTER \\"
echo "     --service-name $ECS_SERVICE \\"
echo "     --task-definition eu-reg-agent-task \\"
echo "     --desired-count 1 \\"
echo "     --launch-type FARGATE \\"
echo "     --network-configuration 'awsvpcConfiguration={subnets=[YOUR_SUBNET_ID],securityGroups=[YOUR_SG_ID],assignPublicIp=ENABLED}' \\"
echo "     --region $REGION"
echo ""
echo "5. Add to GitHub repository secrets:"
echo "   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
echo "   ECR_REGISTRY=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
echo "   ECR_REPOSITORY=$ECR_REPO"
echo "   ECS_CLUSTER=$ECS_CLUSTER"
echo "   ECS_SERVICE=$ECS_SERVICE"
echo "   + all API keys"
echo "═══════════════════════════════════════════════════════════"
