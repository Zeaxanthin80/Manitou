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

## Region

Not yet fixed at time of writing. IAM is global, so nothing in task 3 depended on it.

**Task 4 pins it in practice** — RDS, ECR, ECS and S3 must all sit in the same region, or
cross-region data transfer charges and a great deal of confusion follow. Decide it deliberately
there rather than accepting a console default.

A default VPC was auto-created in `us-east-2` when the account activated (visible in CloudTrail as
`CreateDefaultVpcResources`). Convenient, but its subnets are public, and RDS must not be — which
is the decision task 4 actually turns on.
