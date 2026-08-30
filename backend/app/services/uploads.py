"""Presigned uploads to the media bucket.

Framework-free like checkout.py, payments.py, stock.py and fulfilment.py: no
FastAPI import, so a router, a script and a test can all ask the same question
the same way. Every function takes the S3 client as its first argument, which is
what lets the tests drive the whole flow with a stub and no AWS account.

**The API never handles the bytes.** The browser asks for a URL, PUTs the file
straight to S3, and posts the key back. No request-size ceiling, no memory spike,
and a Fargate task sized for the application rather than for the largest
photograph anyone might upload.

**A presigned URL carries the SIGNER's authority.** Whoever holds it can do what
this service's IAM role can do, to that key, until it expires. That is why the
role grants PutObject on two prefixes and nothing else, and why the conditions
below are baked into the signature rather than checked afterwards -- a check
after the fact still leaves the object in the bucket.

**Two prefixes, and the reason is the lifecycle rule.** An upload is signed into
`pending/`; confirming it copies to `media/` and removes the source. So anything
still in `pending/` is by definition an upload nobody completed, and the bucket's
lifecycle rule can expire it after a day without ever touching a live asset.
Uploading straight to `media/` would make abandoned and live objects
indistinguishable, and the bucket would fill with things nothing references.
"""

import uuid
from datetime import datetime, timezone

from app.models.media import ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES

#: How long a signed URL is good for. Long enough for a large photograph on a
#: slow connection, short enough that one copied out of a browser's network tab
#: is not a standing grant.
PRESIGN_EXPIRY_SECONDS = 15 * 60

PENDING_PREFIX = "pending/"
MEDIA_PREFIX = "media/"

#: Extension per content type, so the stored key ends in something a CDN and a
#: browser both recognise. Derived from the content type rather than from the
#: uploaded filename: a filename is attacker-controlled, and `.jpg.html` is a
#: filename.
_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}


class UploadError(Exception):
    """Refused before anything was signed or stored."""


def new_pending_key(content_type: str) -> str:
    """A fresh key under pending/, dated for browsability.

    The original filename is deliberately absent. Two vendors uploading
    `photo.jpg` must not collide, a filename can contain path separators and
    percent-encoding, and the human-readable name is kept on the row instead --
    where it can be searched without ever being part of a path.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(f"{content_type} is not an accepted image type.")
    now = datetime.now(timezone.utc)
    return (
        f"{PENDING_PREFIX}{now:%Y/%m}/{uuid.uuid4().hex}"
        f".{_EXTENSIONS[content_type]}"
    )


def confirmed_key(pending_key: str) -> str:
    """Where a pending key lives once confirmed."""
    if not pending_key.startswith(PENDING_PREFIX):
        raise UploadError("Not a pending key.")
    return MEDIA_PREFIX + pending_key[len(PENDING_PREFIX) :]


def presign_put(
    client, bucket: str, content_type: str, byte_size: int
) -> tuple[str, str]:
    """Sign a single PUT. Returns (key, url).

    **Both the content type and the exact byte count are signed**, which is what
    makes them enforceable rather than advisory. SigV4 covers every header it
    lists, so S3 rejects a request whose Content-Type or Content-Length differs
    from what was signed -- the signature simply will not verify.

    That matters because a presigned PUT has no equivalent of the POST policy's
    `content-length-range`. Signing the exact size instead means the client
    declares what it is about to send, this function decides whether that is
    allowed, and S3 enforces the answer. A client that lies about the size gets a
    signature failure; one that tells the truth about too large a file is
    refused here, before any bytes move.

    Refusing at presign time is the point: rejecting after the upload would mean
    paying for the transfer and then still holding the object.
    """
    if not bucket:
        raise UploadError(
            "No media bucket is configured, so uploads are unavailable. "
            "Set S3_BUCKET (and CDN_HOST) to enable them."
        )
    # Checked BEFORE the size, and that ordering is the only thing this line
    # does that new_pending_key below does not: a 20 MB SVG should be told it is
    # not an image type, which is fixable, rather than that it is too large,
    # which would send the vendor off to compress a file we will refuse anyway.
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(f"{content_type} is not an accepted image type.")
    if byte_size <= 0:
        raise UploadError("An empty file is not an image.")
    if byte_size > MAX_UPLOAD_BYTES:
        raise UploadError(
            f"That file is {byte_size / 1_048_576:.1f} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB."
        )

    key = new_pending_key(content_type)
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": byte_size,
        },
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )
    return key, url


def confirm_upload(client, bucket: str, pending_key: str) -> dict:
    """Verify the object arrived, move it to media/, and describe it.

    Returns {"key", "content_type", "byte_size"} -- **S3's view of the object,
    not the client's claims about it.** The browser PUTs directly and the API
    never sees it happen, so without this the row would record an upload that may
    never have completed. head_object is what turns "the client says it uploaded"
    into "the object exists and is this big".

    Refuses a key outside pending/. Without that check a caller could name any
    key in the bucket -- including one belonging to somebody else's asset -- and
    have it copied into media/ under a row they own.
    """
    if not bucket:
        raise UploadError("No media bucket is configured.")
    if not pending_key.startswith(PENDING_PREFIX):
        raise UploadError("Not a pending upload key.")

    try:
        head = client.head_object(Bucket=bucket, Key=pending_key)
    except Exception as exc:  # botocore raises ClientError; stubs raise their own
        raise UploadError(
            "That upload was not found. It may have expired, or the PUT may "
            "never have completed."
        ) from exc

    content_type = head.get("ContentType", "")
    byte_size = int(head.get("ContentLength", 0))

    # Re-checked against S3's own answer rather than trusting the presign. The
    # signature makes a mismatch very hard, but "hard" is not "cannot", and this
    # is the last point before a row exists.
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(f"{content_type} is not an accepted image type.")
    if byte_size <= 0 or byte_size > MAX_UPLOAD_BYTES:
        raise UploadError("That upload is not a valid size.")

    final_key = confirmed_key(pending_key)
    client.copy_object(
        Bucket=bucket,
        Key=final_key,
        CopySource={"Bucket": bucket, "Key": pending_key},
        ContentType=content_type,
        MetadataDirective="REPLACE",
    )
    # Best effort. A failure here leaves a duplicate in pending/, which the
    # lifecycle rule expires in a day -- strictly better than failing a confirm
    # whose object is already safely in media/.
    try:
        client.delete_object(Bucket=bucket, Key=pending_key)
    except Exception:
        pass

    return {"key": final_key, "content_type": content_type, "byte_size": byte_size}


def clean_filename(name: str) -> str:
    """A vendor's filename, made safe to STORE and DISPLAY.

    Never used to build a key -- that is what `new_pending_key` is for, and the
    separation is the whole reason a filename can be kept at all. This only has
    to survive being written to a column and rendered in a list.

    Three things are removed, each for its own reason:

    * **Directories.** A browser may send `C:\\Users\\jo\\shirt.jpg` or
      `photos/shirt.jpg`. Only the last segment is the name of the file, and
      keeping the rest would make the library's search match on folder names.
    * **Non-printable characters.** They render as nothing, so two visibly
      identical names could differ, and they are how log output gets forged.
    * **Length.** Capped at 255, the same bound the presign request declares.

    Falls back to "untitled" rather than raising: an odd filename is not a
    reason to reject an upload that has already succeeded in S3.
    """
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return (name or "untitled")[:255]


def public_url(cdn_host: str, key: str) -> str:
    """Where the storefront fetches this object.

    Built from configuration plus the key, never stored -- so pointing a clone at
    its own distribution is a config change rather than a data migration. The
    bucket is private; this host is the only way in.
    """
    if not cdn_host:
        raise UploadError("No CDN host is configured.")
    return f"https://{cdn_host.rstrip('/')}/{key.lstrip('/')}"
