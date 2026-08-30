"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { listAssetsAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import type { MediaAsset, MediaAssetPage } from "@/lib/api";

/** Twelve fits three rows of four without scrolling on a laptop, and keeps the
 *  response small enough that paging feels instant. */
const PAGE_SIZE = 12;

const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "name", label: "Filename A–Z" },
  { value: "size", label: "Largest first" },
] as const;

/**
 * Browse what has been uploaded, and reuse one on another product.
 *
 * **Why this is not `components/pagination.tsx`.** That component renders
 * `<Link href="?page=2">`, deliberately, so a page of orders can be bookmarked
 * and shared. Inside a dialog the same behaviour is wrong: following a link
 * navigates, which unmounts the dialog and throws away the vendor's search, sort
 * and half-filled form behind it. So this keeps its own page state and fetches
 * through a Server Action instead.
 *
 * **It has to be a Server Action rather than a browser fetch**, because the
 * admin JWT lives in an httpOnly cookie — the browser can send it to this Next
 * server but cannot read it to put in an Authorization header for FastAPI. Every
 * other admin call in this app goes the same way.
 *
 * The dialog itself is `ui/modal.tsx`, which is the native `<dialog>`: focus
 * trap, Escape to close, background inert, focus returned on close. None of that
 * is re-implemented here.
 */
export function MediaLibraryModal({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (asset: MediaAsset) => void;
}) {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [sort, setSort] = useState<string>("newest");
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<"grid" | "list">("grid");

  const [page, setPage] = useState<MediaAssetPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);

  // What is being asked for, versus what has come back. Loading is DERIVED from
  // the two rather than being a flag of its own, so it cannot disagree with what
  // is on screen -- a flag has to be cleared on every exit path, and the one
  // that gets missed is always an error path that leaves a spinner forever.
  const asked = `${debouncedQ}|${sort}|${offset}`;
  const loading = open && loaded !== asked;

  // A request only gets to write state if it is still the newest one. Typing
  // "black" fires several searches whose responses can arrive out of order, and
  // without this the slowest reply wins -- so the grid would show results for a
  // prefix of what the box says. Cheaper and more reliable than aborting.
  const seq = useRef(0);

  // Search waits for a pause in typing; sort and paging do not. A blanket delay
  // on every input would make clicking "Next" feel broken.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => {
    if (!open) return;
    const mine = ++seq.current;
    void listAssetsAction({
      q: debouncedQ,
      sort,
      limit: PAGE_SIZE,
      offset,
    }).then((result) => {
      if (mine !== seq.current) return;
      setError(result.error ?? null);
      setPage(result.page ?? null);
      setLoaded(asked);
    });
  }, [open, debouncedQ, sort, offset, asked]);

  const items = page?.items ?? [];
  const total = page?.total ?? 0;
  const showing = total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`;

  return (
    <Modal open={open} onClose={onClose} title="Media library" className="max-w-3xl">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-1 flex-col gap-1 font-body text-sm text-text">
            Search
            <Input
              value={q}
              // Any change to what is being asked resets to the first page.
              // Staying on page 3 of a different question shows an empty grid
              // and looks like "there are no results".
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
              placeholder="Filename or alt text"
            />
          </label>

          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Sort
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value);
                setOffset(0);
              }}
              className="rounded-md border border-border bg-surface px-3 py-2 font-body text-base text-text"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          {/* A list is faster to scan than a grid when the pictures all look
              alike, which is exactly the case for twelve photographs of black
              t-shirts -- there the filename and the size are the distinguishing
              features, not the thumbnail. */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setView(view === "grid" ? "list" : "grid")}
          >
            {view === "grid" ? "List view" : "Grid view"}
          </Button>
        </div>

        {error && (
          <p role="alert" className="font-body text-sm text-error">
            {error}
          </p>
        )}

        {!error && items.length === 0 && !loading && (
          <p className="py-8 text-center font-body text-sm text-muted">
            {debouncedQ
              ? `Nothing matches “${debouncedQ}”.`
              : "Nothing has been uploaded yet. Upload a photo and it will appear here."}
          </p>
        )}

        {items.length > 0 && view === "grid" && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {items.map((asset) => (
              <li key={asset.id}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect(asset);
                    onClose();
                  }}
                  className="group flex w-full flex-col gap-1 text-left"
                >
                  <span className="relative block aspect-[4/5] overflow-hidden rounded-sm border border-border bg-background group-hover:border-accent group-focus-visible:outline group-focus-visible:outline-2">
                    <Image
                      src={asset.url}
                      alt=""
                      fill
                      sizes="120px"
                      className="object-cover"
                    />
                  </span>
                  <span className="truncate font-body text-xs text-text">
                    {asset.original_filename}
                  </span>
                  <span className="font-body text-xs text-muted">
                    {describe(asset)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {items.length > 0 && view === "list" && (
          <ul className="flex flex-col divide-y divide-border">
            {items.map((asset) => (
              <li key={asset.id}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect(asset);
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 py-2 text-left hover:bg-background focus-visible:outline focus-visible:outline-2"
                >
                  <span className="relative block size-12 shrink-0 overflow-hidden rounded-sm border border-border bg-background">
                    <Image
                      src={asset.url}
                      alt=""
                      fill
                      sizes="48px"
                      className="object-cover"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-body text-sm text-text">
                      {asset.original_filename}
                    </span>
                    <span className="block font-body text-xs text-muted">
                      {describe(asset)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
          <span aria-live="polite" className="font-body text-xs text-muted">
            {loading ? "Loading…" : `Showing ${showing} of ${total}`}
          </span>
          <span className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </span>
        </div>
      </div>
    </Modal>
  );
}

/**
 * The line under a thumbnail: size, dimensions, and whether anything uses it.
 *
 * "In use" is the part worth showing. An asset a live product is displaying is
 * not the same thing as a stray upload, and a vendor about to reuse or (later)
 * delete one should be able to see the difference without leaving the dialog.
 */
function describe(asset: MediaAsset): string {
  const parts = [formatBytes(asset.byte_size)];
  if (asset.width && asset.height) parts.push(`${asset.width}×${asset.height}`);
  if (asset.used_by_count > 0) {
    parts.push(
      asset.used_by_count === 1 ? "in use" : `in use on ${asset.used_by_count}`,
    );
  }
  return parts.join(" · ");
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
