import Link from "next/link";

import { currentUser } from "@/app/actions/auth";
import { currentCart, removeFromCartAction, updateQuantityAction } from "@/app/actions/cart";
import { Button, buttonClasses } from "@/components/ui/button";
import { formatMoney } from "@/lib/format";

/**
 * The cart. A Server Component: it reads the httpOnly cookie, forwards the token
 * to FastAPI as a Bearer header, and renders complete HTML. The token never
 * reaches the browser.
 *
 * Prices here are LIVE, not snapshots. A cart should show what the customer
 * would pay today; only order_items freeze name and price, at purchase time
 * (Section 6.4).
 */
export default async function CartPage() {
  const [user, cart] = await Promise.all([currentUser(), currentCart()]);

  if (!user) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Your cart
        </h1>
        <p className="mt-4 font-body text-base text-muted">
          <Link href="/login" className="text-accent underline underline-offset-4">
            Sign in
          </Link>{" "}
          to see your cart.
        </p>
      </main>
    );
  }

  const items = cart?.items ?? [];

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Your cart
      </h1>

      {items.length === 0 ? (
        <div className="mt-8">
          <p className="font-body text-base text-muted">Your cart is empty.</p>
          <Link
            href="/"
            className="mt-4 inline-block font-body text-sm text-accent underline underline-offset-4"
          >
            Browse products
          </Link>
        </div>
      ) : (
        <>
          <ul className="mt-8 flex flex-col">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-baseline gap-4 border-b border-border py-4"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/products/${item.variant.product_slug}`}
                    className="font-display text-sm uppercase tracking-tight text-text hover:text-accent"
                  >
                    {item.variant.product_name}
                  </Link>
                  <p className="mt-1 font-body text-sm text-muted">
                    {item.variant.variant_name} &middot; {formatMoney(item.variant.price)}
                  </p>
                  <StockNote
                    isForSale={item.variant.is_for_sale}
                    sellable={item.variant.quantity_sellable}
                    quantity={item.quantity}
                  />
                </div>

                {/* Each control is its own form posting to a Server Action, so
                    the whole page works without JavaScript. */}
                <form action={updateQuantityAction} className="flex items-center gap-2">
                  <input type="hidden" name="item_id" value={item.id} />
                  <label
                    htmlFor={`qty-${item.id}`}
                    className="font-body text-xs uppercase tracking-tight text-muted"
                  >
                    Qty
                  </label>
                  <input
                    id={`qty-${item.id}`}
                    name="quantity"
                    type="number"
                    min={1}
                    defaultValue={item.quantity}
                    className="w-16 rounded-md border border-border bg-surface px-2 py-1 font-body text-sm text-text"
                  />
                  <Button type="submit" variant="ghost" size="sm">
                    Update
                  </Button>
                </form>

                <p className="w-20 text-right font-display text-base text-text">
                  {formatMoney(item.line_total)}
                </p>

                <form action={removeFromCartAction}>
                  <input type="hidden" name="item_id" value={item.id} />
                  <Button type="submit" variant="ghost" size="sm">
                    Remove
                  </Button>
                </form>
              </li>
            ))}
          </ul>

          <div className="mt-6 flex items-baseline justify-between">
            <span className="font-body text-sm uppercase tracking-tight text-muted">
              Subtotal &middot; {cart?.item_count} item
              {cart?.item_count === 1 ? "" : "s"}
            </span>
            <span className="font-display text-xl text-text">
              {formatMoney(cart?.subtotal ?? "0")}
            </span>
          </div>
          <p className="mt-1 text-right font-body text-xs text-muted">
            Tax and shipping calculated at checkout.
          </p>

          <Link
            href="/checkout"
            className={buttonClasses({ size: "lg", className: "mt-6 w-full" })}
          >
            Checkout
          </Link>
        </>
      )}
    </main>
  );
}

/**
 * What one cart line has to say about itself, in strict precedence.
 *
 * Three states, where the cart used to carry two:
 *
 *   discontinued        the product is withdrawn -- remove it
 *   nothing left        sellable is 0 -- check back later
 *   NOT ENOUGH LEFT     sellable is short of this line's quantity
 *
 * That third one is defect 10. Holding 3 when 1 remains is neither "in stock"
 * nor "out of stock", and saying nothing until zero meant a basket looked
 * entirely fine until checkout refused it -- after the customer had picked an
 * address and reached the payment step.
 *
 * **Discontinued wins over both stock cases**, and the order of these branches
 * is what enforces it. "Out of stock" means check back later, which is exactly
 * the wrong advice for something that is never coming back.
 *
 * The exact count is published deliberately. VariantRead withholds counts from
 * the public catalogue; this is a count for a line the customer already holds,
 * and it is the difference between fixing the problem here and discovering it
 * at the till.
 */
function StockNote({
  isForSale,
  sellable,
  quantity,
}: {
  isForSale: boolean;
  sellable: number;
  quantity: number;
}) {
  const note = !isForSale
    ? "No longer available \u00b7 remove to check out"
    : sellable === 0
      ? "Out of stock"
      : sellable < quantity
        ? `Only ${sellable} left \u00b7 reduce to check out`
        : null;

  if (!note) return null;

  return (
    <p className="mt-1 font-body text-xs uppercase tracking-tight text-accent">
      {note}
    </p>
  );
}
