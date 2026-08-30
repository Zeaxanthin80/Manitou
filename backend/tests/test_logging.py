"""Logging configuration (defect 28).

These assert a *global* -- the logging module's state is process-wide, so every
test here restores what it found. Without that, raising the level in one test
would silence assertions in another and the failure would look like a bug in the
code under test rather than in the fixture.

The regression these exist for is not "logging is misconfigured". It is that
logging was **entirely unconfigured** and nothing said so: the app started,
served traffic, and dropped every INFO line without a word.
"""

import logging

import pytest

from app.logging_setup import _HANDLER_NAME, configure_logging


@pytest.fixture(autouse=True)
def restore_logging():
    """Snapshot the process-wide logging state, hand over a clean slate, put it back.

    **Removing our handler first is load-bearing, not tidiness.** conftest imports
    `app.main`, which calls `configure_logging()` at import time and binds a
    handler to whatever `sys.stdout` was then. `configure_logging` is idempotent
    and reuses that handler, so a test asserting on captured output would be
    reading a stream captured before the test started -- and it showed exactly
    that: passing when the file ran alone, failing in the full suite, with pytest's
    own report displaying the line it claimed was missing.

    Clearing it means every test here configures logging genuinely rather than
    inheriting import-time state, so results do not depend on what ran first.
    """
    root = logging.getLogger()
    app_logger = logging.getLogger("app")
    saved = (list(root.handlers), root.level, app_logger.level)

    root.handlers[:] = [
        h for h in root.handlers if getattr(h, "name", None) != _HANDLER_NAME
    ]
    yield

    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    app_logger.setLevel(saved[2])


def test_the_webhook_logger_can_emit_info():
    """Defect 28 itself, as a regression test.

    Asserted on the real logger the webhook handler uses rather than on a logger
    made up here -- the defect was about that specific name resolving to an
    effective level of WARNING, and a synthetic logger would not have shown it.
    """
    configure_logging("INFO")

    assert logging.getLogger("app.routers.webhooks").isEnabledFor(logging.INFO)


def test_third_party_info_stays_suppressed():
    """The control for the test above, and the reason root is not just set to INFO.

    botocore and SQLAlchemy narrate every HTTP call and every query. CloudWatch
    charges for ingestion, storage AND the scanning a Logs Insights query does, so
    that noise is billed three times and read never.
    """
    configure_logging("INFO")

    assert not logging.getLogger("botocore").isEnabledFor(logging.INFO)
    assert not logging.getLogger("sqlalchemy.engine").isEnabledFor(logging.INFO)
    # ... but a real problem from a library still gets through.
    assert logging.getLogger("botocore").isEnabledFor(logging.WARNING)


@pytest.mark.parametrize(
    "level, info_enabled, debug_enabled",
    [
        ("DEBUG", True, True),
        ("INFO", True, False),
        ("WARNING", False, False),
        # Case is not the caller's problem.
        ("info", True, False),
    ],
)
def test_the_level_follows_the_setting(level, info_enabled, debug_enabled):
    """Asserts the level actually CHANGES, not merely that the call succeeded.

    A configure_logging that ignored its argument would pass any test checking
    only one level.
    """
    app_logger = configure_logging(level)

    assert app_logger.isEnabledFor(logging.INFO) is info_enabled
    assert app_logger.isEnabledFor(logging.DEBUG) is debug_enabled


def test_an_unknown_level_is_refused_rather_than_silently_ignored():
    """`logging.getLevelName("VERBOSE")` returns a string, not a number.

    Passing that to setLevel sets 0 (NOTSET), which inherits WARNING from root --
    quieter than asked for, and silent about it. That is precisely the failure
    this module exists to prevent, so it must not be reintroduced by a typo in an
    environment variable.
    """
    with pytest.raises(ValueError, match="not a logging level"):
        configure_logging("VERBOSE")


def test_calling_it_twice_does_not_duplicate_the_handler():
    """Imported at module scope in main.py, and again by these tests.

    A second handler means every line logged twice -- which doubles the bill to
    say the same thing, and makes a log look like a retry storm.
    """
    configure_logging("INFO")
    first = [h for h in logging.getLogger().handlers if getattr(h, "name", None) == _HANDLER_NAME]
    configure_logging("INFO")
    second = [h for h in logging.getLogger().handlers if getattr(h, "name", None) == _HANDLER_NAME]

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] is second[0], "the handler was replaced rather than reused"


def test_uvicorn_loggers_are_left_alone():
    """uvicorn installs its own handlers with propagate already False.

    Adding ours to them would emit every access line twice.
    """
    before = {
        name: list(logging.getLogger(name).handlers)
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error")
    }

    configure_logging("INFO")

    for name, handlers in before.items():
        assert logging.getLogger(name).handlers == handlers


def test_an_info_line_actually_reaches_the_stream(capfd):
    """The end of the pipe, not the middle.

    Every assertion above is about levels; this one is about a line of text
    arriving. A handler attached at the wrong level, or a formatter that raised,
    would pass all of them and still produce nothing -- which is the shape of the
    original defect.

    **capfd, not capsys**, and the difference is the point: capsys captures the
    `sys.stdout` object, capfd captures file descriptor 1. The container's log
    driver reads the descriptor, so capfd is what CloudWatch will see. Written
    with capsys first, this test failed while pytest's own report showed the line
    under "Captured stdout call" -- the line was real and the assertion was
    measuring the wrong end.
    """
    configure_logging("INFO")

    logging.getLogger("app.routers.webhooks").info("Stripe %s for %s -> %s",
                                                   "payment_intent.succeeded",
                                                   "pi_test", "confirmed")

    out = capfd.readouterr().out
    assert "pi_test" in out
    assert "confirmed" in out
    assert "app.routers.webhooks" in out
