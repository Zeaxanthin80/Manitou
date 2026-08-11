"use client";

import Image from "next/image";
import { useActionState } from "react";

import { addImageAction, imageAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AdminProduct } from "@/lib/api";

/**
 * Product images, referenced by URL.
 *
 * No file picker: Phase 6 moves storage to S3 + CloudFront and a container
 * filesystem is ephemeral, so anything uploaded to local disk now would be
 * thrown away. What changes in Phase 6 is where the URL comes from, not this
 * screen.
 *
 * Exactly one image is primary, enforced by a partial unique index
 * (uq_product_images_one_primary) rather than by this component. Promoting a new
 * one demotes the old in the same transaction; removing the primary promotes the
 * oldest survivor. Both happen server-side, so a stale tab cannot leave a
 * product with no primary image.
 */
export function ProductImagesEditor({ product }: { product: AdminProduct }) {
  const [addState, addAction, adding] = useActionState(addImageAction, {});
  const [rowState, rowAction, busy] = useActionState(imageAction, {});

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
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Image URL
            <Input name="url" required placeholder="/placeholder-product.png" />
          </label>
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
