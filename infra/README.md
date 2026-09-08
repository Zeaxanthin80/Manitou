# Infrastructure — decisions and their reasons

Phase 6 deploys Manitou to AWS. Most of that work happens in the AWS console rather than in this
repo, so the reasoning behind it has nowhere else to live. That is what this file is for: **the
decisions and why they were made**, so nobody has to re-derive them from a console screen six
months from now.

**What this file deliberately does not contain:** account IDs, the account alias, email addresses,
usernames, ARNs, or anything resembling a credential. This repo is on GitHub. An AWS account ID is
not a secret in the way a password is, but it is an identifier an attacker can use, and there is no
reason to publish one. Approach and reasoning only.

Deployment steps live in `PROJECT_PLAN.md` Phase 6. Service choices live in Section 7.

---

## Identity: who touches this account

```
root  ──  MFA on, credentials in a password manager, break-glass only
  │
  └─ IAM group: admins
       policy: AdministratorAccess (AWS managed)
       │
       └─ IAM user (daily work)
            - console password + MFA
            - access keys: not created until first needed
```

### Root is not the daily identity

Everything in Phase 6 tasks 1 and 2 was done as root, because an account starts with nothing else.
Task 3 ends that. Root is the one identity in AWS with **no permission boundary**: no policy can
restrict it, no administrator sits above it to reset it, and it can close the account outright.
Every root action also looks identical to every other root action in the audit log.

An IAM user is scoped, revocable, and attributable. Those three properties are the point — not
having fewer permissions, which it doesn't.

Root is still required for a short list, and gets used a few times a year:

- Changing the account name, root email, or root password
- Closing the account
- Changing the Support plan
- **Toggling IAM access to billing data** (see below)
- Recovering if the IAM user is locked out

Root credentials and the MFA recovery secret are therefore **kept, not deleted** — they are the
only way back in.

### `AdministratorAccess`, not a hand-scoped policy

Least privilege exists to separate people who have different jobs. There is one person here
and their job is "everything," so a hand-scoped human policy would buy no security and produce
a permission wall every few minutes — each one looking like a broken feature rather than a
policy gap.

Least privilege applies properly to **service** roles, and that is where the effort goes: the ECS
task role (task 7) and the API's S3 access (task 9). A machine role that can do exactly one thing
is a real control. A human admin role that cannot administer is theatre.

### A group, for a single user

Permissions on a group outlive the user attached to it, and when a second identity appears — a
CI deploy user, most likely — the permissions are already in the right place rather than needing
to be found and copied.

### Why not IAM Identity Center

AWS's current recommendation for human access is IAM Identity Center: sign in at a portal, get
**temporary** credentials, never hold a long-lived access key. For a team that is plainly better.

It was not used here for one specific reason. Managing AWS **account** access through Identity
Center requires an *organization instance*, and enabling one on a standalone account **creates an
AWS Organization** with this account as its management account. AWS's own documentation warns that
doing so "automatically upgrades your account to a paid plan... Your free tier credits expire
immediately." That sentence is written for accounts on the free plan and this one is already on the
paid plan — but the credits carry the name "AWS Free Tier," and $100 was not worth wagering on a
reading of an ambiguous clause.

The alternative *account instance* does not solve it: it covers application assignments only, not
AWS account access.

Revisit if this ever becomes a multi-account setup, where an Organization exists anyway and the
argument reverses.

### Access keys are created late, not up front

The most common way AWS credentials leak is a long-lived access key committed to a repository or
left in a dotfile. None is needed until the ECR image push (task 6), so none exists before then.

When one is created it belongs in `~/.aws/credentials` via `aws configure` — **outside this
repo**, which is why `.env.example` has no AWS keys in it and should not gain any.

### Billing is a special case in IAM

An IAM user is blocked from Billing and Cost Management **even with `AdministratorAccess`** unless
a root-only toggle is switched on:

> Account menu → Account → *IAM user and role access to billing information* → Activate

Skipped, the budgets become invisible to the identity that actually does the work. This fails
silently — the pages simply deny access — and can only be fixed from root.

---

## Cost controls, and what each one answers

Set up before any resource was created, deliberately: an alarm configured after the fact reports a
bill that has already been run up.

| Control | Question it answers | Configuration |
| --- | --- | --- |
| Zero-spend budget | "Are credits gone — is real money leaving?" | tracks **net** cost, credits included |
| Monthly cost budget | "How fast am I burning credits?" | **excludes** Credit and Refund charge types |
| Cost Anomaly Detection | "Did one service quietly change behaviour?" | per-service baselines, $5 impact threshold |

The two budgets are a complementary pair, and the charge-type filter is what makes them different.
With credits absorbing usage, a net-cost budget stays silent for months and then fires all at once
when they run out — useless as an early warning, but exactly right as a "the free ride is over"
signal. The gross-cost budget is the one that shows the burn rate while credits are still covering
it.

**Two corrections worth recording**, because both defaults were wrong in ways that would have
failed quietly:

- Cost Anomaly Detection's auto-created subscription had a threshold of **$100 AND 40%** — both
  conditions required. On an account spending $20–40/month that alert could never fire. Lowered to
  $5 absolute. Percentage thresholds are meaningless at this scale: $0.10 → $0.60 is +500%.
- Budgets are **evaluated a few times a day and cap nothing**. No AWS budget stops charges. They
  tell you to go and look.

### Cost traps specific to this architecture

- **RDS bills 24/7**, visitors or not. It is the largest single line item in this design. Stop the
  instance when not actively working.
- **NAT Gateway is ~$32/month** and charges hourly plus per-GB regardless of traffic. "Keep RDS
  private" has an easy wrong answer that provisions one. See the VPC note in task 4.
- **Domain registration is not covered by credits** — it lands as real net cost immediately, so
  expect the zero-spend budget to fire at task 10. That is the alarm working correctly.

---

## Audit

**CloudTrail Event history** records management events for the last **90 days**, with nothing to
configure and no cost. That was enough to verify task 3 directly: sign-in events before the switch
are attributed to `root`, sign-ins after it name the IAM user, with a `CheckMfa` event beside each
one.

A **Trail** (delivering to S3) is the answer if retention beyond 90 days is ever needed.
**CloudTrail Lake** — a SQL query layer over the same events — closes to new customers on
31 May 2026 and is not used here.

CloudTrail and CloudWatch answer different questions and are easy to confuse: **CloudTrail is who
did this; CloudWatch is how is it behaving.** CloudWatch is task 11.

---

## Database — RDS PostgreSQL (task 4)

A single `db.t4g.micro` running **PostgreSQL 16.15**, in `us-east-1`.

### Why 16 and not the newest

Local development runs `postgres:16-alpine` and this laptop has `psql`/`pg_dump` 16.15. **`pg_dump`
refuses to dump a server newer than itself**, so an 18 server would break the backup-and-restore
exercise Section 6.10 asks for — and it would fail as a version-mismatch error rather than
anything that looks like a backup problem.

The console offered 18.3 by default, and the tell that it had been applied was the parameter group
reading `default.postgres18`. Worth knowing where that shows: the engine version itself is far up
the form, but the parameter group sits right beside the settings you are actually checking.

### Public, with the security group as the control

`publicly_accessible = yes`, and `manitou-db-sg` allows port 5432 from **one `/32`** — the
development laptop. Everything else is dropped.

The alternatives all cost more than they are worth for a database with no data in it: a NAT Gateway
is ~$32/month (more than the database), a bastion adds an EC2 to patch plus a tunnel in front of
every migration, and running migrations from inside the VPC makes task 5 depend on task 6 while a
private subnet has no internet for `pip install`.

**Closed 2026-08-31.** `publicly_accessible` is now No and the developer-IP rule is gone;
the only inbound rule is sourced from the API's security group. See "Making RDS private"
below for why this needed no new subnets.

### Settings that were chosen rather than defaulted

| Setting | Value | Reason |
| --- | --- | --- |
| Instance class | `db.t4g.micro` | Graviton, cheaper than t3. Section 10.1 sizes to the early-launch tier. |
| Availability | Single-AZ | Multi-AZ is ~2×. Section 6.10 puts it before launch — Phase 7. |
| Storage autoscaling | **Off** | On by default with a 1,000 GB ceiling. Storage never scales back down, so it is a bill that only grows. |
| Master username | `manitou` | Not `postgres`; the default is what scanners try first. |
| Master password | RDS-managed in Secrets Manager | Never exists in plaintext outside an explicit retrieval. Rotation is built in. |
| Initial database name | `manitou` | **Blank creates an instance with no database in it** — the failure surfaces much later as a confusing connection error. |
| Backup retention | 7 days | Enables point-in-time recovery. |
| Encryption at rest | On | Cannot be added later without a snapshot-and-restore. |
| Deletion protection | On | Unticked by default. |
| Enhanced Monitoring, Performance Insights | Off | Both bill. |

Actual cost at creation: **$13.98/month** ($11.68 instance + $2.30 storage), against a ~$15
estimate. The console's figure excludes backup storage, IOs and data transfer.

### Two traps in the console

**The credit tutorial pre-fills an Aurora production cluster.** Starting the "Create an Aurora or
RDS database" activity opened the form set to Aurora PostgreSQL-Compatible, Production template,
`db.r7g.large` with a replica, Enhanced Monitoring and Advanced Database Insights. Aurora is a
different engine with a different pricing model — none of the estimates here apply to it. Changing
*Engine type* to PostgreSQL re-renders the form with sane defaults without leaving the tutorial.

**Express configuration creates Aurora Serverless, not RDS.** "Create with full configuration" is
what used to be called Standard create, and it is the one that exposes public access, initial
database name, storage autoscaling and deletion protection.

### How it was verified

A permit test and a refusal test, because either alone proves nothing:

- **From the laptop** — `psql` connects, TLS 1.3 / AES-256-GCM, prompt reads `manitou=>`.
- **From a phone hotspot** — the same command **times out**. Not "connection refused": security
  groups have no deny rule, so unmatched traffic is dropped silently. A password prompt here would
  have meant the source was wider than one IP.

Connecting only from the laptop is equally consistent with the group being open to the world. The
second test is what separates those.

Incidental confirmation of the version: `psql` prints `psql (16.15, server 18.3)` when majors
differ. It printed no server line, so the server is 16.x.

### Notes for later

- The master user is **not** a Postgres superuser (`manitou=>`, not `=#`). AWS keeps superuser to
  itself — part of what "managed" means. `rds_superuser` covers everything Alembic does.
- A **stopped instance still bills for storage, and RDS restarts it after 7 days.** Stopping
  between sessions is worth doing; it is not a way to park the instance.
- **RDS Proxy** (Section 6.11, connection pooling) bills per vCPU-hour and solves a problem this
  project does not have yet. Phase 7, if the load test says so.

---

## Migrations against RDS (task 5)

Schema only — no seed data, no admin user. The production database gets its first admin at task 7
by registering through the live site and one `UPDATE users SET role='admin'`, so no password is
ever hashed by hand.

### Retargeting one shell, not the environment

`alembic/env.py` resolves its URL from `settings.database_url`, and pydantic-settings reads
**environment variables ahead of `.env`**. Exporting `DATABASE_URL` for a single terminal therefore
points Alembic at RDS while `backend/.env` stays untouched and local development carries on against
Docker. Closing the terminal restores everything.

**`unset DATABASE_URL` when finished.** A shell still holding it aims *every* later command at
production — including `pytest`, whose conftest derives the test database URL by string surgery on
`settings.database_url` and would point `CREATE DATABASE` and its between-test `TRUNCATE` at RDS.

### The schema matched, by number

Comparing table counts alone would have proved very little. `PROJECT_PLAN.md` Section 6.8 records
that **Alembic autogenerate detects neither CHECK constraints nor triggers** — every one of those
was hand-written into a migration, so they are exactly the things that could have been missing while
a table list looked perfect.

| | local | RDS |
| --- | --- | --- |
| Tables | 18 | 18 |
| Triggers | 4 | 4 |
| Functions | 2 | 2 |
| CHECK constraints | 12 | 12 |
| Indexes | 45 | 45 |
| Alembic head | `be02c29a9f3c` | `be02c29a9f3c` |

The append-only trigger was then tested for **behaviour** rather than existence, since the triggers
are `FOR EACH ROW` and an `UPDATE` against an empty table would not fire one — a test that passes
for the wrong reason. Wrapped in `BEGIN … ROLLBACK` so nothing persists, which matters because
`audit_events` rejects `DELETE` too and a stray test row could never be removed:

```
ERROR:  audit_events is append-only; UPDATE is not permitted
CONTEXT:  PL/pgSQL function audit_events_append_only() line 3 at RAISE
```

Section 6.11's claim holds: same schema in both places, one connection string apart, because the
same migrations built both.

### Two bugs this surfaced

Pointing the application at a second environment for the first time is what found them. Both were
latent, and both are recorded in `docs/defect-log.md` (21 and 22).

- **Any password containing `%` broke Alembic.** `set_main_option` writes through configparser,
  where `%` starts an interpolation token — and percent-encoding a `#` for URL-safety produces
  exactly that. `devpassword` has no special characters, so nothing could reveal it locally.
- **`seed.py` could not reseed a database that had shipped an order.** Its hand-written delete
  order went stale when Phase 5.5 added `shipments`. It now uses the catalogue-driven
  `TRUNCATE … RESTART IDENTITY CASCADE` the test suite already used.

### Handling the password

Two things that are not obvious and cost time:

- **URL-encode it.** RDS excludes `/`, `"`, `@` and space from generated passwords, but `#`, `%`
  and `?` are all possible and each changes how a URL parses. A `#` truncates the string silently
  and the resulting error names the host, not the password.
- **`HISTCONTROL` is unset on the development machine**, so prefixing a command with a space does
  *not* keep it out of `~/.bash_history`. That behaviour requires `HISTCONTROL=ignorespace`. Read
  the password with `read -rsp` into a variable instead; history then stores `$PGPW`, never a value.

**A traceback can publish a credential.** Alembic's configparser error quotes the whole connection
string, password included. It reached a terminal here; one task later the same failure would have
written it to CloudWatch Logs under a 90-day retention policy. The master password was rotated.

---

## The API container and ECR (task 6)

`backend/Dockerfile` on `python:3.12-slim`, `linux/amd64`, pushed to a private ECR repository
called `manitou-api`.

### Build from the repository root

```
docker build --platform linux/amd64 --provenance=false --sbom=false \
  -f backend/Dockerfile -t manitou-api:local .
```

**The context has to be the root**, and that is not stylistic. `app/store.py` reads
`store-config.json` at import time from `Path(__file__).resolve().parents[2]` — one level *above*
`backend/`. An image built by copying `backend/` alone would resolve that to `/` and die on import,
before FastAPI starts, naming a path nobody wrote.

So the image mirrors the repo's shape: `/app/store-config.json` beside `/app/backend/`. Preserving
the layout rather than making the path configurable means the logic that works in development works
in the container for the same reason, instead of by a second arrangement someone has to keep in
step. Verified by mutation — mount `/dev/null` over the file and the container dies on a JSON parse
error, so the copy is load-bearing rather than decorative.

### Choices worth their reasons

| | |
| --- | --- |
| **slim, not Alpine** | Every wheel here — `psycopg2-binary`, `pillow`, `bcrypt`, `uvloop`, `httptools` — ships as `manylinux`, which Alpine's musl libc cannot use. Alpine would compile them from source and end up larger and slower to build than the image it was meant to beat. |
| **`--host 0.0.0.0`** | A container binding loopback is unreachable from outside itself. The symptom is a process that starts cleanly and answers nothing. |
| **Exec-form `CMD`** | uvicorn becomes PID 1 and receives SIGTERM directly. Shell form puts `/bin/sh` at PID 1, which does not forward signals, so ECS would wait out its full stop timeout on every deploy. |
| **`PYTHONUNBUFFERED=1`** | Python block-buffers stdout when not a TTY. Without it CloudWatch shows nothing until the buffer fills, and a task killed mid-buffer loses exactly the logs that would say why. |
| **non-root `USER`** | uid 10001. Nothing here needs root. |
| **no `--workers`** | Express Mode scales by running more tasks; one process per container keeps the scaling unit a task rather than a hidden pool inside one. |

`--platform` belongs on the build command, not pinned in `FROM` — a constant there makes the file
unusable for any other architecture, and buildx warns about it. Getting the architecture wrong
produces `exec format error`: a task that starts, dies and restarts forever with nothing useful in
the logs. One `docker image inspect --format '{{.Os}}/{{.Architecture}}'` is cheaper than diagnosing
that.

### Two ECR findings, both silent

**`scanOnPush=true` on the repository did nothing.** The registry-level scanning configuration
governs, and it read `type: BASIC, rules: []` — so no rule matched and no scan ran. Nothing errors;
`describe-image-scan-findings` simply reports that no scan exists. Fixed with a registry rule:

```
aws ecr put-registry-scanning-configuration --scan-type BASIC --region us-east-1 \
  --rules '[{"scanFrequency":"SCAN_ON_PUSH","repositoryFilters":[{"filter":"*","filterType":"WILDCARD"}]}]'
```

**buildx's default output cannot be scanned.** It attaches provenance and SBOM attestations, which
forces an OCI *image index* even for a single platform, and ECR basic scanning refuses that media
type outright (`UnsupportedImageTypeException`). `--provenance=false --sbom=false` produces a plain
`application/vnd.oci.image.manifest.v1+json`, which scans. It also stops each push leaving an
untagged index and attestation behind.

### What the scan found

All Debian base-image packages, none from `requirements.txt`.

| | findings | CRITICAL | HIGH |
| --- | --- | --- | --- |
| `v1` — base image as shipped | 28 | 4 | 15 |
| `v2` — after `apt-get upgrade` | 18 | 4 | 8 |

The `apt-get upgrade` layer is worth its cost in reproducibility: a base image is a point-in-time
snapshot, and an image that never upgrades accumulates CVEs by standing still.

**The 4 CRITICALs are carried deliberately** — 3 in `perl`, 1 in `glibc`, with no Debian fix
available. `perl-base` is `Essential: yes, Priority: required`, and nothing in this application
invokes perl. Removing an Essential package to move a scanner number is a worse trade than an
unreachable CVE. A distroless base would remove perl entirely; that is a Phase 7 question, not a
reason to break dpkg now.

### Access keys now exist

Deferred since task 3 specifically so they would exist for the shortest possible time; the ECR push
is what needed them. They live in `~/.aws/credentials`, **outside the repository** — which is why
`.env.example` has no AWS keys and must not gain any.

**Docker credential storage needed a decision.** Docker Desktop's helper delegates to `pass`, which
needs a GPG key this machine has none of. `credsStore` was removed from `~/.docker/config.json`
(backed up alongside it), so Docker stores the registry auth base64-encoded in that file instead.
Base64 is encoding, not encryption — but the stored value is an ECR token that expires in 12 hours,
not a standing credential. Initialising `pass` with a GPG key is the better answer if this machine
ever holds more registry logins.

`aws ecr get-login-password | docker login --password-stdin` rather than `--password`: the latter
puts a live token in shell history and in the process list, where any other user on the machine can
read it.

### Tags

`v1`, `v2` — never `latest`. A moving tag makes "which image is running?" unanswerable and turns
rollback into guesswork. Task 7 deploys a specific tag.

The repository is `MUTABLE`, so a tag *can* be overwritten; `v1` was, once, before anything consumed
it. From task 7 on, a deployed tag should be treated as immutable whether or not ECR enforces it.

---

## The API service — ECS Express Mode (task 7)

One `aws ecs create-express-gateway-service` call provisions the lot: the `default` ECS cluster on
Fargate, a task definition, a service with canary deployment and autoscaling, an **Application Load
Balancer with an HTTPS listener and an ACM certificate**, security groups, a CloudWatch log group,
metric alarms, and a public URL. Roughly 3–5 minutes.

The certificate is worth noticing — TLS 1.3 on an Amazon-issued cert for the generated hostname,
with no certificate work of our own. That is most of what task 10 would otherwise have to arrange
for the API.

### Sizing, and the default that would have cost the most

| | chosen | Express Mode default |
| --- | --- | --- |
| CPU / memory | **512 / 1024** | 1024 / 2048 |
| max tasks | **2** | **20** |
| health check path | **/health** | `/` |

**`maxTaskCount` defaults to 20.** At roughly $18/task that is ~$360/month if anything drives CPU
above the 60% scaling target. Capping it is the single most valuable line in the whole command.

Not 256/512 for CPU/memory: Fargate hard-kills a task that exceeds its memory limit, and diagnosing
an OOM restart loop costs more than the ~$9/month saved. Trim from CloudWatch data later rather than
guessing now — Section 10.1's principle applied to the compute rather than the database.

The health check path is not optional here. The default is `/`, and this API has no route there, so
every health check would 404 and the deployment would fail with nothing obviously wrong.

### Reaching the database: authorise before deploying

`/health` runs `SELECT 1`. The target group checks it every 30s and marks a target unhealthy after
**2 failures**, against a 300s grace period — so a task that cannot reach RDS fails the deployment
about six minutes in, and Express Mode's canary strategy **cannot be changed** to soften that.

So the security group came first, not after:

1. `manitou-api-sg` created in the default VPC.
2. `manitou-db-sg` given an inbound rule: TCP 5432, **source `manitou-api-sg`** — a group reference,
   not a CIDR.
3. That group passed to `--network-configuration`.

A group-referencing rule admits traffic from any ENI carrying that group. And because RDS sits in
the same VPC, its endpoint resolves to a **private** address from inside — traffic never leaves the
VPC despite `publiclyAccessible = true`.

**Providing a security group adds to Express Mode's own, it does not replace them.** The running
service carries two: ours and the auto-created service group. Confirmed in the deployed
configuration, and it matters — a rule referencing only ours still works because the ENI carries
both.

### Secrets: injected, never stored in the definition

`ExpressGatewayContainer` takes `environment` **and** a separate `secrets` list whose `valueFrom` is
a Secrets Manager ARN with an optional JSON key selector. So this did not wait for task 11, and
should not have: **task definition revisions are immutable**, so a plaintext key in revision 1 stays
readable until that revision is deregistered *and* deleted.

```
secrets (ARN references)                  environment (plaintext, by design)
  DB_PASSWORD  → rds!db-…:password::        DB_HOST, DB_PORT, DB_USER, DB_NAME
  JWT_SECRET   → manitou/api:jwt_secret::   STRIPE_PUBLISHABLE_KEY  (public by design)
  STRIPE_SECRET_KEY → manitou/api:…         EMAIL_SENDER, PAYMENT_GATEWAY
```

**The database password is read straight from the RDS-managed secret** — no copy anywhere. That is
the whole reason for the `config.py` change below: a duplicated password goes stale the moment RDS
rotates, and fails as a connection error naming the host rather than the credential. It has already
been rotated twice by hand during this phase.

The execution role carries an inline policy granting `secretsmanager:GetSecretValue` on **exactly
those two ARNs** — not a wildcard. This is where least privilege actually applies, as the identity
section above argues: a machine role that can do one thing is a real control.

The **JWT signing key is newly generated**, not the development one. Section 4.2: a leaked
development secret must never be able to forge production tokens.

### Why `DATABASE_URL` is assembled rather than passed

The RDS-managed secret holds `{username, password}` JSON, not a connection string, so there is no
whole URL to inject. `backend/app/config.py` therefore builds one from `DB_HOST/PORT/USER/NAME` plus
the injected `DB_PASSWORD` when `DATABASE_URL` is absent, percent-encoding the password and
appending `sslmode=require`.

Done as a validator on the single `database_url` field rather than at the call sites, because five
places read it — `db.py`, `alembic/env.py`, `conftest.py` twice, `seed.py` — and all of them want a
string. None of them changed.

Two things learned while building it, both by measurement:

- **SQLAlchemy's `make_url` is lenient.** It parses a raw `#`, `)`, `%` or `/` in the password
  correctly, so the encoding is not fixing a bug in today's path. It is there because the encoded
  form is RFC 3986-correct and `database_url` is a plain string any consumer may parse. An earlier
  version of the comment claimed a raw `#` truncates the URL; that was wrong and is corrected.
- **The encoding does not cause defect 21.** A password containing a literal `%` — which RDS can
  generate — puts a `%` in the URL whether or not we encode, so `env.py`'s `%%` escape was always
  required. Encoding only makes it surface sooner.

Locally, `backend/.env` always supplies `DATABASE_URL`, so the assembly branch never runs — the
tests pass `_env_file=None` to reach it. The container has no `.env` at all (`.dockerignore`), which
is what makes production the real exercise of that code.

### Two failures worth recording

**The service-linked role must exist first.** The first `create-express-gateway-service` failed with
*"Unable to assume the service linked role"* — and **created `AWSServiceRoleForECS` as a side effect
while failing**. The retry then worked. The console creates these implicitly; the API does not.
`AWSServiceRoleForElasticLoadBalancing` and `AWSServiceRoleForApplicationAutoScaling_ECSService` were
created explicitly rather than discovered the same way.

**The managed policy ARN is not guessable.** It is
`arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices` — a
`/service-role/` path and a lowercase `for`. `iam list-policies --scope AWS` did not surface it; the
documentation did.

### How it was verified

- **`/health` → `{"status":"ok"}` over HTTPS.** One request proves the image ran, `store-config.json`
  resolved at `parents[2]`, all three secrets were injected, the assembled URL parsed, and the task
  reached RDS through the group-referencing rule.
- **`/products` → `{"items":[],"total":0}`.** Empty is the pass: schema without rows.
- **The environment contains no `DATABASE_URL`** — yet the service connects. That absence is what
  proves the assembly path runs in production rather than only in tests.
- **Every task definition revision scanned for `sk_test_`, `sk_live_` and `postgresql://`** — clean,
  including revision 1 from the failed attempt. The control for the entire secrets decision.

---

## The web app — a second Express Mode service (task 8)

### Amplify Hosting was in the plan and could not be used

`PROJECT_PLAN.md` Section 7 named **Amplify Hosting**. Its compute SSR provider supports
**Next.js 12 through 15**; this app is on **16.3.0**. AWS's migration page states plainly:
*"Currently, the Amplify Hosting compute SSR provider supports Next.js version 15."* Nothing
announces 16.

So the storefront runs as a **second ECS Express Mode service**. The cost argument makes that a
substitution rather than a compromise: **up to 25 Express Mode services in one VPC share an
Application Load Balancer**, so the web app adds Fargate capacity and no second ~$16/month ALB.
Confirmed after deploying — `describe-load-balancers` returns exactly one.

What it gives up is real: **Amplify's git-push CI/CD and PR previews**. Deploys are manual, as for
the API. A "Deploy Express Service" GitHub Action exists and would close the gap. Both stack tables
in `PROJECT_PLAN.md` (Sections 3 and 7) were corrected, because a plan naming a service that cannot
run the app is worse than no plan.

### `output: 'standalone'`, and the two directories it does not copy

`.next/standalone` holds a minimal `server.js` plus only the `node_modules` Next traced as
reachable. Necessary: the working tree carries **476 MB of `node_modules` and 798 MB of `.next`**.

Next's docs are explicit that standalone **does not copy `public/` or `.next/static`** — they are
expected to sit behind a CDN. They are not yet (task 9), so the Dockerfile copies them in. Miss
either and the container passes its health check while serving an unstyled page with broken images,
which is why verification fetches a CSS file and a `public/` image rather than trusting the health
check.

`HOSTNAME=0.0.0.0` is mandatory. `server.js` binds loopback otherwise — the same mistake as
uvicorn's `--host`, with the same symptom: a process that starts cleanly and answers nothing.

### One build context, two images

The root `.dockerignore` excludes `web/` outright — right for the API image, fatal for this one.
BuildKit gives **`<dockerfile-path>.dockerignore`** precedence over the root file, so
`web/Dockerfile.dockerignore` and `backend/Dockerfile.dockerignore` each describe their own image.

**Verified before relying on it**, with a throwaway build: a root ignore excluding `sub/` and a
`sub/Dockerfile.dockerignore` excluding something else — the per-Dockerfile file won.

Both images still build from the repository root, because `web/scripts/build-tokens.mjs` reads
`design-tokens.json` and `store-config.json` from there, exactly as `backend/app/store.py` does.
Those generate `app/tokens.css`, `lib/design-tokens.ts` and `lib/store-config.ts` — all git-ignored,
so a clone has none of them and the build must produce them. `prebuild` runs `npm run tokens`
automatically.

### Build-time versus runtime configuration

| | when | why |
| --- | --- | --- |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | **build** | `NEXT_PUBLIC_*` is compiled into the client bundle. Passing it at runtime leaves the browser with an empty string and Stripe Elements silently fails to mount. Baked into the image; changing it needs a rebuild. |
| `API_URL` | **runtime** | A plain server-side variable read at module scope, not inlined — so one image can point at any environment. Every route is dynamic, so nothing calls the API during the build. |

Baking the publishable key is acceptable for that one variable and only that one: it is designed to
be public and can only start a payment the secret key already authorised. **No other secret may be
handled this way** — the client bundle was audited to confirm: `sk_test_` absent, `postgresql://`
absent, `pk_test_` present in exactly one chunk as the positive control proving the grep worked.

### The health check does not call the API

`web/app/api/health/route.ts` returns `{"status":"ok"}` without touching the backend. The obvious
alternative — health-checking `/`, which renders the catalogue — would couple this service's health
to the API's: a brief backend problem would fail the check, ECS would recycle the web tasks, and a
short blip becomes a longer whole-site outage.

A liveness probe answers "is this server up", not "is everything downstream healthy". The API has
its own `/health` and its own alarms.

### Deployment differences from the API service

- **No `secrets`** — the web app holds none.
- **No `manitou-api-sg`** — it never touches the database, and attaching that group would grant
  Postgres reach it has no use for.
- Otherwise identical: `--cpu 512 --memory 1024`, `maxTaskCount` **2** rather than the default 20,
  `containerPort 3000`, `--health-check-path /api/health`.

The web app calls the API over its **public HTTPS URL**, leaving the VPC and returning through the
shared ALB. Not elegant; the alternative is service discovery for a two-service system, and the ALB
is already in the path.

### Verified

Locally against the live API before pushing, then again deployed: `/api/health` 200, the storefront
rendering `0 products` with the "Nothing here yet" empty state (correct — production has schema and
no rows), CSS and a `public/` image both 200, `/login` 200 and `/admin` 307 to login when signed
out. First ~90 seconds after deploy returned 503 while the target registered — expected, not a
fault.

---

## Product images — S3, CloudFront and presigned uploads (task 9)

Until this, adding a product photo meant committing a file to `web/public/` and
redeploying, and **the container filesystem is ephemeral** — anything written at
runtime dies with the task. Now a vendor picks a file on the product edit page and
it goes straight to S3.

### The shape, and why it has three steps

```
browser ──► API            sign a PUT into pending/
browser ──────────────────► S3       the bytes, direct (needs CORS)
browser ──► API            confirm: head_object, copy to media/, write the row
```

**The bytes never pass through the API or the Next server.** No request-size
ceiling anywhere in the chain, and no Fargate task sized for the largest
photograph anyone might send.

**The confirm step is not optional.** The browser uploads directly and the API
never sees it happen, so without it there is no row and no evidence the upload
completed. `head_object` is what turns "the client says it uploaded" into "the
object exists and is this big" — size and content type come from S3's own view,
never from what the client claims.

**Two prefixes exist so the lifecycle rule can tell the difference.** Uploads are
signed into `pending/`; confirming copies to `media/` and removes the source. So
anything still in `pending/` is by definition abandoned, and expires after a day.
Uploading straight to `media/` would make abandoned and live objects
indistinguishable and the bucket would fill with orphans.

### A presigned URL carries the signer's authority

This is the fact that shapes the IAM policy. Whoever holds the URL can do what
`manitou-api-task` can do, to that key, until it expires. So the role grants:

| | |
| --- | --- |
| `s3:PutObject`, `s3:GetObject` | on `pending/*` and `media/*` only |
| `s3:DeleteObject` | on **`pending/*` alone** |
| everything else | not granted — no list, no delete on `media/` |

Deleting a live asset is task 9b's, and it needs the "which products use this"
check that does not exist yet. A role that could already do it would be handing
that capability to every upload URL.

This is also the project's **first task role**. Everything before it needed only
an execution role — ECS pulling an image and injecting secrets. Now the
application's own code calls an AWS API, which is a different thing and gets a
different identity.

### Enforcing the size limit on a PUT

A presigned **POST** has `content-length-range` in its policy conditions. A
presigned **PUT** has no equivalent. So the limit is enforced by signing the
exact byte count: the client declares what it is about to send, the API decides
whether that is allowed, and S3 holds it to the answer — SigV4 covers every
header it lists, so a request whose `Content-Length` differs simply will not
verify.

A client that lies about the size gets a signature failure; one that tells the
truth about too large a file is refused at presign, before any bytes move.
Rejecting after the upload would mean paying for the transfer and still holding
the object.

**No SVG.** It is an image to a user and a script to a browser, and one served
from a host the site trusts is stored XSS. Vector artwork is `store.logo`, which
is committed rather than uploaded.

### One trusted host, listed in two places that must agree

`AdminImageCreate` refuses to **store** a URL on any host but the CloudFront
distribution; `next.config.ts` `images.remotePatterns` refuses to **render** one.
Either alone leaves the gap defect 1 fell through — a URL the form accepts that
then makes `next/image` throw at render time, taking down the home page, the
product page and the admin edit page together.

The widening is an allow-list of **one**, and the trailing slash in
`https://{host}/` is doing real work: without it,
`https://d111….cloudfront.net.evil.example/` is a different host that merely
starts with ours. Mutation-tested — removing that slash fails a test named for
exactly that shape.

**`CDN_HOST` must be set at BUILD time for the web image.** Next serialises the
resolved config into `.next/required-server-files.json` during the build, so
setting it only at runtime leaves `remotePatterns` empty and every CDN image is
refused. Found by checking the built file rather than assuming: the first build
of the image reported `remotePatterns: []`.

### How it was verified

- **The bucket is private, the CDN is not.** Direct S3 → **403**; through
  CloudFront → **200** with the bytes. Either alone is consistent with a
  world-readable bucket.
- **A non-existent key returns 403, not 404** — OAC denies rather than confirming
  what the bucket contains.
- **CORS both ways.** A preflight from the web origin returns
  `Access-Control-Allow-Methods: PUT`; the same preflight from an unlisted origin
  returns **403**. (`curl` tests this fine, contrary to the plan's claim — you
  just have to send an `Origin` header.)
- **41 backend tests**, driving the whole flow against a stub client, plus 7
  through the real app. Mutation-tested: dropping the size limit, unsigning
  either header, or removing the pending-prefix guard each fail a test.

### Two mutations that survived, and what they taught

Both times the fix was to pin real behaviour, not to delete the code:

- The content-type check in `presign_put` looked redundant with `new_pending_key`.
  Its actual job is deciding which error a request failing *both* checks gets —
  "not an image type" is fixable, "too large" sends the vendor off to compress a
  file that will be refused anyway.
- The `cdn and` guard on the host check. With an empty `CDN_HOST` the comparison
  builds the prefix `https:///`, and a URL beginning with exactly that would
  match it. Malformed, but defect 1 was precisely a URL the API accepted and
  `next/image` then threw on.

---

## Making RDS private (Phase 7)

Phase 6 task 4 asked for a private database and did not get one. Closed 2026-08-31.

### It needed no new subnets, and that is the part worth understanding

The instinct is that "private" means private subnets, which in a default VPC means new subnets and
usually a **NAT gateway at roughly $32/month**. None of that was necessary.

**`PubliclyAccessible` and subnet routing are different controls.** The flag decides whether the
instance gets a public IP and how its endpoint resolves from outside the VPC. The route table decides
whether things in the subnet can reach the internet *outbound*. A database with no public IP sitting
in a public subnet is not reachable from the internet — there is no address to reach it at.

AWS states it directly: *"Even if an instance is launched in a public subnet... disabling public
access [means] the RDS endpoint resolves to a private IP address only."*

So the change was one `ModifyDBInstance --no-publicly-accessible --apply-immediately`, and the real
work was everything that depended on the old behaviour.

### The API never noticed, and that was predictable

From inside the VPC the endpoint **already** resolved to the private address; the flag only removes
the public one, and the private IP does not change. Verified rather than assumed: `/categories`
returned real data from the database throughout.

Measured from a laptop afterwards:

```
manitou-db.…rds.amazonaws.com  ->  172.31.36.22     (private, was a public IP)
TCP :5432                      ->  timed out
```

**Both halves matter.** "The database is unreachable" and "the database is unreachable *from the
internet*" look identical unless the API is confirmed working at the same moment.

### Migrations now run inside the VPC

`infra/scripts/migrate.sh` runs `alembic` as a **one-off ECS task on the API's own task definition** —
same image, same subnets, same security group, same `DB_PASSWORD` from Secrets Manager. Only the
lifecycle differs: run once and exit rather than serve.

No new image was needed. `backend/Dockerfile.dockerignore` excludes `backend/tests/` but not
`backend/alembic/`, so the production image already carries the CLI and every migration.

Three details that are easy to get wrong:

- **`assignPublicIp: ENABLED`.** This VPC has no NAT gateway and no VPC endpoints, so a task's public
  IP is its only route to ECR to pull the image and to Secrets Manager to read the password. Without
  it the task never starts, and the failure reads as a mysterious timeout.
- **The task definition is resolved, not pinned.** Migrations must run the code being deployed, so
  hardcoding a revision would be exactly backwards.
- **The script waits for `STOPPED` and returns the container's exit code as its own.** `run-task`
  returns as soon as the task is *accepted*, well before it has connected to anything. Verified by
  running a deliberately bad revision: alembic exited 255, the script exited 1, and the error came
  through from CloudWatch. A success signal never tested against failure is worth nothing.

### The ordering was the design

The replacement path was proven **while the old one still worked** — `alembic current` and
`upgrade head` both ran green before the flag was touched. Flipping first would have removed the only
route to the database and then asked whether its replacement worked.

### Two things given up, deliberately

**Ad-hoc `psql` from a laptop.** Affordable now only because defect 23 is fixed: the portal can
create categories, so the SQL workaround it once forced is unnecessary. If it is missed, a stopped
`t4g.nano` with SSM port-forwarding costs about $0.80/month for its volume and needs no open ports.

**Private subnets as a second control.** The stronger form of this: a subnet with no route to an
internet gateway survives someone flipping `PubliclyAccessible` back. Not worth $32/month here, and
worth revisiting if the account ever holds regulated data.

### A near miss worth recording

The security-group cleanup nearly revoked rules from the wrong group. `sg-0765ba8bd1c0e6c51` was
taken from an earlier query and is the **API's** security group, not the database's — revoking its
rules would have cut the API off from the very database this task was securing. An
`assert GroupName == "manitou-db-sg"` before the revoke caught it, and the correct group was then
found by looking it up from the RDS instance rather than from memory.

**Assert what a resource IS before mutating it**, whenever the identifier came from anywhere but the
call immediately preceding.

---

## The application's own database role (Phase 7, defect 30)

The API used to connect as the RDS **master** user. Two separate problems, one fix.

### An injected secret is not a live secret

The RDS-managed master secret rotates automatically every 7 days. **ECS resolves a `secrets`
reference once, when a task starts, and never refreshes it.** A long-running service therefore keeps
the password it read at boot, and the next rotation leaves it authenticating with a credential the
database has stopped accepting.

Injection and retrieval look interchangeable in a task definition. They are not, and this is where
the difference shows: rotation only helps a consumer that re-reads.

**One-off tasks are immune by construction** — `migrate.sh` and `run_in_vpc.sh` start a *new* task
for every run, so ECS resolves the secret fresh each time. Only the long-running service was ever
exposed. That asymmetry is the bug in one sentence.

### The failure is invisible to every health signal

Postgres authenticates at connect time and only at connect time. So after a rotation:

- connections already open keep working;
- new connections fail;
- and `/health`, which runs `SELECT 1` every 30 seconds, keeps one connection permanently checked
  out, valid and answering.

**The one code path guaranteed to keep working is the one the load balancer uses to decide whether
anything is working.** Reproduced deliberately: sequential requests all 200, 20 concurrent gave
5 × 500, 40 concurrent gave 10 × 500 — a steady 25% failure rate — while both target groups read
`healthy` and `UnHealthyHostCount` never moved.

Two things that reproduction taught which the design did not predict:

- **The alarms arrived after the incident ended.** `manitou-alb-target-5xx` evaluates a 300-second
  period; first errors at 19:54, ALARM at 19:59:52, recovery already complete at 19:59:24.
- **The first burst missed the threshold by one request** — 5 errors against *greater than* 5.

### Least privilege applies to database roles too

Separately from rotation, the master owns every table. Owning a table is enough to
`ALTER TABLE ... DISABLE TRIGGER` — so the API could have switched off the trigger that makes
`audit_events` append-only. **A guarantee the guarded party can disable is not a guarantee.**

`manitou_app` now holds `SELECT, INSERT, UPDATE, DELETE` on the tables, `USAGE, SELECT` on the
sequences, and nothing else. `ALTER DEFAULT PRIVILEGES` covers tables a future migration creates —
without it, the next migration's table is invisible to the API and surfaces as a permission error on
something just created. `UPDATE` and `DELETE` on `audit_events` are revoked as well as
trigger-blocked, so the append-only claim holds at two layers.

### Two credential sets, chosen by which task definition you run on

Migrations need DDL; the API must not have it. Rather than branch in application code, the
credentials live in different task definitions and the choice is made by *what you run*:

| | database identity | used by |
| --- | --- | --- |
| the API service | `manitou_app`, password from the non-rotating application secret | serving traffic |
| `manitou-dbadmin` | the master, from the RDS-managed secret | `migrate.sh`, `run_in_vpc.sh` |

The alternative — both credential sets on the API's own task definition, selected at runtime — was
rejected. It would leave the master password in the API container's environment, and **a variable
the application never reads is still a variable it holds.**

`manitou-dbadmin` registers a **fresh revision on every run**, deriving the image from the live
service. A static definition would pin the image to whatever was current the day it was written,
which is backwards for migrations: a migration must match the code being deployed. Same reasoning as
`deploy.sh` — derive the container spec, do not retype it.

### `pool_pre_ping` is not the fix, and it was worth proving that

The obvious reach is `pool_pre_ping=True`. It does not help here: the replacement connection
authenticates with the same stale password and fails identically. Measured on a disposable role
before relying on it.

It is enabled anyway, for the thing it *does* fix — an RDS reboot, failover or maintenance window
closing idle connections. On a store sized at ~1 concurrent user, connections sit idle for hours, so
those are exactly the connections a customer meets after a quiet night.

### Recovery must not be a deployment

The 500s feed `RollbackAlarm`, which ECS reads during a deployment bake — it went to ALARM during
this test. **A forced deployment would have been reverted, and the post-mortem would have blamed the
image.** Defect 29 with a different trigger.

`stop-task` instead: the service floor is one task, so the scheduler launches a replacement, which
resolves the secret fresh. No alarm is consulted. About 90 seconds, of which ~60 return 503.

### Verified

The control was the harder half. `stop-task` fixes the symptom either way, so "a rotation no longer
breaks it" proves nothing unless a rotation *did* break it first — otherwise both measurements are
zero and agree that nothing is nothing.

1. **Mechanism first, on a disposable role, with no blast radius.** Warm connection survived a
   password change; a new connection failed; `pool_pre_ping` did not rescue it; a fresh password
   worked. This also measured the pool: 5 + 10 overflow = **15 per task, 30 across two** — which is
   why `manitou-rds-connections-high`, set to fire above 50, could never fire.
2. **Then on the live API**, then recovered, then re-confirmed at the concurrency that had been
   failing: 40/40 × 200.
3. **Paired permit and refusal on the new role.** Reads and inserts allowed; `CREATE TABLE`,
   `DROP TABLE`, `DISABLE TRIGGER`, and `UPDATE`/`DELETE` on audit rows all denied. Owns 0 tables,
   not a superuser.

The refusal probe deliberately does **not** run the destructive statements as the master as a
control. An earlier draft did, relying on Postgres DDL being transactional to roll back a
`DROP TABLE products`. That is true and it was still wrong: it put a live table one missing rollback
away from deletion to establish something the catalogue already knows. Ownership is a structural
fact — `pg_tables.tableowner` answers "could the master disable that trigger?" without disabling
anything.

### Two alarms corrected on the way past

Both were provable from arithmetic and 24 hours of existing metrics, without waiting for the load
test.

**`DatabaseConnections` was watching for a number the system cannot reach.** The threshold was 50;
the API's steady-state ceiling is `pool_size` 5 + `max_overflow` 10 = 15 per task × `maxTaskCount` 2
= **30**. Measured, not inferred — the rotation probe printed the live pool's own configuration. Now
24, against an observed idle baseline of 5–10.

**It fired correctly on its first real event**, during the load test, at a peak of 35 connections. At
the old threshold of 50 it would have stayed silent through a saturation event severe enough to
return 859 load-balancer 503s.

That peak of 35 also corrects the arithmetic above: **30 is the steady-state bound, not a hard
limit.** A scale-out or a task replacement briefly runs more tasks than `maxTaskCount` while the old
one drains, and each brings its own pool. The tidy 2 × 15 invites treating it as a ceiling; it isn't.

**Nothing watched CPU credits on a burstable instance.** `db.t4g.micro` accrues 12 credits/hour and
caps at 288 — both confirmed from metrics, which show the balance pinned at 288 against ~0.45/hour of
use. At zero the instance is throttled to its baseline and every query slows at once **while
`CPUUtilization` looks unremarkable**, so the existing CPU alarm would not catch it. New alarm below
50, roughly four hours of full-burst runway, far under the 184 low-water mark of the past day.

That is 14 alarms against a free tier of 10, so roughly $0.40/month.

---

## The load test (Phase 7 task 2)

Section 10.1 sizes ImprimaPress at **~1 concurrent user** at launch-day peak. So the test was never
"can it handle the target" — that would return green and mean nothing. It was a **ramp to failure**
to find the headroom: 0 → 10 → 50 → 100 → 200 VUs over 13 minutes, each level held, k6 in Docker from
the laptop, read-only.

### Run it twice, because the catalogue was a variable

The first run discovered **one product**. That measures the infrastructure but flatters the
application: one row is hot in every cache and renders one card. So 24 products (289 variants) were
seeded and the identical profile re-run.

| | 1 product | 25 products | |
| --- | --- | --- | --- |
| `/health` p50 | 46.6 ms | 46.2 ms | **unchanged — the control** |
| catalog p50 | 91 ms | 180 ms | +97% |
| product p50 | 89 ms | 143 ms | +61% |
| catalog p95 | 1.01 s | 2.09 s | +107% |
| failed | 3.48% | 4.40% | |
| data received | 227 MB | 614 MB | 2.7× |
| RDS CPU max | 24.5% | 24.3% | unchanged |
| API container CPU max | 93.5% | 95.1% | |
| web container CPU max | 67.4% | **96.8%** | +44% |

**`/health` is what makes this a comparison rather than two numbers.** It does one `SELECT 1` and
never touches the catalogue; it did not move. So the doubling elsewhere is catalogue work, not
ambient load, not the network, and not the time of day.

### Where it breaks, and what breaks

Both runs behave the same way: comfortable to 50, degraded but serving at 100, collapse between 100
and 200. Server-side `TargetResponseTime` p95, by stage:

| concurrent | server p95 |
| --- | --- |
| 10 | ~35 ms |
| 50 | 40–80 ms |
| 100 | 0.7–1.3 s |
| 200 | **59 s** |

**Against a sized target of ~1 (launch day) and ~11 (a post doing 10× better than expected), that is
roughly 50× headroom to the comfortable limit and ~100× to the point of degradation.**

### The bottleneck is not the database, which is the opposite of what the plan assumed

Phase 7 task 2 says "adjust the RDS instance size and connection pool based on the results." The
result is: **don't.**

| | at collapse |
| --- | --- |
| RDS CPU | **24%** of a `db.t4g.micro` |
| RDS CPU credits | 287.9 of 288 — untouched |
| RDS connections | 25–35 of ~112 available |
| RDS IOPS | read 2.3, write 9.7 — the working set is in RAM |
| **API container CPU** | **95%** |
| **web container CPU** | **97%** |
| API / web memory | **12% / 25%** |

The constraint is **Fargate CPU at `maxTaskCount: 2`**, not the database. Two further readings:

- **The failure is capacity, not errors.** 849 load-balancer 5xx against 77 *target* 5xx. The
  application was not throwing; the ALB had nowhere to put the work. A 503 from the balancer and a
  500 from the app look identical in a browser and mean opposite things.
- **Memory is not the lever it looks like.** 12% and 25% used looks like waste, but 1024 MB is the
  *minimum* Fargate allows at 512 CPU units. Buying CPU means moving to 1024 units, which forces
  2048 MB. The over-provisioning is a consequence of the CPU choice, not a separate mistake.

**With a real catalogue the web tier saturates as hard as the API** (67% → 97%), so scaling only the
API would move the queue rather than shorten it. Both services would need raising together.

### Nothing was changed as a result, and that is the finding

Raising `maxTaskCount` is the cheap lever — Fargate bills per running task, so a higher cap costs
nothing until it is used. It is not being raised, because ~50× headroom against a derived target is
not a capacity problem, and autoscaling already reaches 2 tasks at the 60% CPU target.

Worth knowing for later: **scale-out takes 60–90 seconds and the collapse from 100 to 200 took less
than one minute.** Autoscaling does not save a service from a sharp spike; it saves it from a slow
climb.

---

## Rate limiting and the security pass (Phase 7 task 3)

### Knowing who is asking had to come first

Rate limiting keys on the client's address, and the application did not have it:
`request.client.host` behind an ALB is the ALB, so every audit row held one VPC address
(defect 32). Shipping limits against that value would have put the entire internet in one bucket,
and the tenth failed login anywhere would have locked the store.

The fix is `X-Forwarded-For`, read **from the right-hand end**. That header is appended to rather
than replaced, so a client can send its own and the balancer adds the address it saw after it. The
trustworthy entries are the ones our proxies appended; the leftmost is whatever the client chose.
Hence a **count** of trusted proxies rather than a boolean — `TRUSTED_PROXY_COUNT`, 1 in production,
**0 by default** so a laptop ignores a header that nothing has validated.

**Set the environment variable before deploying the code that reads it**, never after. Unknown
variables are ignored by the settings model (verified rather than assumed), so the old image
tolerates it; the reverse order would run the new limiter for one canary with every customer sharing
a bucket.

### Where the limits live, and what that costs

In-process, in-memory. The alternatives were AWS WAF at the load balancer and shared counters in
Postgres.

The threat here is not volumetric. It is credential stuffing, TOTP guessing and password-reset mail
bombing — low-rate, targeted, and stopped by counters that cost nothing. Two consequences are worth
stating rather than discovering:

- **Counters are per task**, so the real allowance is the limit times the running task count — two
  today. The numbers were chosen knowing that.
- **A restart forgets everything.**

**WAF is the documented upgrade, and the load test is the argument for it**: the ceiling is Fargate
CPU, not the database, so work rejected at the balancer costs a task nothing while work rejected in
the application has already been paid for. Worth buying when there is traffic to shape; ~$6/month to
solve a problem this store does not yet have.

| rule | allowance | why that number |
| --- | --- | --- |
| login | 10 / 5 min | someone who forgot tries three or four times, then uses the reset link |
| 2FA verify | 5 / 5 min | the tightest, because the search space is smallest — a six-digit code |
| forgot-password | 5 / hour | abuse is paid for by a stranger's inbox and our sending quota |
| reset-password | 10 / hour | guards the guessing rate; the tokens are already hashed and single-use |
| register | 5 / hour | generous, because one address may be a household |

None is tighter than that, for one reason: **office NAT and mobile carrier-grade NAT put many
customers behind one address.** A limit a busy household could reach generates support mail, not
security.

Forgot-password carries a **second key on the email address**, because it is the one endpoint whose
abuse lands somewhere we do not own. It is unreachable from a single address — the per-IP rule bites
first — so it exists for the distributed case. The trade taken deliberately: an attacker can spend a
victim's hourly allowance and delay their reset by an hour, against unbounded mail to that inbox. The
victim can still sign in normally throughout; this limits the reset path, not the account.

The limit is a **route dependency, not a check inside the handler**, so it runs before the bcrypt
comparison — the expensive step, and the one an attacker wants to make you perform.

**The counter map is bounded.** Its keys are attacker-controlled, so an unbounded dictionary is a
memory-exhaustion bug wearing a security feature's clothes, and Fargate kills a task that exceeds its
memory. Eviction can only ever forgive a client early, never refuse one who is inside their
allowance.

### The rest of the pass

**A password one byte too long returned 500 from an unauthenticated endpoint** (defect 31), which
handed anyone a switch for producing 5xx — and those feed the alarm ECS consults during a deployment
bake.

**The interactive schema is no longer served in production.** 108 KB naming all 62 routes, every
admin path and the shape of every request body. The endpoints were authenticated throughout; what
this removes is free reconnaissance. The flag **defaults to off**, so an environment configured
without thinking about it is the safe one.

**Security headers on the storefront**, which had none: HSTS (a year, no `preload` — that commitment
deserves its own decision), `nosniff`, `X-Frame-Options: DENY`, a referrer policy, and a permissions
policy. `x-powered-by` no longer announces the framework. Verified against a real response from the
built image rather than trusted to configuration.

**CSP shipped in Report-Only and is enforcing from 2026-09-01.** Stripe Elements mounts an iframe
from `js.stripe.com`; a policy that gets that wrong does not degrade, it stops customers paying at
the last step of the funnel. Its `script-src` still needs `'unsafe-inline'` because the App Router
injects inline bootstrap scripts — removing that needs nonce middleware, and until then the policy
stops less than it looks like it does.

**Report-Only earned its keep.** It caught two origins that no amount of reading the code would have
produced — one on the checkout path, one nowhere near it — and both would have been silent failures
rather than errors. **If a resource is blocked now, add the origin and redeploy; do not switch back
to Report-Only**, which would hide the next one as well. The console names the directive and the
blocked URL exactly.

**Three gaps were found by reading rather than by testing**, before anyone opened a browser —
against Stripe's own CSP guide and this repository's checkout code:

| directive | what was missing | what it would have cost |
| --- | --- | --- |
| `connect-src` | `https://fonts.googleapis.com` | **defect 16, exactly.** `payment-form.tsx` passes a `cssSrc` to `<Elements/>` and Stripe.js fetches that URL *itself* to inject Inter into its iframe — so it is a connection, not a stylesheet. Blocked, it would not error: it falls back to `system-ui` and the payment step renders in a different typeface from every other page |
| `script-src`, `frame-src` | `https://*.js.stripe.com` | Stripe.js starts frames on sibling origins where it can. Their guide lists the wildcard; the origins it picks vary, so this cannot be derived from what one working checkout happened to request |
| — | Link's hosts, **deliberately absent** | `payment-form.tsx` sets `wallets: { link: "never" }`, so there is no Link UI to frame. A policy should not admit hosts the code refuses to use |

The lesson is narrower than "read the docs": **a CSP cannot be derived from observing one successful
page load.** Wildcard origins, fallback fonts and features disabled in config all behave differently
from what a single trace shows.

### Why the last step is a person

The remaining check needs a real browser completing a real payment, and it is not automatable here.
The defect log already records two headless-Chrome probes built for defect 16 in which **the Payment
Element never got past its skeleton state** — so a headless run would report no violations for a form
that never rendered, which is indistinguishable from success and worse than not testing at all.

### The checkout test, and what it confirmed

Run in Incognito, on the deployed site, through a real test-mode purchase.

**Exactly the predicted violation appeared and nothing else**: four reports of
`connect-src` against `https://fonts.googleapis.com/css2?family=Inter…`, **sourced to `stripe.js`**.
That attribution is the part worth keeping — it confirms Stripe.js fetches the `cssSrc` itself,
which is why the font belongs in `connect-src` and not `style-src`. Enforcing the policy as it stood
would have dropped the payment form to `system-ui`: defect 16, silently, because a blocked font does
not error.

After the fix, a second purchase completed with **zero violations**. Everything left in the console
came from inside Stripe's own frames — a `web-vitals` TypeError in a `VM…` script with no source
URL, three `[Stripe.js]` advisories, and an `hcaptcha.html` passive-listener note. None of it ours;
`web-vitals` is not a dependency of this project.

### A clean checkout was not enough to enforce

The policy applies to every page, and the purchase path exercises one of them.

**`components/image-upload-field.tsx` PUTs uploads straight from the browser to a presigned S3 URL.**
The API never sees the bytes — that is the point of presigning — and it also makes the upload a
cross-origin connection the policy must permit. No part of checkout touches it, so no number of
successful purchases would have revealed it. It was found by asking which *other* pages make
external requests.

**Both hostname forms are listed, after getting it wrong once.** The first version carried only
`<bucket>.s3.<region>.amazonaws.com`, taken from a URL signed to check the shape — but signed with a
*different boto3 session than the application's*. us-east-1 resolves to the legacy global endpoint
`<bucket>.s3.amazonaws.com`, and the application's client produces that. Two clients, same bucket,
different hostnames; the check confirmed the shape of the wrong one.

**Signing a URL is not the same as signing it the way the application does.** The fix lists both:
they are two names for one bucket, not two grants, and AWS has been steering clients toward the
regional form, so which appears can change without any edit here.

It is built from `S3_BUCKET` rather than written down, because the name is account-specific and a
clone has its own — the same treatment as `CDN_HOST`, and needed at **build** time for the same
reason, since Next bakes the config into `routes-manifest.json` rather than reading it per request.

`deploy.yml` now verifies both. An absent `CDN_HOST` yields `remotePatterns: []` and every product
photo 404s; an absent `S3_BUCKET` drops the bucket from `connect-src` and, once enforcing, silently
refuses every admin image upload. Both are the same class of mistake: **a container that serves the
site perfectly and is broken somewhere nobody was looking.** Checked in both directions — a build
with the variable carries the host, a build without it fails the guard.

### Two things found and deliberately not changed

**CORS is absent, and that is correct.** The browser never calls the API — the web app reaches it
from Server Components — so no `Access-Control-Allow-Origin` means browsers refuse cross-origin reads
by default. Adding a CORS middleware would only widen it.

**CORS is absent, and that is correct** — see above. **Port 80** was closed; it now redirects, below.

---

## Redirecting port 80 (Phase 7 follow-up)

`http://imprimapress.com` used to fail to connect. Safe — there was nothing to intercept — but a
customer typing the bare domain got a connection error instead of the shop, and HSTS only helps
from the *second* visit onward.

**The security group already allowed port 80 from anywhere.** Nothing was listening, which is the
entire reason it failed. So this was one listener and no security-group change — worth checking
before assuming a firewall is the cause, because the two failures look identical from outside.

One HTTP listener, default action `redirect`:

| field | value | why |
| --- | --- | --- |
| `Host` | `#{host}` | one listener serves both names — the storefront apex and the API subdomain each keep their own host instead of being pinned to one |
| `Path` | `/#{path}` | `#{path}` **excludes** the leading slash, so the literal `/` is required. Omitting it yields no slash; adding two yields `//` |
| `Query` | `#{query}` | preserved, so a filtered catalogue link survives the hop |
| `StatusCode` | `HTTP_301` | permanent and cacheable, so a browser stops asking over plain HTTP at all |
| `Port` | **`443`, explicitly** | see below |

### `Port` must be written out, and the default reads like a trap

Omitting `Port` does not mean "no port". It defaults to **`#{port}` — the *original* port** — so an
HTTP request on 80 redirects to `https://host:80/`, which never connects. The field that looks
optional is load-bearing.

### A measurement mistake worth recording

Testing the omitted-`Port` variant appeared to show it producing an identical `:443` — which would
have meant the default was harmless. **It was a stale read: ALB listener changes take tens of
seconds to propagate, so each measurement returned the PREVIOUS configuration.** The `:80` arrived a
minute later, by which time the config had already been changed back, making the broken version look
like the working one and vice versa.

Both readings were of a real load balancer and both were wrong about the thing being tested. **After
changing a listener, wait for the value to stop moving before believing it** — the same discipline as
verifying a rollout from the control plane rather than the first response that comes back.

### `:443` in the Location header is unavoidable

Every ALB redirect emits an explicit port: `https://imprimapress.com:443/`. Browsers strip a default
port, so nobody sees it, and search engines normalise it. It cannot be configured away. If a
canonical URL matters for search, that belongs in the Next.js metadata as a `rel="canonical"` link —
the load balancer is the wrong layer to fix it at.

### Verified

Apex, `www`, and the API subdomain; a path with a query string; and end to end following the hop —
301 then 200, one hop, host and path and query intact. HTTPS timings unchanged as the control, since
"HTTP now redirects" is only good news if HTTPS still works.

### Watch for this on the next deploy

Express Mode created and manages this load balancer. **This listener was added outside it**, so a
future Express Mode operation could in principle reconcile it away. A deployment happens on every
push to main, so the check is cheap: `curl -sI http://imprimapress.com/ | grep -i location`.

---

## Closing the front door (TEMPORARY — delete this section with the rule)

**Why.** The site went live while Stripe was still in test mode. A visitor could register, fill a
cart and reach the payment step, where a real card is refused — no money moves, but the impression
is a broken shop. Worse, if a webhook endpoint is pointed here with the test-mode signing secret, a
visitor using a well-known test card number could drive an order to `paid`, decrementing stock and
sending a real confirmation now that SES sends.

**The switch is one additive ALB rule.** Priority `100`, ahead of Express Mode's own `44890` and
`44990`, matching `host-header` on the two public names and returning a `fixed-response` holding
page. Express Mode's rules are **not modified** — additive is the lowest-risk shape and deleting one
rule undoes it entirely.

**The generated hostname is deliberately not matched, and that is the whole design.** Requests to
`ma-<web>.ecs.us-east-1.on.aws` fall through to Express Mode's own rule and reach the web service
normally, so **that hostname is the admin door** while the brand domain is dark. The API rule is
untouched, which is required rather than incidental: the web app calls the API over its public
HTTPS URL and back through this same balancer.

**Why not "everyone except my IP".** ALB conditions AND together and there is no NOT, so an
exception needs a pass-through *forward* rule — and a hand-made forward rule has to name the
weighted target-group pair, which is exactly what "Extend the existing rules; do not add new ones"
below says breaks on the next canary. Using the generated hostname avoids inventing one.

**Why a 503 cannot block a deployment.** Both `default/manitou-{api,web}/RollbackAlarm` are metric
math over `HTTPCode_Target_4XX_Count`, `HTTPCode_Target_5XX_Count` and `RequestCount`, and
`manitou-alb-target-5xx` watches the target 5xx count. **A fixed-response never reaches a target**,
so it contributes to none of them. Checked against the live alarm definitions, not assumed. 503 also
tells crawlers the closure is temporary, where a 200 would invite indexing "Opening soon".

**What this is not.** It is not a blackout. The generated hostname serves the whole site and the API
stays public; both are what keep the admin working. It closes the door people actually arrive
through, nothing more.

**Same caveat as the port-80 listener above:** this rule was added outside Express Mode, so a future
Express Mode operation could in principle reconcile it away. The failure direction is the site
quietly coming *back up*, so check after any deploy.

### To close

```
LB=$(aws elbv2 describe-load-balancers --region us-east-1 \
  --query "LoadBalancers[?starts_with(LoadBalancerName,'ecs-express-gateway-alb')].LoadBalancerArn | [0]" --output text)
L=$(aws elbv2 describe-listeners --region us-east-1 --load-balancer-arn "$LB" \
  --query "Listeners[?Port==\`443\`].ListenerArn | [0]" --output text)

python3 -c "import json,pathlib; print(json.dumps([{'Type':'fixed-response','FixedResponseConfig':{'StatusCode':'503','ContentType':'text/html','MessageBody':pathlib.Path('infra/holding-page.html').read_text()}}]))" > /tmp/hold-actions.json

aws elbv2 create-rule --region us-east-1 --listener-arn "$L" --priority 100 \
  --conditions 'Field=host-header,HostHeaderConfig={Values=[imprimapress.com,www.imprimapress.com]}' \
  --actions file:///tmp/hold-actions.json \
  --tags Key=Name,Value=storefront-holding-page
```

### To reopen

```
LB=$(aws elbv2 describe-load-balancers --region us-east-1 \
  --query "LoadBalancers[?starts_with(LoadBalancerName,'ecs-express-gateway-alb')].LoadBalancerArn | [0]" --output text)
L=$(aws elbv2 describe-listeners --region us-east-1 --load-balancer-arn "$LB" \
  --query "Listeners[?Port==\`443\`].ListenerArn | [0]" --output text)
R=$(aws elbv2 describe-rules --region us-east-1 --listener-arn "$L" \
  --query "Rules[?Priority=='100'].RuleArn | [0]" --output text)

aws elbv2 delete-rule --region us-east-1 --rule-arn "$R"
```

**Listener changes take tens of seconds to propagate** — see the measurement mistake recorded above.
Re-read until two consecutive checks agree before believing either command worked.

```
curl -sI https://imprimapress.com/           # 503 while closed, 200 when open
curl -sI https://www.imprimapress.com/       # same
curl -sI https://api.imprimapress.com/health # 200 throughout
```

**When Stripe goes live:** run the reopen command, delete `infra/holding-page.html`, and delete this
section. It is scaffolding, not architecture.

---

## Email — sending and receiving (Phase 7)

Two directions, two providers, one DNS zone holding both. **They are independent**: SES sends and
never receives; ImprovMX receives and never sends. MX records govern inbound only, so adding them
could not affect sending — which is why the two halves below can be reasoned about separately.

### Outbound — SES

Production was running `EMAIL_SENDER=console`, which prints the message instead of sending it. So
**no mail was leaving the application at all**: a customer who forgot their password got nothing, and
the reset link they never received was sitting in a CloudWatch log group. Not a code defect — the
console sender did exactly what it says — but a deployment that had never been given the real one.

### The domain is the identity, not an address

SES verifies either an address or a domain. Domain verification wins here for a reason that has
nothing to do with scale: **verifying an address requires a mailbox that can receive the confirmation
mail**, and `support@imprimapress.com` has no mailbox behind it. Domain verification is DNS only, and
it additionally allows sending as any address at the domain later without a second round trip.

Easy DKIM, so SES publishes three CNAMEs and signs outgoing mail. Route 53 already hosts the zone, so
this was five records added in one change — never a replace, because the zone also holds the ALB
alias records and the ACM validation CNAME:

| record | value | why |
| --- | --- | --- |
| 3 × `<token>._domainkey` CNAME | `<token>.dkim.amazonses.com` | Easy DKIM. This is what actually authenticates the mail |
| apex TXT | `v=spf1 include:amazonses.com ~all` | see below |
| `_dmarc` TXT | `v=DMARC1; p=none;` | monitoring only, for now |

**`~all` rather than `-all`, deliberately.** DKIM is what authenticates SES mail, and DKIM survives
forwarding where SPF does not — so a hard fail buys very little and costs a silent outage the day a
second sender appears (a mailbox provider for `support@`, say). **`p=none` is monitoring, not
protection**: tighten to `quarantine` only after confirming alignment passes, or legitimate mail gets
binned by the record meant to protect it.

Verified in about twenty minutes: `VerifiedForSendingStatus: True`, `DkimAttributes.Status: SUCCESS`.

### The sandbox was the long pole

A new SES account is in the **sandbox**: 200 messages a day, one per second, and — the part that
matters — **it can only send to verified addresses**. Real customers cannot receive anything until
AWS grants production access, which is a request in the console and takes about a day.

So the domain being verified did not mean mail worked. `EMAIL_SENDER` stayed `console` until
production access was granted, because flipping it early would have sent nothing to real customers
while looking configured.

**Granted 2026-09-05, flipped 2026-09-06.** Production limits are 50,000 a day at 14 a second, which
is not a number this store will approach; the point of the grant is the removal of the
verified-recipient restriction, not the volume.

**The flip is a service configuration change, not a deploy.** The image tag does not move, so
nothing about it is visible to a watcher that tracks tags — what changes is the task definition
revision and one environment value. It reads the container definition whole and rewrites one field,
for the same reason `deploy.sh` does: send only the field you want and the environment and the
Secrets Manager references go with it, and the service comes back with no database password.

**Proven end to end rather than assumed.** A password reset was requested on the live site. The API
logged `SES accepted message`, which proves the first hop; SES then reported Send 1 and Delivery 1
with no bounce, complaint or reject, which proves the second. Those are different facts and a send
can succeed while still bouncing. The message reached a primary inbox rather than spam — the first
evidence that DKIM satisfies a major provider on a domain that had never sent before — the link
resolved, which is the only test `APP_BASE_URL` had ever had, and the reset completed.

**`p=none` still stands, and one message is not a sample.** Alignment passing once is not grounds to
tighten DMARC to `quarantine`. Leave it as monitoring until there is a run of real traffic to look
at, per the reasoning above.

### The From address is store config, not a new variable

`store.support_email` already appears in the storefront footer, and a reply to a reset email should
reach the inbox a customer would write to anyway. A clone edits one file instead of a file and an
environment variable.

### Permissions, scoped to the identity

The task role gained `ses:SendEmail` on the domain identity ARN only — a second inline policy, so the
S3 upload policy was not rewritten to add it.

A `ses:FromAddress` condition would be tighter still and was **rejected**: it would pin the policy to
a value that lives in `store-config.json`, so changing the support address would break sending in a
way that surfaces as an IAM error. The domain identity is the boundary that matters — it already
prevents sending as anyone else's domain — and the marginal gain over a task that can already read
the database is small.

### Bounces have somewhere to go, and it was checked rather than declared

The production-access form asks you to confirm *"you have a process in place for handling bounce and
complaint notifications."* Before this, half of that was true and the half involving a human was not:

- **Account suppression list: on** for `BOUNCE` and `COMPLAINT`, so SES already stopped resending to
  addresses that hard-bounced. That is the automatic half.
- **Feedback forwarding: on**, which mails bounce notices to the From address —
  `support@imprimapress.com`, **which has no mailbox**. Notices were going into a void.

So bounce and complaint notifications now publish to the existing `manitou-alerts` topic, and
forwarding is off. Reusing that topic rather than making another: it already has a confirmed email
subscription, a second would mean another confirmation link to find in a spam folder (task 11's went
there), and the volume on a store sized at ~1 concurrent user is negligible.

**The topic policy needed a statement.** It was still AWS's default, which does not let SES publish.
The added statement carries a `AWS:SourceAccount` condition — a service principal is not an identity,
and without the condition SES *in any account* could be induced to publish here.

**Proven with the mailbox simulator**, which works inside the sandbox and does not touch sending
reputation: `success@`, `bounce@` and `complaint@simulator.amazonses.com`. SNS recorded 4 published,
4 delivered, **0 failed**.

One expectation was wrong and is worth writing down. The check was going to be "the bounced address
appears on the suppression list" — it did not, and that is correct: **AWS deliberately exempts
simulator addresses from the suppression list** so the path can be tested repeatedly. Read as a
failure it would have sent someone hunting a working feature. The SNS delivery count is the evidence;
the suppression list is not.

### The task role was tested separately, and that mattered

The CLI sends above ran as an IAM user with `AdministratorAccess`. They proved SES works and proved
nothing about the policy the application runs under. Running the same call inside a Fargate task
carrying `manitou-api-task`:

| from address | result |
| --- | --- |
| `support@imprimapress.com` | **ALLOWED** |
| `nobody@example.com` | **DENIED** (`AccessDeniedException`) |

The refusal is what makes the permit meaningful — a grant wide enough to permit everything would have
passed the first row just as happily.

**A constraint of `run_in_vpc.sh` surfaced here:** it runs the **deployed** image, so a probe cannot
import code that has not shipped yet. The first attempt failed on `ImportError` for a class still
sitting uncommitted. Test the AWS boundary with boto3 directly when the code under test is not
deployed; test the class after it is.

### One failure the console sender was hiding

`ConsoleEmailSender.send` cannot fail; printing does not raise. So `/auth/forgot-password` called
`sender.send(...)` unguarded, and its account-enumeration property held **by accident**.

SES fails in ordinary ways — a throttle (one per second in the sandbox), a suppressed recipient, a
missing credential. Unguarded, a **known** address would answer 500 where an unknown one answers 202,
which is exactly the oracle that handler is shaped to deny. The send is now wrapped, deliberately
broadly, because the requirement is about the response rather than about a family of exceptions.

It is not silent: the sender logs the cause at WARNING, and the `manitou-app-warnings` metric filter
turns that into an alarm. Mail that stops going out pages somebody instead of being discovered by a
customer.

---

## Inbound — forwarding, not a mailbox

`support@imprimapress.com` is the From address on every message the store sends, and until this it
had nothing behind it: **replies bounced.** A store whose confirmation emails cannot be replied to is
a store that looks abandoned the first time somebody tries.

### AWS is not in the mailbox business, permanently

SES sends and can receive *programmatically* — into S3, or a Lambda — but it has no inbox anybody can
open. The AWS product that did was **WorkMail, and it is discontinued: end of support 31 March 2027,
new sign-ups already closed.** So this is not a gap to fill later with an AWS service; there will not
be one.

That is the **second** AWS sunset this project has walked into. Express Mode is here because App
Runner closed to new customers in April 2026. Worth carrying forward as a way of reading the
catalogue: the commodity primitives — S3, RDS running stock PostgreSQL, a load balancer — are
load-bearing for AWS's own business and safe to depend on. The convenience layers on top are the ones
that get retired.

### Forwarding beats a mailbox here

`support@` and `admin@` forward into an inbox that is already read every day. A real mailbox — Zoho,
Google Workspace — would be a second inbox to remember, and **an inbox nobody opens is worse than
none**: a customer replying gets silence either way, but the mailbox version also costs money and
looks like it works.

Two MX records at the apex, priority 10 and 20, pointing at `mx1`/`mx2.improvmx.com`. Free tier.

### The provider's DNS checker reports two "errors" that are not errors

Its dashboard shows **MX ✓✓ and SPF ✗**, and recommends:

    v=spf1 include:amazonses.com include:spf.improvmx.com -all

Neither half of that was adopted, and the reasoning matters more than the decision because the red
banner will still be there in six months tempting somebody to "fix" it.

**`include:spf.improvmx.com` is not needed for forwarding.** SPF authorises servers that send **as**
this domain. When mail is forwarded, the `From` is the *original sender* — `someone@example.com` —
so this domain's SPF is never evaluated in that path at all. The include only matters when sending
*outbound* through their SMTP, which is a paid feature this account does not use. Adding it anyway
would authorise ten IP ranges to send as the store, and spend one of SPF's **ten** permitted DNS
lookups, for a service that never sends. Confirmed empirically: a test message forwarded correctly
with the record exactly as it stands.

**`-all` versus `~all` is a policy preference, not a fault.** Their advice is not wrong — a hard fail
is stronger anti-spoofing, and would be safe today since SES is the only sender. But **DMARC is at
`p=none`, so neither qualifier is enforced**: receivers are told to take no action either way.
Changing it buys nothing until DMARC tightens, and DMARC must not tighten until `dkim=pass` has been
observed on a real message to a real inbox — which needs SES production access first. Tightening
before verifying alignment is how the record meant to protect the mail starts binning it.

So: a red banner, no action. It compares against a generic ideal rather than detecting a break.

### The catch-all was removed

The provider's default configuration included a `*` alias forwarding **every** address at the domain.
Deleted, leaving `support@` and `admin@` explicitly.

A catch-all is a standing invitation: spammers run dictionary attacks against domains specifically to
find them, every guess lands in the inbox, and forged bounces to addresses that never existed get
forwarded too. Explicit aliases cost one dashboard entry each and stop all of it.

### What is still missing

Replies **arrive**, but they arrive in a personal inbox and would be answered *from* that address
rather than from `support@`. Closing that gap needs Gmail's "send mail as" pointed at **SES SMTP
credentials** — the sending path that already exists, no new provider — and it only works once SES
production access is granted.

---

## The restore test (Phase 7 task 4)

Section 6.10's rule is that an untested backup is not a backup. Four encrypted automated snapshots
existed, 7-day retention, `available` — and nobody had ever restored one. `available` describes an
object nobody has looked inside.

Restored `rds:manitou-db-2026-09-01-08-57` to a throwaway `manitou-db-restoretest`: same class, same
subnet group, same security group, **private**, deletion protection off, tagged `ephemeral=true`.

### The numbers worth keeping

**Restore took about six minutes**, 04:01 → 04:07, through `configuring-enhanced-monitoring`,
`backing-up`, `modifying`, `available`. That is the recovery-time figure — and it is the answer to
"how long are we down", which no amount of reading the console tells you.

The recovery *point* is the other half. The snapshot was taken 08:57 and the newest production order
was created 13:58:

| | production | restored |
| --- | --- | --- |
| `alembic_version` | `8350f895449a` | **identical** |
| tables | 19 | 19 |
| orders | 5 | **4** |
| newest order | #5, 13:58 | **#4, 03:47** |
| media assets | 9 | 7 |
| total rows | 46 | 39 |

**Every difference is later than 08:57, and that is the point.** A restore that matched production
exactly would have meant the probe was pointed at the wrong database. Price snapshots came back
intact — `'T-Shirt (Large/Black)' @ 29.95 x1`, subtotal + tax + shipping = total — which counting
rows would not have shown.

### The finding: a restored instance has no readable password

Production uses an **RDS-managed master password**, rotated every 7 days. The restored instance came
back with **`MasterUserSecret: none`**.

So its master password is frozen at whatever it was when the snapshot was taken, and **no secret
anywhere holds that value**. This restore was usable only by coincidence: the last rotation was
2026-08-31 and the next is 2026-09-07, so the current production secret still happens to match.

**Restore after a rotation and you have a database you cannot log into.** The data is intact and
unreachable, which is a worse failure than an obvious one — you would be reading "available" while
locked out, in the middle of an incident.

**So the recovery procedure has a step the console does not mention:** immediately after
`restore-db-instance-from-db-snapshot`, run

    aws rds modify-db-instance --db-instance-identifier <restored> \
      --manage-master-user-password --apply-immediately

which has RDS generate and manage a fresh secret you can actually read. Do this before assuming the
restore succeeded, because a restore you cannot authenticate against has not succeeded.

This is exactly what the exercise exists to surface. Nothing about the snapshots, the retention
setting or the encryption looked wrong; the gap was in the step after them.

### Point-in-time recovery, tested separately

The snapshot test proved the daily path. PITR is the one you would actually reach for after a bad
migration or a mistaken delete, and it answers a different question, so it was run on its own.

**Tested without writing anything to production**, by using existing history as the fixture. The
database already contained two precisely dated events: order #4 created 03:47:49 on 2026-09-01, and
product #26 created at **04:28:58**. Restoring to **04:00** therefore has a falsifiable expected
answer, and it was written down before the restore ran:

| | 08:57 snapshot | 04:00 PITR predicted | actual |
| --- | --- | --- | --- |
| products | 2 | **1** | **1** |
| audit_events | 6 | **5** | **5** |
| orders | 4 | 4 | 4 |

A **28-minute window changes the answer**. That is the granularity claim demonstrated rather than
asserted — and the product, its variant, its inventory row and its audit event all disappear
together, so the restore is coherent at that instant rather than a partial reconstruction.

### The two paths trade off against each other

| | recovery time | recovery point |
| --- | --- | --- |
| Snapshot restore | **~6 minutes** | up to 24 hours of loss |
| Point-in-time restore | **~30 minutes** | ~5 minutes of loss |

PITR restores the base snapshot and then replays transaction logs, which is why it is far slower to
come back. **Neither is better.** After a bad migration you want PITR and you will wait for it; after
losing the instance you want the snapshot, because the lost day does not matter and the downtime
does.

### The missing password is a property of restoring, not of snapshots

`MasterUserSecret` came back **`(none)`** here too, exactly as on the snapshot restore. So
`modify-db-instance --manage-master-user-password` belongs in **any** recovery procedure, not just
the snapshot one.

### `EarliestRestorableTime` is absent, and that is not a limit

`DescribeDBInstances` does not return the field at all — confirmed against the raw response, not
inferred from a parse. `LatestRestorableTime` is present and current, and a PITR to 2026-09-01 04:00
was accepted, so continuous backup is working across the retention window regardless.

**Letting RDS adjudicate beat reasoning about the gap:** an out-of-window target fails with an error
naming the valid range, which is a better answer than any inference from a field that is not there.

### Cost and cleanup

A `db.t4g.micro` for under an hour — a few cents. Deleted with `--skip-final-snapshot
--delete-automated-backups`, after asserting the identifier was the throwaway and not production.
`infra/probes/db_census.py` is the reusable half: it takes a host override so the same probe
describes production and a restore, and the two outputs diff directly.

---

## GitHub Actions deploys without AWS keys

**No access keys anywhere.** The workflow assumes an IAM role through GitHub's OIDC provider, and
the role's trust policy names this repository and this branch. A stored access key would have none
of those properties and would still work after it leaked.

### Thumbprints are not required

`CreateOpenIDConnectProvider` accepts a `ThumbprintList`, and most guides supply one. AWS verifies
the provider's JWKS endpoint against its own library of trusted CAs, so the field can be omitted --
and should be, because a hardcoded thumbprint is a value that silently rots when GitHub rotates its
certificate.

### The subject claim was not the shape the examples show

The first deploy failed with `Not authorized to perform sts:AssumeRoleWithWebIdentity`, twelve times.
CloudTrail held the answer:

```
errorCode:  AccessDenied
sub claim:  repo:OWNER@163702382/REPO@1335310859:ref:refs/heads/main
trust policy: repo:OWNER/REPO:ref:refs/heads/main
```

**Repositories created after 15 July 2026 use GitHub's immutable subject claim**, which embeds the
numeric owner and repository IDs. Every example in circulation shows the older name-only form. It is
not a setting; it depends on when the repository was created.

Pinning the ID form is *better*, and that is worth understanding rather than treating as a
workaround: a repository rename changes the name and keeps the ID, and a repository deleted and
recreated under the same name gets a new one. Trust follows the actual repository rather than a
string someone else could later claim.

**The fix was the right string, not a looser comparison.** `StringEquals` stayed; relaxing it to
`StringLike` with wildcards would also have made it pass, by trusting repositories nobody intended.

### Read CloudTrail's event, not a projection of it

The diagnosis was nearly missed. `aws cloudtrail lookup-events --query '...ErrorCode' --output text`
printed `None` for all four events, which reads as "no error" and is actually "that field is not in
this projection" -- the AWS CLI prints `None` for an absent key. Parsing the full `CloudTrailEvent`
JSON showed `errorCode: AccessDenied` on every one.

`--output text` cannot distinguish an absent field from a null one, and both look like good news.

### `iam:PassRole` is scoped to three exact roles

Not `Resource: "*"`. Combined with ECS task-definition permissions, a wildcard `PassRole` is a
privilege-escalation path to every passable role in the account, Administrator included.

---

## Logs and alarms (task 11)

### The secrets half was already done

Task 11 in the plan reads "move secrets into Secrets Manager **and** set up CloudWatch logs and
alarms". The first half happened incidentally in tasks 7 and 10: `DB_PASSWORD` from the RDS-managed
secret, `JWT_SECRET` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` from `manitou/api`, each with a
`:field::` selector so one secret serves several variables and rotating one touches nothing else.
Everything left in plain environment is non-secret by inspection — `STRIPE_PUBLISHABLE_KEY` is
designed to be public.

### An alarm is not a notification

The account already had **six alarms and no way for any of them to reach a person.** Express Mode
creates them, and their actions are machinery rather than alerts:

- 4 × target-tracking alarms whose action is an Application Auto Scaling **policy ARN**.
- 2 × `RollbackAlarm` with **zero actions** — ECS reads the alarm state directly during a deployment
  bake. It watches deployments and nothing else.

**There were no SNS topics at all.** So the first thing this task built was the notification path,
not the alarms: a topic, an email subscription, and the confirmation click without which everything
downstream is decorative.

Two related traps worth naming:

- **`ALARM` does not mean "broken".** Two of the pre-existing alarms sit in `ALARM` permanently and
  correctly — a scale-in alarm fires when utilisation is *low*.
- **An email subscription starts `PendingConfirmation`** and looks identical to a working one in the
  console. The confirmation mail arrives from `no-reply@sns.amazonaws.com` and lands in spam
  routinely; ours did.

### Alarms chosen for what they would actually catch

| Alarm | Why this one |
| --- | --- |
| RDS `FreeStorageSpace` < 2 GiB | 20 GB with **storage autoscaling off**, so a full disk is a hard stop, not a slow degradation |
| RDS `DatabaseConnections` > ~~50~~ **24** | exhaustion looks like an application hang, not a database error. **50 was unreachable** — the API tops out at 30 (2 tasks × 15) — so the alarm could never fire. Corrected in Phase 7; see below |
| RDS `CPUCreditBalance` < 50 | **added in Phase 7.** A burstable instance has a second capacity dimension, and this one had nothing watching it |
| RDS `CPUUtilization` > 80% | the slow-burn precursor to timeouts |
| ALB `HTTPCode_Target_5XX_Count` | the store is returning errors to customers |
| ALB `UnHealthyHostCount` over 3 min | a task is failing health checks; three minutes so a deployment's normal churn does not page |
| ALB `TargetResponseTime` **p95** | p95 rather than Average — an average hides the slow tail users actually feel |
| `AppWarningCount` (metric filter) | log text no AWS metric reports |

`OKActions` is set as well as `AlarmActions`. An alert with no all-clear trains you to ignore alerts.

### The metric filter is the bridge between logs and metrics

Metrics are cheap, numeric and pre-aggregated; logs are expensive, textual and detailed. A **metric
filter** converts matching log lines into a metric you can alarm on — the only way to page on
something no metric reports. Here it counts the application's own `WARNING` lines, which catches
repeated Stripe webhook signature rejections: those return 400 and look like perfectly ordinary
traffic to the load balancer.

Two details that matter:

- The pattern anchors on **both** the level and the `app.` namespace. Matching bare `WARNING` would
  also catch any library that happens to print the word.
- `defaultValue: 0` is required. Without it the metric reports *nothing* when there are no warnings,
  and "no data" is not zero — the alarm could never return to OK.

### Retention, because the default is forever

Both log groups were `NEVER EXPIRE`, which is the default and a well-known source of surprise bills.
Now 30 days. The CloudWatch free tier is **5 GB combined across ingestion, storage and the scanning a
Logs Insights query does** — easy to misread as 5 GB each, and the reason the root logger is kept at
WARNING rather than INFO.

### Cost

Six pre-existing alarms plus seven new is 13 against a free tier of **10 alarm metrics**, so about
**$0.30/month**. Retention reduces cost rather than adding it.

### Verified

- The measurement that found defect 28, re-run inside the built image: `INFO enabled: True`, root
  still `WARNING`, botocore INFO still suppressed.
- A correctly-signed webhook for a non-existent intent produced the handler's INFO line in
  CloudWatch. Before this task that line did not exist and the endpoint still answered 200.
- **An alarm was deliberately tripped** — threshold temporarily set below the live value — and the
  alarm history recorded `Successfully executed action …manitou-alerts`, with the email arriving.
  Thresholds restored immediately from a captured copy rather than retyped. An alarm nobody has seen
  fire is not an alarm.

---

## The domain and HTTPS (task 10)

The store had two machine-generated `.on.aws` addresses. It now answers on a registered domain,
with the old names still working.

### Express Mode had already built most of this

The shared ALB's HTTPS listener was **already presenting two ACM certificates**, one per service,
selected by **SNI**. Adding a third is therefore the mechanism Express Mode itself uses, not a
workaround — which is also why one ALB can host 25 services with distinct hostnames.

### Extend the existing rules; do not add new ones

This is the decision the whole task turns on. Each Express Mode rule forwards to a **weighted pair**
of target groups:

```
web rule → tg-A (weight 100) + tg-B (weight 0)
api rule → tg-C (weight 0)   + tg-D (weight 100)
```

**A canary shifts those weights; it does not repoint the rule.** So a hand-made rule with the same
pair would work exactly once — after the next deployment it would send every request to a drained
target group, breaking on deploy rather than on the change, which is far harder to attribute.

Adding the new hostnames to the existing rules' `host-header` values instead means the custom names
ride on routing ECS keeps maintaining. `ModifyRule` was sent with **`Conditions` only**; omitted
`Actions` are left untouched, and the weights were confirmed still `100/0` afterwards rather than
assumed.

### One wildcard certificate, not three names

`<domain>` plus `*.<domain>`. ACM issues the **same validation CNAME** for an apex and its wildcard,
so it is one DNS record, and a future `cdn.<domain>` needs no new request. Note a wildcard covers one
label only: it matches `api.<domain>`, not `a.b.<domain>`.

Validation took about **15 seconds**, because Route 53 holds the zone and ACM writes nothing itself —
the records are ours to create.

### ACM renews only what is in use

Immediately after issuance the certificate reported `RenewalEligibility: INELIGIBLE`. Attaching it to
the listener flipped it to **`ELIGIBLE`**. Managed renewal applies to certificates associated with a
supported service, and it also depends on the validation CNAME still existing — delete that record
later and renewal fails silently, months afterwards.

### ALIAS, not CNAME

DNS forbids a CNAME at a zone apex, so the bare domain cannot CNAME to a load balancer. Route 53's
**ALIAS** is an AWS extension that resolves to the target's addresses at query time, works at the
apex, and costs nothing for queries to AWS resources. The ALB's `CanonicalHostedZoneId` — not the
zone the domain lives in — is what an ALIAS target needs; they are different values and mixing them
is the usual first error.

`AAAA` records were **not** created: the ALB reports `IpAddressType: ipv4`, so an AAAA ALIAS would
advertise addresses it does not have. Checked rather than copied from a tutorial.

### Verified

- All three hostnames answer 200 over TLS 1.3, certificate `CN=<domain>`, issued by Amazon.
- **The old `.on.aws` names still answer 200** — the control, and the only thing that distinguishes
  "the rule was extended" from "the rule was replaced".
- Forward weights unchanged after `ModifyRule`.

### The open question, now settled by experiment

Nothing in the AWS documentation says whether Express Mode reconciles listener-rule conditions and
strips a hostname it did not add. If it did, the custom domain would break on the next deployment
rather than on the change — so it was tested rather than hoped for.

**Both services were then rebuilt and deployed, and the rule conditions came back byte-identical.**
All three hostnames still answered 200, and the forward weights were still `100/0` and `0/100`. So
extending an Express Mode rule survives a deployment, and the CloudFront-in-front fallback is not
needed.

The canary is also visibly a *traffic* split, not just two running tasks: during the bake, successive
requests to the same URL returned the old and the new build alternately. Worth remembering when
verifying a deploy — one request proves nothing until the bake is over, which is why the checks above
sample ten.

---

## Rolling out a new image (learned during task 9b)

Tasks 7 and 8 recorded how these services were *created*. Neither recorded how a new image reaches
one, which is the operation actually performed most often.

The verb is **`aws ecs update-express-gateway-service`**, and the image lives inside
`--primary-container`, which is a structure rather than a string.

### Omitted top-level fields are preserved — measured, not assumed

The API documentation for `primaryContainer` is one sentence and does not say whether an update
merges with the running configuration or replaces it. The distinction is not academic: the API
service carries a `taskRoleArn` granting its S3 access, and a replace that dropped it would leave a
service that starts, passes its health check, and fails every upload.

So it was measured on the web service first, which has less to lose. The update passed
`--service-arn` and `--primary-container` and nothing else; afterwards `cpu`, `memory`,
`healthCheckPath`, `scalingTarget`, the security groups and **`executionRoleArn`** were all
unchanged. Omitted top-level fields survive.

**What that check does NOT establish**: whether the fields *inside* `primaryContainer` merge or
replace. The update sent a complete structure, so both semantics produce the same result and the
comparison cannot tell them apart. Send that structure complete every time and the question stays
harmless.

### Derive the container spec, do not retype it

The API's `primaryContainer` holds ten environment variables and three Secrets Manager ARNs. Typing
those by hand to change one tag is how a secret reference acquires a typo.

```
aws ecs describe-express-gateway-service --region <region> --service-arn "$ARN" \
  --query 'service.activeConfigurations[0].primaryContainer' \
  | jq '.image = "<repo>:<new tag>"' > /tmp/container.json

aws ecs update-express-gateway-service --region <region> \
  --service-arn "$ARN" --primary-container file:///tmp/container.json
```

This round-trips because every field `describe` returns for that structure — `image`,
`containerPort`, `environment`, `secrets`, `awsLogsConfiguration` — is also a field the update
accepts. Confirmed against the service model rather than by trying it.

### A feature spanning both services needs both deployed

Task 9b's media library is a modal in the web image calling an endpoint in the API image. The web
image was built, pushed and deployed first, and the library then failed — correctly, because
`GET /admin/assets` did not exist on the running API.

Cheap to detect, and worth doing *before* opening the browser to hunt for it:

```
curl -s <api-url>/openapi.json | jq -r '.paths | keys[] | select(startswith("/admin/assets"))'
```

Empty before the API deploy, the path after. FastAPI publishes its own schema, so the running
service can be asked what it implements rather than inferred from which commit was last pushed.
The general habit: **a deploy is of an image, not of a feature**, and a feature that crosses two
images is not deployed until both are.

### Verify a rollout from the control plane, never by probing it

**A verification loop once rolled back its own deployment.** Three requests every
twenty seconds to a page that existed only in the new image returned 404 from every
task still running the old one. Express Mode's `RollbackAlarm` counts 4xx, and on a
store with no real traffic the probe *was* the traffic: 75% error rate against a 1%
threshold. ECS reverted the deployment, correctly, on the evidence it had. The same
image deployed cleanly minutes later when the watching was done differently.

So while a rollout is in flight, watch it with:

```
aws ecs describe-tasks ...            # which image each RUNNING task carries
aws ecs describe-express-gateway-service ...   # what the service points at
aws cloudwatch describe-alarms --alarm-names .../RollbackAlarm
```

None of those touch the load balancer, so none of them can influence what they are
measuring. **Save HTTP checks for after the rollout finishes**, keep them few, and
prefer URLs that answer 2xx or 3xx — an unauthenticated admin page should give
**307** to the login screen, and a 404 from that same URL is exactly the signal
that must not be manufactured during a bake.

The general rule, which is not specific to AWS: **on a low-traffic service, a probe
that is expected to fail is indistinguishable from the service failing.** Usually
that only misleads whoever is reading the graph; during a deployment it decides the
outcome.

### Canary, and why the rollout is not instant

Express Mode deploys the new revision alongside the old, shifts a slice of traffic, watches the
health check and the service alarms through a bake period, and only then completes. A failing
revision rolls back on its own rather than waiting for someone to notice. That is the cost of the
few minutes, and it is the reason a deployment that "returned successfully" is not yet a deployment
that is serving — verify against the running service, not against the exit code.

---

## The media library (task 9b)

**No AWS resources were added.** This task is application work on top of task 9's bucket,
distribution and task role. It is recorded here because one decision is an AWS design decision, and
because the deferred piece needs an IAM change.

### Why the index lives in PostgreSQL and not in the bucket

The obvious thought is that S3 already knows what is in it, so `ListObjectsV2` could drive the
library. It cannot answer the questions the screen asks:

| The screen needs | `ListObjectsV2` gives |
| --- | --- |
| page 3 of the results | a continuation token — forward-only, no offset |
| newest first, or largest first | key order, and nothing else |
| "find the navy shirt photo" | no search of any kind |
| alt text, dimensions, who uploaded it | no application metadata |
| "which products use this?" | no idea what a product is |

So a `media_assets` row is written at the moment the upload is confirmed, and the bucket holds only
bytes. This is the general shape worth carrying into the exam: **an object store is for objects, and
the questions you want to ask *about* those objects belong in a database beside it.** The same
reasoning is why DynamoDB or RDS sits next to S3 in almost every reference architecture that has a
"browse my files" screen.

### The row is written on confirm, never on presign

The browser PUTs straight to S3 and the API never observes it. A row written when the URL was signed
would record uploads that were abandoned, refused by S3, or never attempted. `head_object` after the
fact is what turns "the client says it uploaded" into "the object exists, and is this size and this
type" — and size and content type are taken from that answer rather than from the client's claim.

### The library refuses when `CDN_HOST` is unset

Every row's public URL is built from the CDN host plus the key — never stored, so pointing a clone at
its own distribution stays a configuration change. The consequence is that with no host configured
there is no URL to return, so `GET /admin/assets` answers **503 naming the setting** rather than
listing images the caller cannot display. This is reachable in ordinary work: a development machine
pointed at the deployed database has the rows but not the host, and "the images are broken" and "this
machine is not configured" are worth telling apart.

The `web/public/` picker was kept below the library for the same reason — it is the only path that
works with no bucket at all, which is every development machine.

### Deleting an asset is deferred, deliberately

The task role can `PutObject` on two prefixes and nothing else. Deleting needs `DeleteObject` on
`media/*`, and that permission should not be granted before the guard that decides *whether* an asset
may be deleted works — which depends on `product_images.asset_id` being populated. It was not
populated until this task (defect 24): the column and its foreign key existed, and the write path
ignored them, so every asset looked unused. **A delete built on that would have reported every
in-use photograph as safe to remove.**

Granting the permission in the same change that first makes the guard meaningful is the wrong order,
so delete is its own task. The general lesson is the one IAM keeps teaching: a permission is easy to
add and hard to notice, so add it when the code that needs it is already correct.

---

## Region

Not yet fixed at time of writing. IAM is global, so nothing in task 3 depended on it.

**Task 4 pins it in practice** — RDS, ECR, ECS and S3 must all sit in the same region, or
cross-region data transfer charges and a great deal of confusion follow. Decide it deliberately
there rather than accepting a console default.

A default VPC was auto-created in `us-east-2` when the account activated (visible in CloudTrail as
`CreateDefaultVpcResources`). Convenient, but its subnets are public, and RDS must not be — which
is the decision task 4 actually turns on.
