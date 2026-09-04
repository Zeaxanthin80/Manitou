"""The store block in store config -- specifically the optional logo.

The header renders `store.name` in the display font when `store.logo` is empty
and an <img> when it is set. Both are first-class: a clone gets a finished-
looking masthead by editing one string, and swaps in artwork by editing another.
That makes the empty string a supported value rather than a placeholder, which
is what these tests pin down.
"""

import pytest
from pydantic import ValidationError

from app.store import CONFIG_PATH, StoreIdentity, store_config

# The other required fields, so a case can vary `logo` alone. Omitting these was
# the first version of this file, and every case failed -- including the ones
# that should have passed. A control that fails is a broken instrument, not a
# finding.
BASE = dict(name="Manitou", support_email="support@example.com", tagline="A tagline")


def test_the_default_build_points_its_logo_at_a_file_that_exists():
    """The committed config carries the field, and the file is really there.

    This used to assert the field was EMPTY, on the reasoning that a clone
    opening store-config.json should be able to see the option exists. That
    reasoning survives; the assertion did not. ImprimaPress has a wordmark now,
    and a filled-in example is strictly more discoverable than an empty string.

    What replaced it is the check the empty version could never make. The
    validator in app/store.py refuses a path that cannot resolve from a route,
    but it cannot know whether anything is at the end of a well-formed one -- and
    a logo pointing at a missing file is the module's own nightmare: the header
    renders, the alt text stands in, nothing logs, and the store looks subtly
    unfinished. Renaming or dropping the artwork now fails here instead.

    Skipped for an absolute URL, which is a supported value (Phase 6 may move
    assets to CloudFront) and not something a test run can reach.
    """
    logo = store_config.store.logo
    assert logo, "the default build ships a wordmark; see web/public/"

    if logo.startswith("/"):
        served = CONFIG_PATH.parent / "web" / "public" / logo.lstrip("/")
        assert served.is_file(), f"store.logo points at {logo}, which is not in web/public/"


def test_the_field_may_be_omitted_entirely():
    """A clone whose config predates this field must still boot.

    The whole point of a default is that adding an option cannot break an
    existing store, and this is the test that would catch it becoming required.
    """
    assert StoreIdentity(**BASE).logo == ""


@pytest.mark.parametrize(
    "path",
    [
        "/logo.svg",
        "/brand/wordmark.svg",
        "https://cdn.example.com/logo.svg",
    ],
)
def test_a_public_path_or_absolute_url_is_accepted(path):
    """The control for the refusals below.

    Without it, a validator that rejected every non-empty value would pass the
    next three tests and make the feature impossible to use -- the exact shape
    of failure a refusal test alone cannot see. The URL case matters for Phase 6,
    where assets may move to CloudFront.
    """
    assert StoreIdentity(**BASE, logo=path).logo == path


@pytest.mark.parametrize(
    "path",
    [
        "logo.svg",         # bare filename -- 404s from every route
        "./logo.svg",       # relative -- resolves differently per route
        "public/logo.svg",  # the on-disk path, not the served one
    ],
)
def test_a_path_that_will_not_resolve_is_refused_at_boot(path):
    """Because the failure is otherwise silent in the one place it shows.

    A broken src does not raise, does not log and does not fail a build: the
    header renders, the alt text stands in for the missing image, and the store
    looks subtly unfinished with nothing reporting why. Better to refuse to
    start, where whoever just edited the config is still watching.
    """
    with pytest.raises(ValidationError, match="must be a public path"):
        StoreIdentity(**BASE, logo=path)
