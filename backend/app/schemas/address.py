from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AddressCreate(BaseModel):
    """A new address for the caller.

    `type` is a Literal rather than a plain str so Pydantic rejects anything else
    with a 422, matching the ck_addresses_type_valid CHECK constraint. Without it
    a bad value would reach the database and surface as a 500.

    There is no `user_id` field: the owner comes from the token, never the body.
    Same reasoning as UserCreate having no `role`.
    """

    line1: str = Field(min_length=1)
    line2: str | None = None
    city: str = Field(min_length=1)
    state: str | None = None
    postal_code: str = Field(min_length=1)
    country: str = Field(min_length=1)
    type: Literal["shipping", "billing"]
    is_default: bool = False


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line1: str
    line2: str | None
    city: str
    state: str | None
    postal_code: str
    country: str
    type: str
    is_default: bool
