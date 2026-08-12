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

_request_ip: ContextVar[str | None] = ContextVar("request_ip", default=None)


def current_ip() -> str | None:
    """The IP of the request being handled, or None outside a request.

    None is a legitimate value -- a seed script or a test calling a service
    directly has no request -- so callers must not treat it as an error.
    """
    return _request_ip.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Stash the client IP for the duration of one request.

    `request.client.host` is the address of whatever opened the TCP connection.
    Locally that is the browser. Behind the load balancer in Phase 6 it is the
    ALB, and the real client sits at the end of `X-Forwarded-For` -- which must
    NOT simply be trusted, because a client can send that header itself. Reading
    it safely means knowing how many proxies are in front of the app and taking
    the right entry from the right end. That is a Phase 6 decision, made when the
    topology exists; until then this records the direct peer and says so.
    """

    async def dispatch(self, request: Request, call_next):
        token = _request_ip.set(request.client.host if request.client else None)
        try:
            return await call_next(request)
        finally:
            # Reset rather than leave it set: the context can be reused, and a
            # stale IP on a later request would be worse than none at all.
            _request_ip.reset(token)
