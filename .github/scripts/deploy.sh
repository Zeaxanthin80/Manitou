#!/usr/bin/env bash
#
# Deploy a tag to both Express Mode services and wait for the result.
#
# Kept out of deploy.yml because it is real logic with real failure modes, and
# YAML is a bad place to read a loop. It can also be run by hand, which is what
# you want at 2am when the pipeline is the thing that is broken.
#
# **The whole point of this script is that it fails when the deployment fails.**
# UpdateExpressGatewayService returns success as soon as the request is accepted,
# minutes before the canary decides anything. A job that stops there reports green
# for a rollout that ECS is about to revert -- which is worse than no automation,
# because it teaches you to trust a signal that is not connected to the outcome.
#
# Usage: deploy.sh <image-tag>

set -euo pipefail

TAG="${1:?usage: deploy.sh <image-tag>}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="739275454344"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
SERVICES=(manitou-api manitou-web)

# Two canaries at ~7 minutes each, plus room for a slow start.
DEADLINE=$(( $(date +%s) + 25 * 60 ))

svc_arn() { echo "arn:aws:ecs:$REGION:$ACCOUNT:service/default/$1"; }

running_tag() {  # every distinct image tag currently RUNNING for a service
  local tasks
  tasks=$(aws ecs list-tasks --region "$REGION" --cluster default \
            --service-name "$1" --query 'taskArns' --output text)
  [ -z "$tasks" ] && { echo ""; return; }
  aws ecs describe-tasks --region "$REGION" --cluster default --tasks $tasks \
    --query 'tasks[?lastStatus==`RUNNING`].containers[0].image' --output text \
    | tr '\t' '\n' | sed 's/.*://' | sort -u | tr '\n' ' '
}

configured_tag() {  # what the service says it should be running
  aws ecs describe-express-gateway-service --region "$REGION" \
    --service-arn "$(svc_arn "$1")" \
    --query 'service.activeConfigurations[0].primaryContainer.image' \
    --output text | sed 's/.*://'
}

# ---------------------------------------------------------------------------
# Refuse to start into a breaching rollback alarm.
#
# Deploying while it is already in ALARM gets the new revision reverted within
# minutes, and the post-mortem blames the image. The alarm is usually breaching
# for a reason that has nothing to do with the code -- see defect 29.
# ---------------------------------------------------------------------------
for s in "${SERVICES[@]}"; do
  state=$(aws cloudwatch describe-alarms --region "$REGION" \
            --alarm-names "default/$s/RollbackAlarm" \
            --query 'MetricAlarms[0].StateValue' --output text 2>/dev/null || echo "MISSING")
  echo "  $s RollbackAlarm: $state"
  if [ "$state" = "ALARM" ]; then
    echo "::error::$s is already breaching its rollback alarm. Deploying now would" \
         "revert immediately and look like a bad build. Investigate first."
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Swap the image, preserving everything else.
#
# primaryContainer is read and written whole. Sending only { image } would drop
# the environment and the Secrets Manager references, which is how a service
# comes back up with no database password.
# ---------------------------------------------------------------------------
declare -A PREVIOUS
for s in "${SERVICES[@]}"; do
  PREVIOUS[$s]=$(configured_tag "$s")
  echo "  $s: ${PREVIOUS[$s]} -> $TAG"

  aws ecs describe-express-gateway-service --region "$REGION" \
    --service-arn "$(svc_arn "$s")" \
    --query 'service.activeConfigurations[0].primaryContainer' \
    | jq --arg img "$REGISTRY/$s:$TAG" '.image = $img' > "/tmp/$s.json"

  # Sanity-check the payload before sending it. A jq path that silently produced
  # null would otherwise be discovered by the service failing to start.
  jq -e --arg img "$REGISTRY/$s:$TAG" '.image == $img and .containerPort != null' \
    "/tmp/$s.json" > /dev/null

  aws ecs update-express-gateway-service --region "$REGION" \
    --service-arn "$(svc_arn "$s")" \
    --primary-container "file:///tmp/$s.json" > /dev/null
done

# ---------------------------------------------------------------------------
# Wait, reading ONLY the control plane.
#
# Not one HTTP request to the load balancer while this runs. Requests that are
# expected to fail -- a page that only exists in the new build, say -- are
# counted by the rollback alarm as 4xx, and on a low-traffic store the probe
# becomes the majority of the traffic. That is not hypothetical: it rolled back a
# deployment of this exact service. Defect 29.
# ---------------------------------------------------------------------------
echo "  waiting for both services (control plane only) ..."
while :; do
  done_count=0
  for s in "${SERVICES[@]}"; do
    configured=$(configured_tag "$s")
    running=$(running_tag "$s")

    # The service reverting to the tag it had is ECS rolling the deploy back.
    # Detect it explicitly: otherwise the loop simply times out and reports a
    # timeout, which sends the next person looking at the wrong thing.
    if [ "$configured" = "${PREVIOUS[$s]}" ] && [ "$configured" != "$TAG" ]; then
      echo "::error::$s was ROLLED BACK to ${PREVIOUS[$s]}. The canary judged $TAG" \
           "unhealthy. Check the RollbackAlarm history and the service logs."
      exit 1
    fi

    if [ "$configured" = "$TAG" ] && [ "$running" = "$TAG " ]; then
      done_count=$(( done_count + 1 ))
    fi
    echo "    $s  configured=$configured  running=${running:-none}"
  done

  [ "$done_count" -eq "${#SERVICES[@]}" ] && { echo "  both services on $TAG"; break; }

  if [ "$(date +%s)" -gt "$DEADLINE" ]; then
    echo "::error::Timed out waiting for $TAG. The services were neither fully" \
         "rolled out nor rolled back — check the ECS console."
    exit 1
  fi
  sleep 30
done

echo "::notice::Deployed $TAG to ${SERVICES[*]}"
