"""Per-request context that would otherwise have to be threaded through everything.

Right now that is one thing: the client's IP address, which the audit trail
records. Passing it explicitly would mean adding `request: Request` to every
endpoint that audits -- and, worse, silently recording nothing the day someone
adds an audited endpoint and forgets.

A ContextVar is the right tool rather than a global because each request gets its
own value: contextvars are copied into each task's context, so two concurrent
requests never see each other's IP.
"""

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

_request_ip: ContextVar[str | None] = ContextVar("request_ip", default=None)


def client_ip(request: Request) -> str | None:
    """The address of the actual client, accounting for proxies in front.

    `request.client.host` is whoever opened the TCP connection: the browser on a
    laptop, and the load balancer in production. Recording that unconditionally
    is what filled the audit trail with one VPC address (defect 32).

    **X-Forwarded-For is appended to, not replaced.** A client may send its own,
    and the ALB adds the peer address to the end rather than discarding what
    arrived. So a request sent with `X-Forwarded-For: 1.2.3.4` is forwarded as::

        X-Forwarded-For: 1.2.3.4, <the real client address>
                         ^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^
                         forged   added by our load balancer

    Reading the LEFTMOST entry -- the common shortcut, and what most snippets
    show -- takes the attacker's value. Every entry we can trust was appended by
    a proxy we run, so they are at the right-hand end, and the client is the
    `trusted_proxy_count`-th from the end.

    With the setting at 0 the header is ignored entirely. That is the correct
    default rather than a cautious one: with nothing in front, anyone could set
    the address that lands in the audit trail and that rate limits are counted
    against.
    """
    peer = request.client.host if request.client else None
    hops = settings.trusted_proxy_count
    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        # Behind a proxy that sent no header. Something is wrong with the
        # topology, so fall back to the peer rather than inventing an address.
        return peer

    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(chain) < hops:
        # Fewer entries than proxies means the chain is shorter than configured;
        # the leftmost is the closest we have and no entry is attacker-supplied.
        return chain[0] if chain else peer
    return chain[-hops]


def current_ip() -> str | None:
    """The IP of the request being handled, or None outside a request.

    None is a legitimate value -- a seed script or a test calling a service
    directly has no request -- so callers must not treat it as an error.
    """
    return _request_ip.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Stash the client IP for the duration of one request.

    Resolved by `client_ip` above, which knows how many proxies are in front and
    reads `X-Forwarded-For` from the correct end. This was deferred until "the
    topology exists" and then not revisited when it did -- so every audit row
    written after the Phase 6 deployment recorded the load balancer. Defect 32.
    """

    async def dispatch(self, request: Request, call_next):
        token = _request_ip.set(client_ip(request))
        try:
            return await call_next(request)
        finally:
            # Reset rather than leave it set: the context can be reused, and a
            # stale IP on a later request would be worse than none at all.
            _request_ip.reset(token)
