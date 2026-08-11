import { storeConfig } from "@/lib/store-config";

/**
 * Token smoke test. Every value on this page comes from design-tokens.json or
 * store-config.json -- nothing is hardcoded. Replaced by the real catalogue in
 * task 6; until then it is how we can see that the bridge works.
 */
export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <p className="font-body text-sm text-muted">
        {storeConfig.store.name} &middot; {storeConfig.currency.code} &middot;{" "}
        {storeConfig.locale}
      </p>

      <h1 className="mt-2 font-display text-3xl text-text">
        {storeConfig.store.name}
      </h1>

      <p className="mt-4 max-w-prose font-body text-base text-muted">
        Every colour, size and space on this page resolves through Tailwind from
        the design tokens at the repo root.
      </p>

      {/* Class names are written out in full on purpose. Tailwind scans source
          for complete class strings and never evaluates JavaScript, so a
          template literal like `bg-${name}` produces no CSS at all -- the build
          succeeds and the swatch renders blank. This is the most common Tailwind
          mistake there is. */}
      <div className="mt-8 flex flex-wrap gap-2">
        {(
          [
            ["background", "bg-background"],
            ["surface", "bg-surface"],
            ["text", "bg-text"],
            ["muted", "bg-muted"],
            ["border", "bg-border"],
            ["primary", "bg-primary"],
            ["accent", "bg-accent"],
            ["success", "bg-success"],
            ["warning", "bg-warning"],
            ["error", "bg-error"],
          ] as const
        ).map(([name, swatch]) => (
          <div
            key={name}
            className="w-28 overflow-hidden rounded-md border border-border shadow-sm"
          >
            <div className={`h-12 ${swatch}`} />
            <p className="p-2 font-body text-xs text-muted">{name}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 flex items-center gap-4">
        <button className="rounded-md bg-primary px-4 py-2 font-body text-sm text-surface">
          Add to cart
        </button>
        <span className="rounded-sm bg-accent px-2 py-1 font-body text-xs text-surface">
          Sale
        </span>
      </div>
    </main>
  );
}
