"use client";

import Image from "next/image";
import { useRef, useState } from "react";

import { confirmUploadAction, requestUploadAction } from "@/app/actions/admin";

/**
 * Upload a photograph, and hand the resulting URL to the form around it.
 *
 * **Three steps, because the bytes never touch our servers.** Ask the API to
 * sign a PUT, send the file straight to S3, then tell the API it landed. The
 * middle step is the only one that moves the image, and it goes browser → S3
 * with nothing of ours in the path: no request-size ceiling in the API, in this
 * Next server, or in the load balancer.
 *
 * The signed URL is safe to hold in the browser. It authorises one PUT, to one
 * key, for fifteen minutes -- not access to the bucket.
 *
 * 'use client' is required: this reads a File, tracks progress across three
 * awaits, and decodes the image to measure it. None of that survives a Server
 * Component.
 */
export function ImageUploadField({
  name,
  onUploaded,
}: {
  name: string;
  /** Told when an upload completes, so the surrounding form can drop a media
   *  library selection the vendor has just superseded. Optional: this component
   *  works on its own, and the form is what knows the other paths exist. */
  onUploaded?: () => void;
}) {
  const [url, setUrl] = useState("");
  const [assetId, setAssetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    setUrl("");
    setAssetId("");
    setFilename(file.name);

    try {
      // The size is sent, not guessed, because a presigned PUT has no
      // equivalent of the POST policy's content-length-range: the API signs the
      // exact byte count, and S3 refuses anything that does not match it.
      const target = await requestUploadAction(file.name, file.type, file.size);
      if (target.error || !target.url || !target.key) {
        setError(target.error ?? "Could not start the upload.");
        return;
      }

      const put = await fetch(target.url, {
        method: "PUT",
        // Exactly the headers the signature covers. Content-Length is set by
        // the browser from the body and cannot be assigned here, which is fine
        // -- it will match, because the body is the file whose size we signed.
        headers: { "Content-Type": file.type },
        body: file,
      });
      if (!put.ok) {
        // A 403 here is almost always CORS or an expired signature rather than
        // a permissions problem, and saying so saves an hour in the IAM console.
        setError(
          `The upload was refused (${put.status}). If this persists the signed ` +
            `link may have expired — try again.`,
        );
        return;
      }

      const size = await measure(file);
      // file.name, not target.key: the key is a generated UUID, and deriving the
      // display name from it is what defect 26 was.
      const confirmed = await confirmUploadAction(
        target.key,
        file.name,
        size.width,
        size.height,
      );
      if (confirmed.error || !confirmed.url) {
        setError(confirmed.error ?? "The upload could not be confirmed.");
        return;
      }
      setUrl(confirmed.url);
      setAssetId(String(confirmed.assetId ?? ""));
      onUploaded?.();
    } catch {
      setError("The upload failed. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="font-body text-sm text-text">Upload a photo</legend>

      {/* The URL the surrounding form submits. Hidden rather than shown,
          because it is a machine detail -- the vendor's evidence that this
          worked is the thumbnail below. */}
      <input type="hidden" name={name} value={url} />
      {/* Sent beside the url so the API can record which uploaded object this
          image is. It refuses the pair if they disagree, so this is a claim it
          checks rather than one it trusts. */}
      <input type="hidden" name="uploaded_asset_id" value={assetId} />

      <input
        ref={inputRef}
        type="file"
        // accept="image/*" and deliberately NO capture attribute: capture forces
        // the camera and REMOVES the photo library, which is the opposite of
        // useful when the vendor already photographed the shirt yesterday.
        accept="image/jpeg,image/png,image/webp,image/avif"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
        }}
        // w-fit is load-bearing, not cosmetic. This fieldset is a flex column,
        // whose default align-items:stretch pulls the input to the form's full
        // max-w-2xl (42rem = 672px). The `file:` prefix styles only the button
        // PSEUDO-ELEMENT inside the input -- the remaining ~570px of stretched
        // input is still the input, so clicking apparently blank space opened
        // the file manager. Shrinking to the intrinsic width makes the visible
        // control and the click target the same thing.
        className="w-fit font-body text-sm text-text file:mr-3 file:rounded-md file:border file:border-border file:bg-transparent file:px-4 file:py-2 file:font-body file:text-sm file:text-text hover:file:bg-background disabled:opacity-50"
      />

      {busy && (
        <p role="status" className="font-body text-xs text-muted">
          Uploading {filename}…
        </p>
      )}

      {error && (
        <p role="alert" className="font-body text-xs text-error">
          {error}
        </p>
      )}

      {url && !busy && (
        <div className="flex items-center gap-3">
          <span className="relative block size-16 shrink-0 overflow-hidden rounded-sm border border-border bg-background">
            <Image src={url} alt="" fill sizes="64px" className="object-cover" />
          </span>
          <span className="font-body text-xs text-muted">
            {filename} uploaded. Add alt text below, then save.
          </span>
        </div>
      )}

      <span className="font-body text-xs text-muted">
        JPEG, PNG, WebP or AVIF, up to 15 MB. The file goes straight to storage —
        it never passes through this site.
      </span>
    </fieldset>
  );
}

/**
 * Width and height, or nulls.
 *
 * Read in the browser because it has already decoded the image; the alternative
 * is the API downloading every upload back out of S3 to measure it. These drive
 * layout hints in the media library and nothing else, so a browser that cannot
 * decode the file costs a pair of nulls rather than a failed upload -- which is
 * why this never throws.
 */
function measure(file: File): Promise<{ width: number | null; height: number | null }> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth || null, height: img.naturalHeight || null });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ width: null, height: null });
    };
    img.src = url;
  });
}
