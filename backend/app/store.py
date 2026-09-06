"""Store configuration.

Deliberately separate from app/config.py. That module reads .env -- secrets and
per-environment values (database URL, JWT secret, Stripe keys) that differ
between a laptop and production. This module reads store-config.json, which is
store *identity*: the same in every environment, different in every clone.

Confusing the two is how a cloned store ends up hunting through Python for a
currency code. PROJECT_PLAN.md Section 1.1 calls this one of the three seams
that make cloning work.

Validated with Pydantic so a malformed config fails loudly at startup rather
than producing a wrong tax total at checkout.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# repo root -- app/store.py -> app -> backend -> repo
CONFIG_PATH = Path(__file__).resolve().parents[2] / "store-config.json"


class StoreIdentity(BaseModel):
    name: str = Field(min_length=1)
    #: Optional path to a wordmark or logo, served from web/public.
    #:
    #: EMPTY BY DEFAULT, and that is the intended state for most clones. The
    #: header renders `name` in the display font when this is blank, so a clone
    #: gets a correctly styled wordmark by editing one string -- no artwork
    #: required. Set it only when there is a real mark to point at.
    #:
    #: SVG is the format to use: it stays crisp at any density, weighs a couple
    #: of kilobytes, and -- unlike a text wordmark -- cannot silently fall back
    #: to a different typeface if the font fails to load.
    logo: str = ""
    support_email: str
    #: One line of store voice, shown in the footer's brand block. It had a
    #: second home on the home page until the hero replaced that headline.
    #:
    #: EMPTY IS A VALID STATE, and it is what ImprimaPress ships. Naming the
    #: runs as short raises a question a footer cannot answer -- whether a thing
    #: can sell out, how long a reprint takes, and what that does to delivery --
    #: so the line was removed rather than reworded.
    #:
    #: Same convention as `logo` above: the key stays, the value empties, and no
    #: component changes. Blank renders nothing at all rather than an empty
    #: paragraph; see web/components/site-footer.tsx.
    tagline: str = ""

    @field_validator("logo")
    @classmethod
    def _must_be_a_public_path(cls, value: str) -> str:
        """A bare filename would 404 and leave a broken image in the header.

        Checked here rather than trusted, because the failure is silent in the
        place it matters most: the header renders, the alt text stands in, and
        nothing reports a fault.
        """
        if value and not value.startswith(("/", "http://", "https://")):
            raise ValueError(
                f"store.logo must be a public path like /logo.svg (got {value!r}). "
                "Put the file in web/public and reference it from the root."
            )
        return value


class Currency(BaseModel):
    code: str = Field(min_length=3, max_length=3)


class Tax(BaseModel):
    """`none` charges nothing. `flat` applies `rate` to the subtotal.

    Destination-based tax is deliberately absent: it needs jurisdiction rules
    that belong to Stripe Tax in Phase 5, not to a JSON file.
    """

    mode: Literal["none", "flat"]
    rate: Decimal = Field(ge=0)


class Shipping(BaseModel):
    mode: Literal["flat"]
    rate: Decimal = Field(ge=0)


class Checkout(BaseModel):
    """How long an unpaid order keeps holding its stock.

    Store behaviour, not a secret and not per-environment, so it belongs here
    rather than in .env: a grocery clone picking stock the same morning wants a
    much shorter window than a T-shirt store.

    The floor is 1 rather than 0. Zero would mean orders stop reserving the
    instant they are placed, so two customers could buy the last unit in the same
    breath -- silently turning the guard off through configuration.
    """

    reservation_minutes: int = Field(ge=1)


class Carrier(BaseModel):
    """One shipping company the vendor can dispatch with.

    `tracking_url` is a template containing `{tracking}`. It lives beside the
    carrier rather than in a lookup somewhere in the web app, because the pairing
    is per-store: a UK clone's list is Royal Mail and Evri, and a TRACKING_URLS
    dict in a component would hand it American links.
    """

    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tracking_url: str = Field(min_length=1)

    @field_validator("tracking_url")
    @classmethod
    def _must_take_a_tracking_number(cls, value: str) -> str:
        """Refuse a URL with nowhere to put the number.

        Without the placeholder the link still renders and still looks clickable
        -- it just lands on the carrier's homepage. A customer chasing a parcel
        finds a search box, and nothing in the system ever reports a fault.
        """
        if "{tracking}" not in value:
            raise ValueError(
                "tracking_url must contain the {tracking} placeholder, or the "
                "link goes to the carrier's homepage instead of the parcel."
            )
        return value


class Fulfilment(BaseModel):
    """How goods reach the customer.

    The Section 1.1 seam. T-shirts and candles ship by carrier; the grocery clone
    delivers with its own staff and has no carriers at all; a market stall is
    collected. One config value picks which, and the schema accepts all three
    with no migration.
    """

    method: Literal["carrier", "courier", "pickup"]
    carriers: list[Carrier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _carrier_method_needs_carriers(self) -> "Fulfilment":
        """A carrier store with no carriers must not boot.

        Left unvalidated, the app starts cleanly and the vendor discovers it at
        the first dispatch -- an empty picker, with a parcel in hand and an order
        that cannot be advanced. Same instinct as defect 12: a configuration
        mistake should be found by whoever deployed it, not by whoever is trying
        to work.
        """
        if self.method == "carrier" and not self.carriers:
            raise ValueError(
                'fulfilment.method is "carrier" but fulfilment.carriers is empty. '
                "Add at least one carrier, or change the method to courier or pickup."
            )
        return self

    def carrier_by_code(self, code: str) -> Carrier | None:
        return next((c for c in self.carriers if c.code == code), None)

    def tracking_url_for(self, code: str, tracking_number: str) -> str | None:
        """The customer-facing link, or None if we cannot build one.

        None rather than a bare carrier homepage: a link that does not reach the
        parcel is worse than no link, because it looks like it worked.
        """
        carrier = self.carrier_by_code(code)
        if carrier is None or not tracking_number:
            return None
        return carrier.tracking_url.replace("{tracking}", tracking_number)


class Catalog(BaseModel):
    default_unit_of_measure: str = Field(min_length=1)


class Features(BaseModel):
    variants_enabled: bool
    weight_pricing_enabled: bool


class StoreConfig(BaseModel):
    store: StoreIdentity
    currency: Currency
    locale: str
    tax: Tax
    shipping: Shipping
    checkout: Checkout
    fulfilment: Fulfilment
    catalog: Catalog
    features: Features

    def tax_for(self, subtotal: Decimal) -> Decimal:
        """Tax on a subtotal, quantised to 2dp.

        Money is Decimal end to end -- never float. Rounding once here, rather
        than letting an unrounded value reach numeric(10,2), keeps the total the
        customer sees identical to the total stored.
        """
        if self.tax.mode == "none":
            return Decimal("0.00")
        return (subtotal * self.tax.rate).quantize(Decimal("0.01"))

    def shipping_for(self, subtotal: Decimal) -> Decimal:
        return self.shipping.rate.quantize(Decimal("0.01"))


def _load() -> StoreConfig:
    with CONFIG_PATH.open() as fh:
        raw = json.load(fh)
    raw.pop("_meta", None)  # documentation, not configuration
    return StoreConfig.model_validate(raw)


store_config = _load()
