"""The presigned upload flow.

Driven entirely by a stub S3 client. `uploads.py` takes the client as its first
argument precisely so this is possible: the whole flow -- signing, refusing,
confirming, moving -- is exercised with no AWS account, no network and no
credentials, which is what makes it a test rather than an integration check.

What a stub CANNOT prove is that S3 enforces the signed Content-Type and
Content-Length. That is a claim about SigV4, not about this code, and it is
verified against the real bucket in the task 9 walkthrough instead.
"""

import pytest

from app.models.media import ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES
from app.services.uploads import (
    MEDIA_PREFIX,
    PENDING_PREFIX,
    UploadError,
    confirm_upload,
    confirmed_key,
    new_pending_key,
    presign_put,
    public_url,
)

BUCKET = "test-bucket"


class StubS3:
    """Records what it was asked to sign, and pretends to hold objects."""

    def __init__(self, objects: dict | None = None):
        self.objects = objects or {}
        self.signed: list[dict] = []
        self.copied: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        self.signed.append({"op": op, "params": Params, "expires": ExpiresIn})
        return f"https://s3.example/{Params['Key']}?X-Amz-Signature=stub"

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise KeyError(Key)          # botocore raises ClientError; shape differs, handling must not
        return self.objects[Key]

    def copy_object(self, Bucket, Key, CopySource, **kw):  # noqa: N803
        self.copied.append((CopySource["Key"], Key))
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)


def _obj(content_type="image/jpeg", size=2048):
    return {"ContentType": content_type, "ContentLength": size}


# --- keys -------------------------------------------------------------------


def test_a_pending_key_carries_no_part_of_the_uploaded_filename():
    """A filename is attacker-controlled and `.jpg.html` is a filename.

    The human-readable name is kept on the row, where it can be searched without
    ever being part of a path.
    """
    key = new_pending_key("image/png")
    assert key.startswith(PENDING_PREFIX)
    assert key.endswith(".png")
    assert "photo" not in key


def test_two_uploads_of_the_same_filename_do_not_collide():
    assert new_pending_key("image/jpeg") != new_pending_key("image/jpeg")


def test_confirming_maps_pending_to_media_and_keeps_the_rest():
    assert confirmed_key(f"{PENDING_PREFIX}2026/08/abc.jpg") == f"{MEDIA_PREFIX}2026/08/abc.jpg"


def test_a_key_outside_pending_cannot_be_confirmed():
    with pytest.raises(UploadError, match="Not a pending key"):
        confirmed_key("media/someone-elses.jpg")


# --- presigning: what is refused, and the control ---------------------------


def test_presigning_signs_the_content_type_and_the_exact_size():
    """The control for every refusal below, and the heart of the design.

    A presigned PUT has no equivalent of the POST policy's content-length-range,
    so the size is pinned by signing it: SigV4 covers every header it lists, and
    S3 will not verify a request whose Content-Length differs. Assert both are in
    Params, because dropping either would silently make the limit advisory.
    """
    s3 = StubS3()
    key, url = presign_put(s3, BUCKET, "image/jpeg", 2048)

    assert key.startswith(PENDING_PREFIX)
    assert url.startswith("https://")
    params = s3.signed[0]["params"]
    assert params["ContentType"] == "image/jpeg"
    assert params["ContentLength"] == 2048
    assert params["Bucket"] == BUCKET
    assert s3.signed[0]["expires"] > 0


@pytest.mark.parametrize("content_type", ALLOWED_CONTENT_TYPES)
def test_every_allowed_image_type_can_be_signed(content_type):
    key, _ = presign_put(StubS3(), BUCKET, content_type, 1024)
    assert key.startswith(PENDING_PREFIX)


def test_svg_is_refused():
    """An image to a user, a script to a browser.

    One served from a host the site trusts -- which the CDN host is, by the
    widened AdminImageCreate validator -- is stored XSS. Vector artwork is
    store.logo, which is committed rather than uploaded.
    """
    with pytest.raises(UploadError, match="not an accepted image type"):
        presign_put(StubS3(), BUCKET, "image/svg+xml", 1024)


@pytest.mark.parametrize("content_type", ["text/html", "application/pdf", "image/gif"])
def test_other_types_are_refused(content_type):
    with pytest.raises(UploadError, match="not an accepted image type"):
        presign_put(StubS3(), BUCKET, content_type, 1024)


def test_a_file_over_the_limit_is_refused_before_anything_is_signed():
    """Refused here, not at confirm.

    Rejecting after the upload means paying for the transfer and still holding
    the object. Asserting `signed == []` is the part that matters: it proves no
    URL was handed out, rather than merely that an error was raised.
    """
    s3 = StubS3()
    with pytest.raises(UploadError, match="The limit is"):
        presign_put(s3, BUCKET, "image/jpeg", MAX_UPLOAD_BYTES + 1)
    assert s3.signed == []


def test_exactly_the_limit_is_allowed():
    """The boundary, from the other side -- an off-by-one here is invisible."""
    key, _ = presign_put(StubS3(), BUCKET, "image/jpeg", MAX_UPLOAD_BYTES)
    assert key


def test_an_empty_file_is_refused():
    with pytest.raises(UploadError, match="not an image"):
        presign_put(StubS3(), BUCKET, "image/jpeg", 0)


def test_no_bucket_configured_refuses_with_an_actionable_message():
    """Local development runs with no S3 at all, and must say so plainly."""
    with pytest.raises(UploadError, match="No media bucket is configured"):
        presign_put(StubS3(), "", "image/jpeg", 1024)


# --- confirming -------------------------------------------------------------


def test_confirm_moves_the_object_and_reports_s3s_view_of_it():
    key = f"{PENDING_PREFIX}2026/08/abc.jpg"
    s3 = StubS3({key: _obj(size=4096)})

    result = confirm_upload(s3, BUCKET, key)

    assert result == {
        "key": f"{MEDIA_PREFIX}2026/08/abc.jpg",
        "content_type": "image/jpeg",
        "byte_size": 4096,
    }
    assert s3.copied == [(key, f"{MEDIA_PREFIX}2026/08/abc.jpg")]
    assert s3.deleted == [key]


def test_confirming_a_key_that_was_never_uploaded_is_refused():
    """The refusal this endpoint exists for.

    The browser PUTs straight to S3 and the API never sees it happen, so without
    head_object a client could post any key and get a row for an object that does
    not exist.
    """
    s3 = StubS3()
    with pytest.raises(UploadError, match="was not found"):
        confirm_upload(s3, BUCKET, f"{PENDING_PREFIX}2026/08/never.jpg")
    assert s3.copied == []


def test_confirming_a_key_outside_pending_is_refused_without_touching_s3():
    """Otherwise a caller could name somebody else's live asset and claim it.

    `copied == []` is the assertion that matters -- an error raised after the
    copy would be far too late.
    """
    s3 = StubS3({f"{MEDIA_PREFIX}someone-elses.jpg": _obj()})
    with pytest.raises(UploadError, match="Not a pending upload key"):
        confirm_upload(s3, BUCKET, f"{MEDIA_PREFIX}someone-elses.jpg")
    assert s3.copied == []


def test_confirm_rechecks_the_type_against_s3_rather_than_the_presign():
    """Belt and braces, at the last point before a row exists.

    The signature makes a mismatch very hard; "hard" is not "cannot", and this
    is cheap.
    """
    key = f"{PENDING_PREFIX}2026/08/x.jpg"
    s3 = StubS3({key: _obj(content_type="text/html")})
    with pytest.raises(UploadError, match="not an accepted image type"):
        confirm_upload(s3, BUCKET, key)
    assert s3.copied == []


def test_a_failed_cleanup_does_not_fail_the_confirm():
    """The object is already safely in media/ by then.

    Failing here would refuse an upload that actually succeeded, and leave the
    caller with no row for an object that exists. The duplicate left in pending/
    is expired by the bucket's lifecycle rule within a day.
    """
    key = f"{PENDING_PREFIX}2026/08/x.jpg"

    class Grumpy(StubS3):
        def delete_object(self, Bucket, Key):  # noqa: N803
            raise RuntimeError("permission denied")

    result = confirm_upload(Grumpy({key: _obj()}), BUCKET, key)
    assert result["key"] == f"{MEDIA_PREFIX}2026/08/x.jpg"


# --- the public URL ---------------------------------------------------------


def test_the_public_url_is_built_from_config_and_never_stored():
    """So pointing a clone at its own distribution is config, not a migration."""
    assert public_url("d111.cloudfront.net", "media/2026/08/a.jpg") == (
        "https://d111.cloudfront.net/media/2026/08/a.jpg"
    )


def test_the_public_url_tolerates_a_trailing_slash_or_leading_slash():
    assert public_url("d111.cloudfront.net/", "/media/a.jpg") == (
        "https://d111.cloudfront.net/media/a.jpg"
    )


def test_no_cdn_host_configured_refuses():
    with pytest.raises(UploadError, match="No CDN host"):
        public_url("", "media/a.jpg")


def test_a_bad_type_is_reported_before_a_bad_size():
    """Pins the ORDER of two checks, which is otherwise untested behaviour.

    Found by mutation: removing the content-type check from presign_put changed
    nothing any test could see, because new_pending_key checks it too. The one
    thing the earlier check does is decide which error a request failing BOTH
    gets -- and "not an image type" is fixable while "too large" sends the vendor
    off to compress a file that will be refused anyway.
    """
    with pytest.raises(UploadError, match="not an accepted image type"):
        presign_put(StubS3(), BUCKET, "image/svg+xml", MAX_UPLOAD_BYTES * 2)


# ============================================================================
# The endpoints
# ============================================================================
#
# Through the real app with a stubbed S3 client, because the service tests above
# cannot see anything the ROUTES get wrong: the admin gate, the status codes, or
# whether a row is actually written.
#
# A note on how these were nearly missed. Checking `app.routes` for the new paths
# reported them absent three times running -- this FastAPI version keeps included
# routers as `_IncludedRouter` objects rather than flattening them, so walking
# app.routes finds nothing no matter how correct the code is. The OpenAPI schema
# and an actual request are the instruments that reflect reality.


@pytest.fixture
def stub_s3(monkeypatch):
    """Replace the client the routes build, for the duration of one test."""
    s3 = StubS3()
    monkeypatch.setattr("app.routers.admin._s3", lambda: s3)
    return s3


@pytest.fixture
def media_configured(monkeypatch, stub_s3):
    from app.config import settings

    monkeypatch.setattr(settings, "s3_bucket", BUCKET)
    monkeypatch.setattr(settings, "cdn_host", "d111abcdef8.cloudfront.net")
    return stub_s3


def test_presign_requires_an_admin(client, db, make_user, auth_headers):
    """A signed URL carries this service's own S3 authority.

    So the gate on this endpoint is not a formality: handing one to an
    unauthenticated caller would hand them PutObject on the bucket.
    """
    customer = make_user(email="c@manitou.example", role="customer")
    r = client.post(
        "/admin/uploads",
        headers=auth_headers(customer),
        json={"filename": "a.jpg", "content_type": "image/jpeg", "byte_size": 100},
    )
    assert r.status_code == 403

    assert client.post(
        "/admin/uploads",
        json={"filename": "a.jpg", "content_type": "image/jpeg", "byte_size": 100},
    ).status_code == 401


def test_presign_returns_a_url_and_the_headers_the_signature_covers(
    client, db, make_user, auth_headers, media_configured
):
    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.post(
        "/admin/uploads",
        headers=auth_headers(admin),
        json={"filename": "shirt.jpg", "content_type": "image/jpeg", "byte_size": 2048},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["key"].startswith(PENDING_PREFIX)
    assert body["url"].startswith("https://")
    # Returned because the signature covers them: a browser that omits either
    # gets a signature failure, which reads like a permissions problem.
    assert body["headers"]["Content-Type"] == "image/jpeg"
    assert body["headers"]["Content-Length"] == "2048"
    assert body["expires_in"] > 0


def test_presign_refuses_an_oversized_file_with_409_not_500(
    client, db, make_user, auth_headers, media_configured
):
    """409 and a readable message. A 500 would tell the vendor nothing."""
    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.post(
        "/admin/uploads",
        headers=auth_headers(admin),
        json={"filename": "huge.jpg", "content_type": "image/jpeg",
              "byte_size": MAX_UPLOAD_BYTES + 1},
    )
    assert r.status_code == 409
    assert "limit" in r.json()["detail"].lower()


def test_presign_says_so_when_no_bucket_is_configured(
    client, db, make_user, auth_headers, stub_s3, monkeypatch
):
    """Local development, and it must name the variables to set."""
    from app.config import settings

    monkeypatch.setattr(settings, "s3_bucket", "")
    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.post(
        "/admin/uploads",
        headers=auth_headers(admin),
        json={"filename": "a.jpg", "content_type": "image/jpeg", "byte_size": 100},
    )
    assert r.status_code == 409
    assert "S3_BUCKET" in r.json()["detail"]


def test_confirm_writes_a_row_describing_s3s_view_of_the_object(
    client, db, make_user, auth_headers, media_configured
):
    from app.models import MediaAsset

    admin = make_user(email="admin@manitou.example", role="admin")
    # A UUID-shaped key, like the ones new_pending_key actually produces, and a
    # filename that appears NOWHERE in it. The earlier version of this test used
    # "abc.jpg" as the key's basename, which made a key-derived filename and the
    # vendor's filename the same string -- so the assertion below could not tell
    # them apart and passed against the implementation of defect 26.
    key = f"{PENDING_PREFIX}2026/08/70eabec67c3c4d70b76dcf8a1b2c3d4e.jpg"
    media_configured.objects[key] = _obj(size=4096)

    r = client.post(
        "/admin/uploads/confirm",
        headers=auth_headers(admin),
        json={
            "key": key,
            "original_filename": "Navy Crew Neck.jpg",
            "width": 800,
            "height": 600,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["key"] == f"{MEDIA_PREFIX}2026/08/70eabec67c3c4d70b76dcf8a1b2c3d4e.jpg"
    assert body["byte_size"] == 4096
    assert body["url"] == f"https://d111abcdef8.cloudfront.net/{body['key']}"
    assert body["width"] == 800

    row = db.query(MediaAsset).one()
    assert row.key == body["key"]
    assert row.uploaded_by == admin.id
    # Kept for the media library's search, and never part of the key. The value
    # asserted here CANNOT have come from the key -- that is the whole point.
    assert row.original_filename == "Navy Crew Neck.jpg"
    assert row.original_filename not in row.key


def test_confirming_a_key_that_was_never_uploaded_writes_no_row(
    client, db, make_user, auth_headers, media_configured
):
    """The endpoint's reason for existing, and the assertion that matters is
    the absence of a row -- a 409 with a row written would be worse than either."""
    from app.models import MediaAsset

    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.post(
        "/admin/uploads/confirm",
        headers=auth_headers(admin),
        json={"key": f"{PENDING_PREFIX}2026/08/never.jpg", "original_filename": "never.jpg"},
    )
    assert r.status_code == 409
    assert db.query(MediaAsset).count() == 0


def test_confirming_a_key_outside_pending_writes_no_row(
    client, db, make_user, auth_headers, media_configured
):
    from app.models import MediaAsset

    admin = make_user(email="admin@manitou.example", role="admin")
    media_configured.objects[f"{MEDIA_PREFIX}someone-elses.jpg"] = _obj()

    r = client.post(
        "/admin/uploads/confirm",
        headers=auth_headers(admin),
        json={"key": f"{MEDIA_PREFIX}someone-elses.jpg", "original_filename": "mine.jpg"},
    )
    assert r.status_code == 409
    assert db.query(MediaAsset).count() == 0


# ============================================================================
# The asset linkage (defect 24)
# ============================================================================
#
# Task 9 added product_images.asset_id and never wrote to it. The column and the
# FK existed; the write path ignored them. So "which products use this asset?"
# -- the question media_assets exists to answer -- returned nothing, and the
# NO ACTION guard protected nothing, because nothing referenced anything.
#
# Populating it carelessly would be worse than leaving it null. An id that does
# not match the url is a confident WRONG answer rather than no answer, and a
# delete guard reading it would refuse the wrong assets and permit the rest.
# Hence the match check, and hence these tests.

CDN = "d111abcdef8.cloudfront.net"


@pytest.fixture
def linked(monkeypatch, db):
    """One asset in the database, with the CDN host configured."""
    from app.config import settings
    from app.models import MediaAsset

    monkeypatch.setattr(settings, "cdn_host", CDN)
    asset = MediaAsset(
        key="media/2026/08/abc.jpg",
        original_filename="shirt.jpg",
        content_type="image/jpeg",
        byte_size=2048,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def test_an_uploaded_image_records_the_asset_it_came_from(
    client, db, make_user, make_product, auth_headers, linked
):
    """The control, and the defect closed.

    Before this, asset_id was NULL on every row and the join below returned
    nothing no matter how many photographs had been uploaded.
    """
    from app.models import ProductImage

    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={
            "url": f"https://{CDN}/{linked.key}",
            "asset_id": linked.id,
            "alt_text": "A shirt",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["images"][0]["asset_id"] == linked.id

    row = db.query(ProductImage).one()
    assert row.asset_id == linked.id
    # The question the table was built to answer, asked for real.
    assert len(linked.images) == 1


def test_a_url_that_does_not_belong_to_the_named_asset_is_refused(
    client, db, make_user, make_product, auth_headers, linked
):
    """The refusal that makes the link mean something.

    Without it any URL could be filed under any asset id, and every later answer
    about usage would be fiction -- including the one a delete guard reads.
    """
    from app.models import ProductImage

    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={
            "url": f"https://{CDN}/media/2026/08/somebody-elses.jpg",
            "asset_id": linked.id,
            "alt_text": "A shirt",
        },
    )
    assert r.status_code == 409
    assert "does not belong" in r.json()["detail"]
    # No row, not merely no link -- a half-written image would be worse.
    assert db.query(ProductImage).count() == 0


def test_an_asset_id_that_does_not_exist_is_a_404_not_a_500(
    client, db, make_user, make_product, auth_headers, linked
):
    """A different fault from a mismatch, and worth a different status."""
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={
            "url": f"https://{CDN}/{linked.key}",
            "asset_id": linked.id + 999,
            "alt_text": "A shirt",
        },
    )
    assert r.status_code == 404


def test_a_committed_file_still_needs_no_asset(
    client, db, make_user, make_product, auth_headers
):
    """The seeded web/public/ images have no S3 object behind them.

    Their asset_id stays NULL, and that is correct rather than a gap -- it is the
    reason product_images.url survives alongside the FK. A version of this
    feature that required an asset would break local development entirely.
    """
    from app.models import ProductImage

    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={"url": "/product-placeholder.png", "alt_text": "A shirt"},
    )
    assert r.status_code == 201
    assert db.query(ProductImage).one().asset_id is None


# ============================================================================
# The stored filename (defect 26)
# ============================================================================


@pytest.mark.parametrize(
    "sent, stored",
    [
        ("shirt.jpg", "shirt.jpg"),
        # A browser may send a path. Only the last segment names the file, and
        # keeping the rest would make the library's search match folder names.
        ("photos/summer/shirt.jpg", "shirt.jpg"),
        (r"C:\Users\jo\shirt.jpg", "shirt.jpg"),
        # Non-printables render as nothing, so two visibly identical names could
        # differ -- and they are how log output gets forged.
        ("shi\x00rt\x1b[31m.jpg", "shirt[31m.jpg"),
        ("   spaced.jpg   ", "spaced.jpg"),
        # Never empty: an odd name is not a reason to fail an upload S3 already
        # accepted.
        ("///", "untitled"),
        ("\x00\x00", "untitled"),
    ],
)
def test_a_filename_is_cleaned_for_storage(sent, stored):
    from app.services.uploads import clean_filename

    assert clean_filename(sent) == stored


def test_a_very_long_filename_is_capped_rather_than_rejected():
    from app.services.uploads import clean_filename

    out = clean_filename("a" * 400 + ".jpg")
    assert len(out) == 255


def test_the_stored_filename_is_sanitised_end_to_end(
    client, db, make_user, auth_headers, media_configured
):
    """A path sent by the browser must not reach the column.

    The control is the test above that a plain name survives untouched -- without
    it this would also pass if the endpoint stored a constant.
    """
    from app.models import MediaAsset

    admin = make_user(email="admin@manitou.example", role="admin")
    key = f"{PENDING_PREFIX}2026/08/aaaabbbbccccddddeeeeffff00001111.jpg"
    media_configured.objects[key] = _obj(size=4096)

    r = client.post(
        "/admin/uploads/confirm",
        headers=auth_headers(admin),
        json={"key": key, "original_filename": "some/deep/path/shirt.jpg"},
    )

    assert r.status_code == 201, r.text
    assert db.query(MediaAsset).one().original_filename == "shirt.jpg"


def test_confirm_refuses_an_upload_with_no_filename(
    client, db, make_user, auth_headers, media_configured
):
    """Paired with the permit case above, or it proves nothing.

    Required rather than defaulted: the browser always holds the File, so a
    missing name means a caller that is not our upload field, and silently
    storing "untitled" would put a row in the library nobody can find.
    """
    from app.models import MediaAsset

    admin = make_user(email="admin@manitou.example", role="admin")
    key = f"{PENDING_PREFIX}2026/08/aaaabbbbccccddddeeeeffff00002222.jpg"
    media_configured.objects[key] = _obj(size=4096)

    r = client.post(
        "/admin/uploads/confirm", headers=auth_headers(admin), json={"key": key}
    )

    assert r.status_code == 422
    assert db.query(MediaAsset).count() == 0


# ============================================================================
# The media library listing
# ============================================================================


@pytest.fixture
def library(monkeypatch, db, make_product):
    """Three assets, one of them attached to a product with alt text."""
    from app.config import settings
    from app.models import MediaAsset, ProductImage
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(settings, "cdn_host", CDN)
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    assets = []
    for i, (name, size) in enumerate(
        [("zebra.jpg", 3000), ("apple.png", 1000), ("mango.webp", 2000)]
    ):
        a = MediaAsset(
            key=f"media/2026/08/{i}.jpg",
            original_filename=name,
            content_type="image/jpeg",
            byte_size=size,
            uploaded_at=base + timedelta(days=i),
        )
        db.add(a)
        assets.append(a)
    db.commit()
    for a in assets:
        db.refresh(a)

    product = make_product()
    db.add(
        ProductImage(
            product_id=product.id,
            url=f"https://{CDN}/{assets[0].key}",
            asset_id=assets[0].id,
            alt_text="A navy crew neck shirt",
            is_primary=True,
        )
    )
    db.commit()
    return assets


def _get(client, headers, **params):
    r = client.get("/admin/assets", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_library_requires_an_admin(client, db, make_user, auth_headers):
    customer = make_user(email="c@manitou.example", role="customer")
    assert client.get("/admin/assets", headers=auth_headers(customer)).status_code == 403
    assert client.get("/admin/assets").status_code == 401


def test_it_lists_every_asset_newest_first_by_default(
    client, db, make_user, auth_headers, library
):
    admin = make_user(email="admin@manitou.example", role="admin")
    body = _get(client, auth_headers(admin))

    assert body["total"] == 3
    # mango was uploaded last in the fixture.
    assert body["items"][0]["original_filename"] == "mango.webp"
    assert body["items"][0]["url"].startswith(f"https://{CDN}/")


def test_used_by_count_answers_the_question_the_table_exists_for(
    client, db, make_user, auth_headers, library
):
    """Zero for an unused asset, one for the attached one.

    Before defect 24 was fixed this was always 0, because nothing populated
    product_images.asset_id -- so the number looked right and meant nothing.
    """
    admin = make_user(email="admin@manitou.example", role="admin")
    rows = {r["original_filename"]: r["used_by_count"] for r in _get(client, auth_headers(admin))["items"]}

    assert rows["zebra.jpg"] == 1
    assert rows["apple.png"] == 0
    assert rows["mango.webp"] == 0


def test_search_matches_the_filename(client, db, make_user, auth_headers, library):
    admin = make_user(email="admin@manitou.example", role="admin")
    body = _get(client, auth_headers(admin), q="appl")
    assert [r["original_filename"] for r in body["items"]] == ["apple.png"]
    assert body["total"] == 1


def test_search_also_matches_the_alt_text_of_an_image_using_the_asset(
    client, db, make_user, auth_headers, library
):
    """The EXISTS half, which is easy to write and never exercise.

    Alt text is not a column on media_assets -- it lives on product_images, and
    an asset used by three products has three of them. "navy" appears in no
    filename, so a match here can only have come through the subquery.
    """
    admin = make_user(email="admin@manitou.example", role="admin")
    body = _get(client, auth_headers(admin), q="navy")
    assert [r["original_filename"] for r in body["items"]] == ["zebra.jpg"]


def test_search_matching_nothing_returns_an_empty_page_not_everything(
    client, db, make_user, auth_headers, library
):
    """The control for the two above: a filter that does nothing would pass them."""
    body = _get(client, auth_headers(make_user(email="a@manitou.example", role="admin")),
                q="nothing-matches-this")
    assert body["items"] == [] and body["total"] == 0


@pytest.mark.parametrize(
    "sort,first",
    [
        ("newest", "mango.webp"),
        ("oldest", "zebra.jpg"),
        ("name", "apple.png"),
        ("size", "zebra.jpg"),   # 3000 bytes, largest first
    ],
)
def test_each_sort_actually_changes_the_order(
    client, db, make_user, auth_headers, library, sort, first
):
    """Asserted on the FIRST ROW, not on the request succeeding.

    A sort parameter that was silently ignored would return 200 for all four and
    pass any test that only checked the status.
    """
    admin = make_user(email="admin@manitou.example", role="admin")
    body = _get(client, auth_headers(admin), sort=sort)
    assert body["items"][0]["original_filename"] == first


def test_an_unknown_sort_is_refused_rather_than_silently_defaulted(
    client, db, make_user, auth_headers, library
):
    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.get("/admin/assets", headers=auth_headers(admin), params={"sort": "cheapest"})
    assert r.status_code == 422


def test_paging_carries_the_search_and_does_not_repeat_rows(
    client, db, make_user, auth_headers, library
):
    admin = make_user(email="admin@manitou.example", role="admin")
    h = auth_headers(admin)
    page1 = _get(client, h, limit=2, offset=0)
    page2 = _get(client, h, limit=2, offset=2)

    assert len(page1["items"]) == 2 and len(page2["items"]) == 1
    assert page1["total"] == page2["total"] == 3
    ids = [r["id"] for r in page1["items"]] + [r["id"] for r in page2["items"]]
    assert len(set(ids)) == 3, "a row appeared on two pages"


def test_no_cdn_host_makes_the_library_refuse_rather_than_list_undisplayable_rows(
    client, db, make_user, auth_headers, library, monkeypatch
):
    """A machine with assets in its database but no CDN configured.

    Reachable in real life: development pointed at the deployed database. Every
    row's url is built from the CDN host, so without one the choice is to refuse
    or to return rows the caller cannot display. It refuses, and names the
    setting -- the alternative looks like "the images are broken" rather than
    "this machine is not configured".

    The control is every other test in this section: they pass because the
    fixture sets cdn_host, so this asserts the guard and not merely that the
    endpoint can fail.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "cdn_host", "")
    admin = make_user(email="admin@manitou.example", role="admin")

    r = client.get("/admin/assets", headers=auth_headers(admin))

    assert r.status_code == 503, r.text
    assert "CDN_HOST" in r.json()["detail"]
