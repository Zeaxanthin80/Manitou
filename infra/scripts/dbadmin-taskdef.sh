#!/usr/bin/env bash
#
# Register a fresh `manitou-dbadmin` task definition revision and print its ARN.
#
# **Why a second task definition exists at all.** After defect 30 the API runs as
# `manitou_app`, a role with no DDL rights -- which is the point. But Alembic
# needs DDL, so migrations cannot run on the API's task definition any more.
# This one carries the MASTER credentials and nothing else differs.
#
# The alternative was to put both credential sets on the API's own task
# definition and pick between them at runtime. That was rejected: it would leave
# the master password in the API container's environment, so anything that could
# read that container's environment would have superuser on the database. The
# whole reason for defect 30's fix is that the API should not hold those rights,
# and a variable it never reads is still a variable it holds.
#
# **The image is derived, never pinned.** A static task definition would run
# migrations with whatever image was current the day it was written -- which is
# exactly backwards, since a migration must match the code being deployed. So
# this reads the live service's container spec on every run and registers a new
# revision. Same reasoning as `.github/scripts/deploy.sh`: derive the container
# spec, do not retype it.
#
# Usage:  infra/scripts/dbadmin-taskdef.sh
#         (called automatically by run_in_vpc.sh and migrate.sh)

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
FAMILY=manitou-dbadmin
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# --- what the live API service is running right now -------------------------
LIVE=$(aws ecs describe-express-gateway-service --region "$REGION" \
         --service-arn "arn:aws:ecs:$REGION:$ACCOUNT:service/default/manitou-api" \
         --query 'service.activeConfigurations[0].primaryContainer')

# --- the roles and log group, taken from the API's own task definition -------
API_TD=$(aws ecs describe-task-definition --region "$REGION" \
           --task-definition default-manitou-api --query 'taskDefinition')

# --- the two secrets, resolved rather than hardcoded -------------------------
# The RDS-managed secret's name contains a UUID generated at instance creation,
# so writing it down here would be writing down an identifier that only this one
# account has. DescribeDBInstances knows it.
RDS_SECRET=$(aws rds describe-db-instances --region "$REGION" \
               --db-instance-identifier manitou-db \
               --query 'DBInstances[0].MasterUserSecret.SecretArn' --output text)
API_SECRET=$(aws secretsmanager describe-secret --region "$REGION" \
               --secret-id manitou/api --query 'ARN' --output text)

# --- assemble ----------------------------------------------------------------
# Start from the live container, then replace the database identity. Everything
# else -- image, log configuration, the Stripe and JWT secrets that app.config
# requires at import time -- is carried across unchanged, because a task that
# cannot import app.config cannot run a migration either.
CONTAINER=$(jq -n \
  --argjson live "$LIVE" \
  --argjson apitd "$API_TD" \
  --arg rds_secret "$RDS_SECRET" \
  --arg api_secret "$API_SECRET" '
  ($apitd.containerDefinitions[0]) as $base |
  {
    name: "Main",
    image: $live.image,
    essential: true,
    logConfiguration: $base.logConfiguration,
    environment: (
      ($base.environment // [])
      | map(select(.name != "DB_USER"))
      | . + [{name: "DB_USER", value: "manitou"}]
    ),
    secrets: (
      ($base.secrets // [])
      | map(select(.name != "DB_PASSWORD" and .name != "DB_APP_PASSWORD"))
      | . + [
          {name: "DB_PASSWORD",     valueFrom: ($rds_secret + ":password::")},
          {name: "DB_APP_PASSWORD", valueFrom: ($api_secret + ":db_app_password::")}
        ]
    )
  }')

# Fail loudly rather than register something malformed. A task definition with a
# null image registers happily and fails minutes later as an image pull error.
echo "$CONTAINER" | jq -e '
  .image != null and (.image | test(":")) and
  ((.environment | map(select(.name == "DB_USER")) | .[0].value) == "manitou") and
  ((.secrets | map(.name) | sort) | index("DB_PASSWORD") != null) and
  ((.secrets | map(.name) | sort) | index("DB_APP_PASSWORD") != null)
' > /dev/null || { echo "::error::assembled container spec failed its sanity check" >&2; exit 1; }

ARN=$(aws ecs register-task-definition --region "$REGION" \
  --family "$FAMILY" \
  --requires-compatibilities FARGATE \
  --network-mode awsvpc \
  --cpu "$(echo "$API_TD" | jq -r '.cpu')" \
  --memory "$(echo "$API_TD" | jq -r '.memory')" \
  --execution-role-arn "$(echo "$API_TD" | jq -r '.executionRoleArn')" \
  --task-role-arn "$(echo "$API_TD" | jq -r '.taskRoleArn')" \
  --runtime-platform "$(echo "$API_TD" | jq -c '.runtimePlatform')" \
  --container-definitions "[$CONTAINER]" \
  --query 'taskDefinition.taskDefinitionArn' --output text)

echo "$ARN"
