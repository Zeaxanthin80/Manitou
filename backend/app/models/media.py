"""Uploaded media: what is in the bucket, and what references it.

**Why a table and not just S3.** The obvious thought is that the bucket already
knows what is in it, so `ListObjectsV2` could drive the media library. It cannot:
it paginates by continuation token rather than offset, so it will not drive
`components/pagination.tsx` the way `/admin/orders`, `/admin/users` and
`/admin/audit` already do; it sorts only by key; it cannot search; and it carries
no alt text, no dimensions and no answer to "which products use this".

A row indexed on `uploaded_at` gives all of that, and it is written by the
confirm step of the upload — the moment the object is known to exist.

**The row is created only after `head_object` succeeds.** The browser PUTs
straight to S3 and the API never sees it happen, so a row written on the
*presign* would record uploads that never completed. Size and content type come
from S3's own view of the object rather than from what the client claims.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

#: What may be uploaded. An allow-list rather than a block-list, and enforced in
#: the presigned URL's conditions rather than checked afterwards -- a check after
#: the fact still leaves the object in the bucket.
#:
#: No SVG. It is an image to a user and a script to a browser, and one served
#: from a host the site trusts is a stored-XSS vector. If a vendor ever needs
#: vector artwork, that is store.logo, which is committed rather than uploaded.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif")

#: 15 MB. Comfortably above a phone photograph and far below anything that would
#: make CloudFront's per-object limits or a vendor's patience an issue.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class MediaAsset(Base):
    """One object in the media bucket."""

    __tablename__ = "media_assets"
    __table_args__ = (
        # Newest first is the default anyone actually wants from a media
        # library, and it is the sort the library modal will page through.
        Index("ix_media_assets_uploaded_at", "uploaded_at"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'image/avif')",
            name="content_type_allowed",
        ),
        # Dimensions are either both known or both absent. A width with no height
        # is not a fact about an image, and half a pair would make any layout
        # calculation quietly wrong.
        CheckConstraint(
            "(width IS NULL) = (height IS NULL)", name="dimensions_paired"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    #: The S3 key, e.g. "media/2026/08/a1b2c3d4.jpg". Unique because the object
    #: is the thing this row describes -- two rows for one key would disagree the
    #: moment either was edited.
    #:
    #: The bucket name is NOT stored. It lives in configuration, so a clone
    #: pointing at its own bucket needs no data migration.
    key: Mapped[str] = mapped_column(Text, unique=True)

    #: What the vendor's file was called. Kept for the library's search, and
    #: deliberately not used to build the key: a filename is attacker-controlled
    #: and full of characters that mean something in a path.
    original_filename: Mapped[str] = mapped_column(Text)

    #: From S3's head_object, not from the upload form.
    content_type: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)

    #: Nullable because they come from the browser, which may not have decoded
    #: the image. Useful for the library's list view; nothing depends on them.
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    #: NO ACTION, like orders.user_id: an account is anonymised rather than
    #: deleted, so this never dangles. Nullable so an asset outlives a user row
    #: that was never there -- a seeded or imported asset has no uploader.
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    images: Mapped[list["ProductImage"]] = relationship(  # noqa: F821
        back_populates="asset"
    )
