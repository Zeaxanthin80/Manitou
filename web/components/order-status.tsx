/**
 * Order status as a small badge.
 *
 * The accent is reserved for states that need action or attention -- the
 * Studio direction's "one sharp accent, used sparingly". A pending or paid order
 * is unremarkable and stays neutral; a cancelled one is not.
 *
 * Unknown statuses fall back to neutral rather than throwing, because the set of
 * statuses is a database CHECK the API owns, and this component should not need
 * a deploy every time one is added.
 */
const STYLES: Record<string, string> = {
  pending: "border-border text-muted",
  paid: "border-text text-text",
  shipped: "border-text text-text",
  delivered: "border-text text-text",
  cancelled: "border-accent text-accent",
  refunded: "border-accent text-accent",
};

export function OrderStatus({ status }: { status: string }) {
  const style = STYLES[status] ?? "border-border text-muted";
  return (
    <span
      className={`inline-block rounded-sm border px-2 py-1 font-body text-xs uppercase tracking-tight ${style}`}
    >
      {status}
    </span>
  );
}
