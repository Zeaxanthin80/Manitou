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

from pydantic import BaseModel, Field

# repo root -- app/store.py -> app -> backend -> repo
CONFIG_PATH = Path(__file__).resolve().parents[2] / "store-config.json"


class StoreIdentity(BaseModel):
    name: str = Field(min_length=1)
    support_email: str
    # One line of store voice, shown on the home hero and in the footer. Here
    # rather than in a component so a clone changes its pitch by editing config.
    tagline: str = Field(min_length=1)


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
