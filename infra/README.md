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

**Open item, Phase 8:** flip `publicly_accessible` to No and replace the IP rule with the API's
security group, once ECS can apply migrations itself. The `/32` also needs re-editing whenever the
ISP reassigns the laptop's address.

### Settings that were chosen rather than defaulted

| Setting | Value | Reason |
| --- | --- | --- |
| Instance class | `db.t4g.micro` | Graviton, cheaper than t3. Section 10.1 sizes to the early-launch tier. |
| Availability | Single-AZ | Multi-AZ is ~2×. Section 6.10 puts it before launch — Phase 8. |
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
  project does not have yet. Phase 8, if the load test says so.

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
unreachable CVE. A distroless base would remove perl entirely; that is a Phase 8 question, not a
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

## Region

Not yet fixed at time of writing. IAM is global, so nothing in task 3 depended on it.

**Task 4 pins it in practice** — RDS, ECR, ECS and S3 must all sit in the same region, or
cross-region data transfer charges and a great deal of confusion follow. Decide it deliberately
there rather than accepting a console default.

A default VPC was auto-created in `us-east-2` when the account activated (visible in CloudTrail as
`CreateDefaultVpcResources`). Convenient, but its subnets are public, and RDS must not be — which
is the decision task 4 actually turns on.
