"""Make the application's logging actually reach stdout.

**Why this file exists at all.** Nothing configured logging, so Python's root
logger sat at its default WARNING with no handlers, and the "handler of last
resort" wrote warnings to stderr and discarded everything below. Every
`logger.info` in the application was silently dropped in production -- including
the one line recording what a Stripe webhook did to an order, which is the
closest thing the API has to an unattended-change trace. That was defect 28.

The lesson worth keeping is not "call basicConfig". It is that **a subsystem
with a working default can be entirely unconfigured and still look fine**: the
app started, answered 200, and produced no sign that half its logging was going
nowhere. Defect 27 was the same shape one layer up -- a variable with a working
default that production never set.

**Three deliberate choices:**

1. *A handler on the ROOT logger, formatted.* So a warning from any library is
   formatted the same way as one of ours, rather than arriving via the last-resort
   handler in a different shape.

2. *Root stays at WARNING; only the `app` logger takes LOG_LEVEL.* Setting root
   to INFO would enable INFO on botocore, urllib3 and SQLAlchemy, which narrate
   every HTTP call and every query. CloudWatch charges for ingestion, storage and
   the scanning a Logs Insights query does, so that noise is billed three times
   and read never. Every logger in this app is `logging.getLogger(__name__)` under
   the `app` package, so one setting covers all of them.

3. *uvicorn's loggers are left alone.* uvicorn installs its own handlers on
   `uvicorn`, `uvicorn.error` and `uvicorn.access`, with `propagate` already
   False. Touching them risks a second copy of every access line -- doubling the
   log bill to say the same thing twice.

Idempotent, because it is called at import time in `main.py` and again by the
tests, and a handler added twice prints everything twice.
"""

import logging
import sys

from app.config import settings

#: Named so a second call can find its own handler rather than counting them --
#: pytest and uvicorn's reloader both import this module more than once.
_HANDLER_NAME = "manitou-stdout"

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: str | None = None) -> logging.Logger:
    """Attach one formatted stdout handler and set the app logger's level.

    Returns the `app` logger, so a caller can assert on it rather than reaching
    into the logging module to find out whether this worked.

    `level` overrides the setting, which exists for tests -- production passes
    nothing and gets LOG_LEVEL.
    """
    root = logging.getLogger()

    handler = next(
        (h for h in root.handlers if getattr(h, "name", None) == _HANDLER_NAME), None
    )
    if handler is None:
        # sys.stdout resolved HERE rather than at import: binding it at module
        # scope captures whatever stdout happened to be when this file was first
        # imported, which is not necessarily the one the process ends up writing
        # to.
        #
        # stdout, not stderr. The ECS awslogs driver captures both, but a
        # container writing ordinary operation to stderr makes "is anything
        # wrong?" unanswerable by stream. PYTHONUNBUFFERED=1 in the Dockerfile is
        # what stops these lines sitting in a block buffer until it fills -- or
        # being lost entirely when a task is killed mid-buffer.
        handler = logging.StreamHandler(sys.stdout)
        handler.name = _HANDLER_NAME
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)

    # The handler passes everything; the loggers decide. Filtering here instead
    # would mean the app logger's level was advisory, and raising LOG_LEVEL to
    # DEBUG would silently do nothing.
    handler.setLevel(logging.NOTSET)
    root.setLevel(logging.WARNING)

    app_logger = logging.getLogger("app")
    resolved = (level or settings.log_level).upper()
    # An unknown name would otherwise be accepted and set the level to 0
    # (NOTSET), which inherits WARNING from root -- quieter than asked for, and
    # silent about it. Exactly the class of failure this module exists to fix.
    if not isinstance(logging.getLevelName(resolved), int):
        raise ValueError(
            f"LOG_LEVEL={resolved!r} is not a logging level. "
            "Use DEBUG, INFO, WARNING, ERROR or CRITICAL."
        )
    app_logger.setLevel(resolved)

    return app_logger
