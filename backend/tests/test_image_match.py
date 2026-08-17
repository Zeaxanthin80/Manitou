"""Which images show for which variant.

The rule is duplicated in TypeScript (web/lib/image-match.ts) because the
customer changes variant without a request, so the browser must decide from data
already on the page. These tests pin the Python side; keeping both tiny is what
makes them readable against each other.
"""

import pytest

from app.services.image_match import allowed_keys, matches, visible_for

BLACK_L = {"size": "L", "color": "Black"}
WHITE_L = {"size": "L", "color": "White"}


@pytest.mark.parametrize("tag,attrs,expected,why", [
    ({}, BLACK_L, True, "untagged shows for every variant"),
    ({}, {}, True, "untagged shows even with no attributes"),
    ({"color": "Black"}, BLACK_L, True, "SUBSET match -- a photo of a black shirt"),
    ({"color": "Black"}, WHITE_L, False, "wrong colour"),
    ({"size": "L", "color": "Black"}, BLACK_L, True, "full match"),
    # EVERY pair must match, not any. A photo of a slim black shirt must not
    # appear on a regular-fit black one.
    ({"color": "Black", "fit": "Slim"}, BLACK_L, False, "second key does not match"),
    ({"colour": "Black"}, BLACK_L, False, "misspelled key can never match"),
    ({"color": "Black"}, {}, False, "variant carries no attributes to match"),
])
def test_matches(tag, attrs, expected, why):
    assert matches(tag, attrs) is expected, why


class _Img:
    def __init__(self, url, applies_to):
        self.url, self.applies_to = url, applies_to
    def __repr__(self):
        return self.url


GALLERY = [
    _Img("primary", {}),
    _Img("wings", {"color": "Black"}),
    _Img("celestial", {"color": "White"}),
    _Img("terrain", {}),
]


def test_nothing_selected_shows_everything():
    """Filtering to a variant nobody picked would hide photographs for no
    reason."""
    assert [i.url for i in visible_for(GALLERY, None)] == [
        "primary", "wings", "celestial", "terrain"]


def test_tagged_images_lead_so_the_gallery_opens_on_the_right_one():
    """The bug this ordering fixes: filtering alone left an untagged primary
    first, so choosing White still showed a generic shot and buried the white
    one down the strip. Filtering was never the goal."""
    assert [i.url for i in visible_for(GALLERY, WHITE_L)] == [
        "celestial", "primary", "terrain"]
    assert [i.url for i in visible_for(GALLERY, BLACK_L)] == [
        "wings", "primary", "terrain"]


def test_variant_with_no_specific_image_still_gets_the_generic_ones():
    assert [i.url for i in visible_for(GALLERY, {"size": "L", "color": "Navy"})] == [
        "primary", "terrain"]


class _Variant:
    def __init__(self, attributes):
        self.attributes = attributes


def test_allowed_keys_unions_every_variant():
    assert allowed_keys([_Variant(BLACK_L), _Variant({"fit": "Slim"}), _Variant({})]) == {
        "size", "color", "fit"}


def test_allowed_keys_of_a_product_with_no_attributes_is_empty():
    assert allowed_keys([_Variant({}), _Variant(None)]) == set()
