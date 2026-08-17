"""Deciding which images belong to which variant.

One rule, defined once, because the API and the browser both need it and a
second copy in TypeScript would eventually disagree with this one -- the same
reason `needs_reorder` became a hybrid_property instead of being written out
three times.
"""

from typing import Any, Iterable


def matches(applies_to: dict[str, Any], attributes: dict[str, Any]) -> bool:
    """Is an image tagged `applies_to` shown for a variant with `attributes`?

    A SUBSET test, not equality. `{"color": "Black"}` matches a variant whose
    attributes are `{"size": "L", "color": "Black"}`, because a photograph of a
    black shirt is a photograph of every size of black shirt. Requiring equality
    would mean tagging each image with a full attribute set and duplicating it
    per size, which is the variant_id design this one exists to avoid.

    Every pair must match, not any: `{"color": "Black", "fit": "Slim"}` is a
    photo of a slim black shirt and must not appear on a regular black one.

    An empty tag matches everything -- `all()` over no items is True, which is
    the behaviour wanted rather than an accident worth guarding against.
    """
    return all(attributes.get(key) == value for key, value in applies_to.items())


def visible_for(images: Iterable[Any], attributes: dict[str, Any] | None) -> list[Any]:
    """The images to show, in their existing order.

    `attributes` is None when nothing is selected yet -- a multi-variant product
    the customer has not chosen from. Everything shows then, because filtering
    to a variant nobody picked would hide photographs for no reason.

    Images tagged FOR the selection lead; untagged ones follow. Without that the
    gallery filters correctly and still opens on the wrong picture: an untagged
    primary matches every variant and sorts first, so choosing White leaves a
    generic shot on screen and buries the white one further down. Filtering was
    never the goal -- showing the thing they picked is.

    A stable partition, so relative order inside each group is untouched.
    """
    if attributes is None:
        return list(images)
    shown = [img for img in images if matches(img.applies_to, attributes)]
    return [i for i in shown if i.applies_to] + [i for i in shown if not i.applies_to]


def allowed_keys(variants: Iterable[Any]) -> set[str]:
    """Every attribute key used by a product's variants.

    An `applies_to` key outside this set can never match anything, so tagging an
    image with one means it silently disappears -- no error, no empty state,
    just an image the vendor uploaded and can no longer find. The database
    cannot check this (the keys live in JSONB on another table), so the API
    does. Section 1.1 already splits the responsibility this way for variant
    attributes themselves.
    """
    keys: set[str] = set()
    for variant in variants:
        keys.update(variant.attributes or {})
    return keys
