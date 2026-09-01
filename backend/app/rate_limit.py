"""Per-IP rate limiting for the endpoints worth guessing at.

**In-process and in-memory, deliberately.** The alternatives were AWS WAF at the
load balancer and shared counters in Postgres. This store is sized at roughly one
concurrent user (PROJECT_PLAN.md 10.1), and the threat here is not volumetric --
it is credential stuffing, TOTP guessing and password-reset email bombing, all of
which are low-rate and targeted. In-memory counters stop those for nothing.

Two honest consequences of that choice:

* **Counters are per task, so the real allowance is the limit times the number of
  running tasks** -- two today, and briefly more during a deployment. The limits
  below are set with that doubling in mind rather than pretending it away.
* **A restart forgets everything.** An attacker who could force restarts could
  reset their own budget; they would have bigger levers.

Move to WAF when there is traffic worth shaping. It sits in front of the
containers, which is the right place given the load test found CPU -- not the
database -- to be the ceiling: work rejected at the balancer never costs a task
anything.

**This is only as good as `current_ip()`.** Before defect 32 was fixed, every
request appeared to come from the load balancer, so a single bucket would have
covered the entire internet and the first person to hit a limit would have locked
out the store. Rate limiting had to wait for that fix, not the other way round.
"""

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from app.middleware import current_ip

#: Most distinct identities tracked at once, across every bucket.
#:
#: The keys are attacker-controlled -- one dictionary entry per source address --
#: so an unbounded map is a memory exhaustion bug wearing a security feature's
#: clothes. Fargate kills a task that exceeds its memory limit, which would turn
#: a flood into an outage. At roughly 100 bytes an entry this caps the structure
#: in the low megabytes.
MAX_TRACKED = 20_000


@dataclass(frozen=True)
class Rule:
    """How many requests, over how many seconds, and what to call it."""

    name: str
    limit: int
    window_seconds: int


# --- the rules ---------------------------------------------------------------
#
# Chosen against what a real person does, not against a round number.
#
# The shared-address caveat is the reason none of these is tighter: office NAT
# and mobile carrier-grade NAT put many customers behind one address, and a limit
# that a busy household could reach is a limit that generates support mail rather
# than security.

#: Ten sign-in attempts per five minutes. A person who has forgotten their
#: password tries three or four times and then uses the reset link; ten is
#: comfortably above that and far below what online guessing needs.
LOGIN = Rule("login", limit=10, window_seconds=5 * 60)

#: Five per five minutes, and the tightest rule here because the search space is
#: smallest: a TOTP code is six digits. Without this, holding a password and
#: guessing codes is arithmetic rather than cryptography.
MFA_VERIFY = Rule("mfa_verify", limit=5, window_seconds=5 * 60)

#: Password reset sends mail to somebody else's inbox, so the cost of abuse is
#: paid by a third party. Five an hour per address is plenty for a real person
#: who did not receive the first one.
FORGOT_PASSWORD = Rule("forgot_password", limit=5, window_seconds=60 * 60)

#: Reset tokens are hashed, single-use and short-lived, so this guards the
#: guessing rate rather than the tokens themselves.
RESET_PASSWORD = Rule("reset_password", limit=10, window_seconds=60 * 60)

#: Account creation. Generous, because a shared address may hold a household.
REGISTER = Rule("register", limit=5, window_seconds=60 * 60)


class _Limiter:
    """Sliding-window counters, bounded in size and safe across threads.

    A `deque` per identity holding the timestamps of recent requests, capped at
    the rule's limit -- so memory per key is fixed rather than proportional to
    how hard someone is trying.

    The lock is not optional: uvicorn runs `def` endpoints in a threadpool, so
    two requests genuinely execute this concurrently, and `dict` mutation from
    several threads is exactly the kind of race that shows up as a rare,
    unreproducible error months later.
    """

    def __init__(self) -> None:
        self._hits: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, rule: Rule, identity: str) -> float | None:
        """Record a request. Returns seconds to wait if it should be refused.

        None means allowed. A float means refused, and is what `Retry-After`
        should say.
        """
        key = (rule.name, identity)
        now = time.monotonic()

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque(maxlen=rule.limit)
                self._hits[key] = hits
            self._hits.move_to_end(key)

            # Drop anything that has aged out of the window.
            cutoff = now - rule.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= rule.limit:
                # Refused. Deliberately does NOT record this attempt: counting
                # rejections would extend the block every time someone retried,
                # so a client polling once a second would never be let back in.
                return hits[0] + rule.window_seconds - now

            hits.append(now)

            if len(self._hits) > MAX_TRACKED:
                self._evict()
            return None

    def _evict(self) -> None:
        """Called with the lock held. Drop empty buckets, then the oldest.

        Eviction can only ever *forgive* a client early, never block an innocent
        one -- so an over-eager sweep costs a little enforcement and no
        correctness.
        """
        for key in [k for k, v in self._hits.items() if not v]:
            del self._hits[key]
        while len(self._hits) > MAX_TRACKED:
            self._hits.popitem(last=False)   # least recently touched

    def reset(self) -> None:
        """Forget everything. For tests, which must not inherit each other's
        counters -- and which would otherwise fail in whatever order pytest
        happened to run them."""
        with self._lock:
            self._hits.clear()


limiter = _Limiter()


def _refuse(retry_after: float) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Try again shortly.",
        # Seconds, rounded up: a client told to wait 0 retries immediately.
        headers={"Retry-After": str(max(1, int(retry_after) + 1))},
    )


def enforce(rule: Rule, identity: str | None) -> None:
    """Apply a rule to an identity, raising 429 if it is over.

    `None` identity means the address is unknown -- an in-process call, or a test
    client with no peer. Those are not rate limited, because the alternative is
    lumping every unknown caller into one shared bucket, which is the same bug
    defect 32 would have caused.
    """
    if identity is None:
        return
    retry_after = limiter.check(rule, identity)
    if retry_after is not None:
        _refuse(retry_after)


def by_ip(rule: Rule):
    """A dependency that limits a route by client address.

        @router.post("/login", dependencies=[Depends(by_ip(LOGIN))])

    Declared as a dependency rather than called in the body so the limit applies
    before the handler runs at all -- including before the password hash, which
    is the expensive part and the one an attacker wants to make you do.
    """

    def dependency() -> None:
        enforce(rule, current_ip())

    return Depends(dependency)
