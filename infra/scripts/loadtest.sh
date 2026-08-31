#!/usr/bin/env bash
#
# Ramp load at the production storefront and print the window to read afterwards.
#
# Usage:
#   infra/scripts/loadtest.sh                 # the full ~13 minute ramp
#   infra/scripts/loadtest.sh --smoke         # 1 minute at 5 VUs, to check the script
#
# **Runs k6 from this laptop, in Docker** -- nothing to install, and k6 scripts
# are JavaScript rather than another tool's config dialect.
#
# The ~35ms from here to us-east-1 is added to every number k6 reports. That is
# not a flaw to correct for: CloudWatch's `TargetResponseTime` measures the same
# requests SERVER-side, so the gap between k6's p95 and CloudWatch's p95 is the
# network, measured rather than argued about. Read both.
#
# **Do not run this during a deployment.** Errors feed `RollbackAlarm`, which ECS
# consults during a canary bake, and a load test would revert the rollout and look
# like a bad build. Defect 29, and again in defect 30's recovery.
#
# **Expect alarm email.** `manitou-alb-latency-high` (p95 > 2s) and
# `manitou-alb-target-5xx` will fire if the ramp reaches the knee, which is the
# entire point of the exercise. They clear on their own.

set -euo pipefail

cd "$(dirname "$0")/.."          # infra/
SCRIPT=loadtest/storefront.js

if ! docker info > /dev/null 2>&1; then
  cat >&2 <<'EOF'
::error::Docker is not running.

  k6 runs in a container so there is nothing to install. Start Docker Desktop
  and try again. (This is the same daemon docker-compose uses for local Postgres.)
EOF
  exit 1
fi

# Refuse to start into a deployment, for the reason in the header. Same guard as
# .github/scripts/deploy.sh, pointing the other way.
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
for svc in manitou-api manitou-web; do
  n=$(aws ecs describe-express-gateway-service --region "$REGION" \
        --service-arn "arn:aws:ecs:$REGION:$ACCOUNT:service/default/$svc" \
        --query 'length(service.activeConfigurations)' --output text)
  if [ "$n" != "1" ]; then
    echo "::error::$svc has $n active configurations -- a deployment is in flight." >&2
    echo "         Wait for it to finish; load now would trip RollbackAlarm." >&2
    exit 1
  fi
done
echo "  no deployment in flight"

# The profile is selected by an env var the script reads, NOT by --vus/--duration:
# k6 ignores those once `scenarios` is defined, so a CLI smoke flag would silently
# run the full ramp instead of a short one.
SMOKE=0
if [ "${1:-}" = "--smoke" ]; then
  # Proves the script runs and the slug discovery works, before committing to
  # thirteen minutes. Same discipline as proving migrate.sh before relying on it.
  SMOKE=1
  echo "  SMOKE: 5 VUs for ~1 minute"
fi

START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "  started: $START"
echo

docker run --rm -i \
  -e SMOKE="$SMOKE" \
  -e WEB_URL="${WEB_URL:-https://imprimapress.com}" \
  -e API_URL="${API_URL:-https://api.imprimapress.com}" \
  grafana/k6 run - < "$SCRIPT"

END=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat <<EOF

  ---------------------------------------------------------------------
  Window: $START  ->  $END

  k6's numbers above are client-side. Now read the server's, which is the
  half that says whether the SYSTEM was slow or the path to it was:

    aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \\
      --metric-name TargetResponseTime --extended-statistics p95 \\
      --start-time $START --end-time $END --period 60 \\
      --dimensions Name=LoadBalancer,Value=<alb>

  Worth pulling for the same window:
    AWS/ApplicationELB  RequestCount            (expect ~2x k6's count: every
                                                 storefront page is dynamic and
                                                 calls the API back through this
                                                 same load balancer)
    AWS/ApplicationELB  HTTPCode_Target_5XX_Count
    AWS/ECS             CPUUtilization, RunningTaskCount  (did it scale 1 -> 2?)
    AWS/RDS             CPUUtilization, DatabaseConnections
    AWS/RDS             CPUCreditBalance        (the one with the least warning:
                                                 a burstable instance throttles
                                                 hard at zero while CPU looks calm)
  ---------------------------------------------------------------------
EOF
