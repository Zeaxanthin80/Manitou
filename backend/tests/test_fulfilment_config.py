"""The fulfilment block in store config.

Carrier lists are store identity, not application logic: this build ships USPS,
UPS and FedEx, a UK clone ships Royal Mail, and the grocery clone has no carriers
at all because its own staff deliver. Putting that list in Python would make
cloning the store an exercise in editing code -- the thing PROJECT_PLAN Section
1.1's seams exist to prevent.
"""

import pytest
from pydantic import ValidationError

from app.store import Carrier, Fulfilment, store_config


def test_the_default_build_ships_by_carrier():
    f = store_config.fulfilment
    assert f.method == "carrier"
    assert [c.code for c in f.carriers] == ["usps", "ups", "fedex"]


def test_a_carrier_store_with_no_carriers_refuses_to_boot():
    """A configuration mistake should be found by whoever deployed it.

    Left unvalidated the app starts cleanly and the vendor discovers it at the
    first dispatch: an empty picker, a parcel in hand, and an order that cannot
    be advanced. Same instinct as defect 12.
    """
    with pytest.raises(ValidationError, match="carriers is empty"):
        Fulfilment(method="carrier", carriers=[])


@pytest.mark.parametrize("method", ["courier", "pickup"])
def test_courier_and_pickup_need_no_carriers(method):
    """The grocery clone has none, and that is not an error.

    This is the control for the test above -- without it, a validator that
    rejected EVERY empty list would pass and would break the very clone the seam
    exists for.
    """
    assert Fulfilment(method=method, carriers=[]).carriers == []


def test_a_tracking_url_without_the_placeholder_is_refused():
    """A link that does not reach the parcel is worse than no link.

    It still renders, still looks clickable, and lands on the carrier's
    homepage. The customer finds a search box and nothing reports a fault.
    """
    with pytest.raises(ValidationError, match="{tracking}"):
        Carrier(code="x", name="X", tracking_url="https://example.com/track")


def test_tracking_url_is_built_from_the_template():
    url = store_config.fulfilment.tracking_url_for("usps", "9400111899223197428490")
    assert url == (
        "https://tools.usps.com/go/TrackConfirmAction?tLabels=9400111899223197428490"
    )
    assert "{tracking}" not in url


@pytest.mark.parametrize(
    "code,number", [("royalmail", "123"), ("usps", "")],
    ids=["unknown carrier", "no tracking number"],
)
def test_no_link_rather_than_a_broken_one(code, number):
    assert store_config.fulfilment.tracking_url_for(code, number) is None


def test_an_unknown_method_is_refused():
    with pytest.raises(ValidationError):
        Fulfilment(method="teleport", carriers=[])
