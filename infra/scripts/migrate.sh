#!/usr/bin/env bash
#
# Run Alembic against the production database, as a one-off ECS task.
#
# **Why this exists.** RDS is private: it has no public IP and its endpoint
# resolves only inside the VPC, so `alembic upgrade head` from a laptop cannot
# reach it and neither can a GitHub Actions runner. Something already inside the
# VPC has to run it, and the API's own task definition is already exactly that --
# same image, same subnets, same security group, same DB_PASSWORD from Secrets
# Manager. Only the lifecycle differs: run once and exit, rather than serve.
#
# No separate image is needed. `backend/Dockerfile.dockerignore` excludes
# `backend/tests/` but not `backend/alembic/`, so the production image carries
# alembic.ini, every migration, and the CLI.
#
# **The exit code is the whole point.** `aws ecs run-task` returns as soon as the
# task is ACCEPTED -- long before it has connected to anything. A script that
# stopped there would report success for a migration that failed to apply, which
# is worse than no automation: it teaches you to trust a signal wired to nothing.
# The same trap as UpdateExpressGatewayService returning before its canary
# decides. See defect 29.
#
# Usage:
#   infra/scripts/migrate.sh                  # alembic upgrade head
#   infra/scripts/migrate.sh current          # any other alembic subcommand
#   infra/scripts/migrate.sh downgrade -1

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER=default
FAMILY=default-manitou-api
CONTAINER=Main          # the task definition's only container; it has no
                        # entryPoint, so a plain command override is enough

# Default to the operation that is almost always wanted.
if [ "$#" -eq 0 ]; then set -- upgrade head; fi

# The LATEST revision, resolved rather than pinned. Pinning would run migrations
# with whatever image was current when this script was written -- which is the
# opposite of what a migration wants, since it must match the code being deployed.
TASK_DEF=$(aws ecs describe-task-definition --region "$REGION" \
             --task-definition "$FAMILY" \
             --query 'taskDefinition.taskDefinitionArn' --output text)
echo "  task definition: ${TASK_DEF##*/}"
echo "  command:         alembic $*"

# Networking copied from the running service, not hardcoded. assignPublicIp is
# ENABLED because this VPC has no NAT gateway and no VPC endpoints: the public IP
# on the task's ENI is its only route to ECR to pull the image, and to Secrets
# Manager to read DB_PASSWORD. Without it the task never starts, and the failure
# looks like a mysterious timeout rather than a missing route.
NET=$(aws ecs describe-express-gateway-service --region "$REGION" \
        --service-arn "arn:aws:ecs:$REGION:$(aws sts get-caller-identity --query Account --output text):service/$CLUSTER/manitou-api" \
        --query 'service.activeConfigurations[0].networkConfiguration' \
        | jq '{awsvpcConfiguration: (. + {assignPublicIp: "ENABLED"})}')

OVERRIDES=$(jq -nc --arg name "$CONTAINER" --args '
  {containerOverrides: [{name: $name, command: (["alembic"] + $ARGS.positional)}]}' "$@")

TASK_ARN=$(aws ecs run-task --region "$REGION" \
  --cluster "$CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEF" \
  --network-configuration "$NET" \
  --overrides "$OVERRIDES" \
  --started-by "migrate.sh/$(whoami)" \
  --query 'tasks[0].taskArn' --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
  echo "::error::run-task returned no task ARN"; exit 1
fi
echo "  task:            ${TASK_ARN##*/}"

echo "  waiting for it to stop ..."
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN"

read -r EXIT_CODE STOP_REASON < <(
  aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN" \
    --query 'tasks[0].[containers[0].exitCode, stoppedReason]' --output text
)

# The container's log stream, so a failure is one command away rather than a hunt
# through the console.
LOG_GROUP=$(aws ecs describe-task-definition --region "$REGION" --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text)
LOG_PREFIX=$(aws ecs describe-task-definition --region "$REGION" --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-stream-prefix"' --output text)
STREAM="$LOG_PREFIX/$CONTAINER/${TASK_ARN##*/}"

echo "  ---- output ----"
aws logs get-log-events --region "$REGION" \
  --log-group-name "$LOG_GROUP" --log-stream-name "$STREAM" \
  --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' | sed 's/^/  /' \
  || echo "  (no log stream yet: $STREAM)"
echo "  ----------------"

# "None" comes back when the container never started at all -- an image pull
# failure or a missing secret. That is a failure, and it is not exit code 0.
if [ "$EXIT_CODE" != "0" ]; then
  echo "::error::alembic exited with '$EXIT_CODE' (stoppedReason: $STOP_REASON)"
  exit 1
fi
echo "  alembic $* completed (exit 0)"
