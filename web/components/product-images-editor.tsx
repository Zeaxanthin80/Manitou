"use client";

import Image from "next/image";
import { useActionState } from "react";

import { addImageAction, imageAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AdminProduct } from "@/lib/api";

/**
 * Every option a product's variants actually offer, as "key=value" pairs.
 *
 * Derived from the variants rather than typed, for the same reason the image
 * URL became a picker: a free-text tag lets you write {"colour":"Black"} on a
 * product whose variants say "color", and the image then matches nothing and
 * silently never appears. The API rejects unknown keys; offering only real ones
 * means never hitting that rejection.
 */
function variantOptions(product: AdminProduct): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const v of product.variants) {
    for (const [k, val] of Object.entries(v.attributes ?? {})) {
      seen.set(`${k}=${val}`, `${k}: ${val}`);
    }
  }
  return [...seen].map(([value, label]) => ({ value, label })).sort((a, b) =>
    a.label.localeCompare(b.label),
  );
}

/**
 * Product images, chosen from the files in web/public/.
 *
 * `available` is read on the server by lib/public-images.ts and passed in --
 * this is a Client Component and cannot read a filesystem.
 *
 * It used to be a free-text URL box, which is how an external address reached
 * the database and made next/image throw at RENDER time on the home page, the
 * product page and this page at once. This screen being one of the casualties is
 * what made it bad: the only control that can remove a broken image lived on a
 * page the broken image had already taken down. A list of real files removes the
 * possibility rather than validating against it -- though the API-side validator
 * stays too, because a Server Action is a reachable POST endpoint and not
 * everything that calls it is this form.
 *
 * No upload yet: a container filesystem is ephemeral and the API is a separate
 * service, so anything written to local disk now would be thrown away. Phase 6
 * moves storage to S3 + CloudFront and turns this into a real file input --
 * `accept="image/*"` alone offers camera and photo library on a phone. What the
 * API receives, a url string, does not change.
 *
 * Exactly one image is primary, enforced by a partial unique index
 * (uq_product_images_one_primary) rather than by this component. Promoting a new
 * one demotes the old in the same transaction; removing the primary promotes the
 * oldest survivor. Both happen server-side, so a stale tab cannot leave a
 * product with no primary image.
 */
export function ProductImagesEditor({
  product,
  available,
}: {
  product: AdminProduct;
  available: string[];
}) {
  const [addState, addAction, adding] = useActionState(addImageAction, {});
  const [rowState, rowAction, busy] = useActionState(imageAction, {});
  const options = variantOptions(product);

  return (
    <section>
      <h2 className="font-body text-sm uppercase tracking-tight text-muted">
        Images
      </h2>

      {product.images.length === 0 ? (
        <p className="mt-4 font-body text-sm text-muted">
          No images yet. The storefront will show a placeholder.
        </p>
      ) : (
        <ul className="mt-4 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {product.images.map((img) => (
            <li
              key={img.id}
              className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4"
            >
              <div className="relative aspect-[4/5] overflow-hidden rounded-sm bg-background">
                <Image
                  src={img.url}
                  alt={img.alt_text}
                  fill
                  sizes="(max-width: 640px) 100vw, 33vw"
                  className="object-cover"
                />
              </div>

              <p className="font-body text-sm text-text">{img.alt_text}</p>

              {img.is_primary ? (
                <span className="inline-block w-fit rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
                  Primary
                </span>
              ) : (
                <form action={rowAction}>
                  <input type="hidden" name="image_id" value={img.id} />
                  <input type="hidden" name="product_id" value={product.id} />
                  <input type="hidden" name="slug" value={product.slug} />
                  <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                    Make primary
                  </Button>
                </form>
              )}

              {options.length > 0 && (
                <form action={rowAction} className="flex flex-col gap-1">
                  <input type="hidden" name="image_id" value={img.id} />
                  <input type="hidden" name="product_id" value={product.id} />
                  <input type="hidden" name="slug" value={product.slug} />
                  <input type="hidden" name="intent" value="applies" />
                  <label className="font-body text-xs uppercase tracking-tight text-muted">
                    Shows for
                  </label>
                  <select
                    name="applies_to"
                    defaultValue={
                      Object.entries(img.applies_to ?? {})
                        .map(([k, v]) => `${k}=${v}`)[0] ?? ""
                    }
                    className="w-full rounded-md border border-border bg-surface px-2 py-1 font-body text-sm text-text"
                  >
                    <option value="">Every option</option>
                    {options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                    Save
                  </Button>
                </form>
              )}

              <form action={rowAction}>
                <input type="hidden" name="image_id" value={img.id} />
                <input type="hidden" name="product_id" value={product.id} />
                <input type="hidden" name="slug" value={product.slug} />
                <input type="hidden" name="intent" value="delete" />
                <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                  Remove
                </Button>
              </form>
            </li>
          ))}
        </ul>
      )}

      {rowState.error && (
        <p role="alert" className="mt-3 font-body text-sm text-error">
          {rowState.error}
        </p>
      )}
      {rowState.ok && (
        <p role="status" className="mt-3 font-body text-sm text-text">
          {rowState.ok}
        </p>
      )}

      <details className="mt-6">
        <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-muted hover:text-text">
          Add an image
        </summary>
        <form action={addAction} className="mt-4 grid max-w-2xl gap-4">
          <input type="hidden" name="product_id" value={product.id} />
          <input type="hidden" name="slug" value={product.slug} />
          <fieldset className="flex flex-col gap-1">
            <legend className="font-body text-sm text-text">Image</legend>
            {available.length === 0 ? (
              <p className="mt-1 font-body text-sm text-muted">
                No images found in <code>web/public/</code>. Add a file there and
                reload this page.
              </p>
            ) : (
              <ul className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {available.map((url) => (
                  <li key={url}>
                    {/* The whole tile is the label, so the picture is the click
                        target rather than a radio dot beside it. */}
                    <label className="group flex cursor-pointer flex-col gap-1">
                      {/* Nothing preselected on purpose. Alphabetical order is
                          not a meaningful default, and this writes to the live
                          storefront -- `required` making the admin choose beats
                          a silent wrong pick. */}
                      <input
                        type="radio"
                        name="url"
                        value={url}
                        required
                        className="peer sr-only"
                      />
                      <span className="relative block aspect-[4/5] overflow-hidden rounded-sm border border-border bg-background peer-checked:border-accent peer-focus-visible:outline peer-focus-visible:outline-2">
                        <Image
                          src={url}
                          alt=""
                          fill
                          sizes="120px"
                          className="object-cover"
                        />
                      </span>
                      <span className="truncate font-body text-xs text-muted peer-checked:text-text">
                        {url}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <span className="mt-2 font-body text-xs text-muted">
              Only files in <code>web/public/</code>. There is no free-text field
              on purpose: a link to another site is accepted by the form and then
              fails when the page renders, which breaks the storefront for every
              visitor. Drop a file in that folder to add to this list. Phase 6
              replaces this with a real upload.
            </span>
          </fieldset>
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Alt text
            <Input
              name="alt_text"
              required
              placeholder="Black crew neck t-shirt laid flat"
            />
            <span className="font-body text-xs text-muted">
              Describe the image for someone who cannot see it. Required — it is
              part of the quality floor, not optional metadata.
            </span>
          </label>
          {options.length > 0 && (
            <label className="flex flex-col gap-1 font-body text-sm text-text">
              Shows for
              <select
                name="applies_to"
                defaultValue=""
                className="w-full max-w-xs rounded-md border border-border bg-surface px-3 py-2 font-body text-base text-text"
              >
                <option value="">Every option</option>
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <span className="font-body text-xs text-muted">
                Restrict this photo to one option, so choosing it on the
                storefront shows this picture. A list, not a text box: a typed
                option name that no variant uses would match nothing and the
                image would silently never appear.
              </span>
            </label>
          )}

          <label className="flex items-center gap-2 font-body text-sm text-text">
            <input type="checkbox" name="is_primary" className="accent-text" />
            Make this the primary image
          </label>

          {addState.error && (
            <p role="alert" className="font-body text-sm text-error">
              {addState.error}
            </p>
          )}
          {addState.ok && (
            <p role="status" className="font-body text-sm text-text">
              {addState.ok}
            </p>
          )}

          <div>
            <Button type="submit" variant="ghost" disabled={adding}>
              {adding ? "Adding..." : "Add image"}
            </Button>
          </div>
        </form>
      </details>
    </section>
  );
}
