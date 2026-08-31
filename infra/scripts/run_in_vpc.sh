#!/usr/bin/env bash
#
# Run a .sql or .py file against the production database, inside the VPC.
#
# **Why this exists.** RDS is private (see infra/README.md, "Making RDS private").
# There is no psql from a laptop and no bastion, by decision. Anything that needs
# to talk to the database has to run inside the VPC, and the API's own image is
# already exactly that: same subnets, same security group, same credentials from
# Secrets Manager. Only the lifecycle differs -- run once and exit.
#
# This is `migrate.sh` generalised. That script runs one command (alembic); this
# one runs a file, so role grants, refusal tests and one-off diagnostics are
# reviewable artifacts in the repository rather than shell history.
#
# **Nothing secret is ever passed on the command line.** Container overrides are
# returned by DescribeTasks and recorded by CloudTrail, so a password in an
# override is a password in an audit log for 90 days. Scripts that need a
# credential either read it from the environment (which ECS populates from
# Secrets Manager, resolved per task) or generate it in-process and never emit
# it. The file's TEXT is passed as an override, so the file itself must contain
# no secrets -- only references to them.
#
# **The exit code is the whole point**, exactly as in migrate.sh: `aws ecs
# run-task` returns as soon as the task is ACCEPTED, long before it has connected
# to anything. Reporting success there would teach you to trust a signal wired to
# nothing. See defect 29.
#
# Usage:
#   infra/scripts/run_in_vpc.sh infra/sql/create_app_role.sql
#   infra/scripts/run_in_vpc.sh infra/probes/rotation_mechanism.py
#
#   TASK_FAMILY=manitou-dbadmin infra/scripts/run_in_vpc.sh <file>
#       Run on the admin task definition, which carries the MASTER credentials.
#       The API's own family runs as manitou_app and cannot execute DDL.

set -euo pipefail

FILE="${1:?usage: run_in_vpc.sh <file.sql|file.py>}"
[ -r "$FILE" ] || { echo "::error::cannot read $FILE"; exit 1; }

REGION="${AWS_REGION:-us-east-1}"
CLUSTER=default
FAMILY="${TASK_FAMILY:-default-manitou-api}"
CONTAINER=Main          # the task definition's only container; it has no
                        # entryPoint, so a plain command override is enough

# The runner, chosen by extension.
#
# A .sql file goes through the raw DBAPI cursor rather than SQLAlchemy's text(),
# for two reasons: psycopg2 executes a multi-statement string in one call, so the
# file needs no statement splitting (which is unparseable in general -- semicolons
# live inside dollar-quoted function bodies, which this schema HAS, in the
# audit_events trigger); and AUTOCOMMIT lets a file mix DDL freely without one
# failed statement silently rolling back the ones before it.
case "$FILE" in
  *.sql)
    RUNNER='
import os, sys
from sqlalchemy import create_engine
sys.path.insert(0, "/app/backend")
from app.config import settings
e = create_engine(settings.database_url)
raw = e.raw_connection()
raw.autocommit = True
cur = raw.cursor()
cur.execute(os.environ["PAYLOAD"])
if cur.description:
    print("\t".join(c.name for c in cur.description))
    for row in cur.fetchall():
        print("\t".join("" if v is None else str(v) for v in row))
print("OK")
'
    ;;
  *.py)
    # exec rather than a temp file: the payload arrives in the environment, and
    # writing it to disk in the container adds a path with no reader.
    RUNNER='
import os, sys
sys.path.insert(0, "/app/backend")
exec(compile(os.environ["PAYLOAD"], "payload", "exec"))
'
    ;;
  *)
    echo "::error::$FILE must end in .sql or .py"; exit 1 ;;
esac

if [ "$FAMILY" = "manitou-dbadmin" ]; then
  # Registered fresh on every run, so the image always matches what is deployed.
  # See dbadmin-taskdef.sh for why this is not a static definition.
  TASK_DEF=$("$(dirname "$0")/dbadmin-taskdef.sh")
else
  TASK_DEF=$(aws ecs describe-task-definition --region "$REGION" \
               --task-definition "$FAMILY" \
               --query 'taskDefinition.taskDefinitionArn' --output text)
fi
echo "  task definition: ${TASK_DEF##*/}"
echo "  file:            $FILE"

# Networking copied from the running service, not hardcoded. assignPublicIp is
# ENABLED because this VPC has no NAT gateway and no VPC endpoints: the public IP
# on the task's ENI is its only route to ECR to pull the image and to Secrets
# Manager to read the credentials. Without it the task never starts, and the
# failure looks like a mysterious timeout rather than a missing route.
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
NET=$(aws ecs describe-express-gateway-service --region "$REGION" \
        --service-arn "arn:aws:ecs:$REGION:$ACCOUNT:service/$CLUSTER/manitou-api" \
        --query 'service.activeConfigurations[0].networkConfiguration' \
        | jq '{awsvpcConfiguration: (. + {assignPublicIp: "ENABLED"})}')

# Extra environment for the payload, opted into one variable at a time:
#
#     TASK_ENV_REMOVE=1 run_in_vpc.sh infra/tasks/seed_loadtest_catalog.py
#
# arrives in the container as REMOVE=1. The prefix is a deliberate allowlist --
# the caller's environment is never forwarded wholesale, because these values go
# into a container override, and overrides are returned by DescribeTasks and
# recorded by CloudTrail for 90 days. Never put a credential here.
#
# This exists because it was missing: a REMOVE=1 in the caller's shell silently
# did nothing, and the script it was driving took the other branch and reported
# success. An env var that is ignored rather than rejected is the worst kind.
EXTRA_ENV=$(jq -nc '
  [env | to_entries[]
   | select(.key | startswith("TASK_ENV_"))
   | {name: (.key | ltrimstr("TASK_ENV_")), value: .value}]')

FORWARDED=$(echo "$EXTRA_ENV" | jq -r 'map(.name) | join(", ")')
[ -n "$FORWARDED" ] && echo "  forwarding env:  $FORWARDED"

OVERRIDES=$(jq -nc \
  --arg name "$CONTAINER" \
  --arg runner "$RUNNER" \
  --arg payload "$(cat "$FILE")" \
  --argjson extra "$EXTRA_ENV" '
  {containerOverrides: [{
     name: $name,
     command: ["python", "-c", $runner],
     environment: ([{name: "PAYLOAD", value: $payload}] + $extra)
   }]}')

TASK_ARN=$(aws ecs run-task --region "$REGION" \
  --cluster "$CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEF" \
  --network-configuration "$NET" \
  --overrides "$OVERRIDES" \
  --started-by "run_in_vpc/$(whoami)" \
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

LOG_GROUP=$(aws ecs describe-task-definition --region "$REGION" --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text)
LOG_PREFIX=$(aws ecs describe-task-definition --region "$REGION" --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-stream-prefix"' --output text)
STREAM="$LOG_PREFIX/$CONTAINER/${TASK_ARN##*/}"

echo "  ---- output ----"
aws logs get-log-events --region "$REGION" \
  --log-group-name "$LOG_GROUP" --log-stream-name "$STREAM" --start-from-head \
  --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' | sed 's/^/  /' \
  || echo "  (no log stream yet: $STREAM)"
echo "  ----------------"

# "None" comes back when the container never started at all -- an image pull
# failure or a missing secret. That is a failure, and it is not exit code 0.
if [ "$EXIT_CODE" != "0" ]; then
  echo "::error::$FILE exited with '$EXIT_CODE' (stoppedReason: $STOP_REASON)"
  exit 1
fi
echo "  $FILE completed (exit 0)"
