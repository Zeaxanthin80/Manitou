import Link from "next/link";

import { currentCart } from "@/app/actions/cart";
import { currentAddresses } from "@/app/actions/checkout";
import { AddressForm } from "@/components/address-form";
import { CheckoutForm } from "@/components/checkout-form";
import { OrderTotals } from "@/components/order-totals";
import { Card, CardBody } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";

/**
 * Checkout.
 *
 * A Server Component: it reads the cart and the saved addresses on the server
 * with the session cookie, so no token ever reaches the browser. The two
 * interactive pieces -- picking an address, adding one -- are Client Components
 * nested inside.
 *
 * Three states, in order of how early they stop you:
 *   signed out  -> nothing to check out with
 *   empty cart  -> the API would 422; say so before they try
 *   no address  -> the only path forward is to create one
 */
export default async function CheckoutPage() {
  const cart = await currentCart();

  if (!cart) {
    return (
      <Shell>
        <p className="font-body text-base text-muted">
          Please{" "}
          <Link href="/login" className="text-text underline">
            sign in
          </Link>{" "}
          to check out.
        </p>
      </Shell>
    );
  }

  if (cart.items.length === 0) {
    return (
      <Shell>
        <p className="font-body text-base text-muted">Your cart is empty.</p>
        <Link
          href="/"
          className="mt-4 inline-block font-body text-sm uppercase tracking-tight text-text underline"
        >
          Browse products
        </Link>
      </Shell>
    );
  }

  const addresses = await currentAddresses();

  return (
    <Shell>
      <div className="grid gap-12 lg:grid-cols-[1fr_20rem]">
        <div>
          {addresses.length === 0 ? (
            <>
              <h2 className="font-body text-sm uppercase tracking-tight text-muted">
                Add a delivery address
              </h2>
              <p className="mt-2 mb-6 max-w-prose font-body text-sm text-muted">
                We need somewhere to send this order.
              </p>
              <AddressForm />
            </>
          ) : (
            <>
              <CheckoutForm addresses={addresses} />
              <details className="mt-10">
                <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-muted hover:text-text">
                  Use a different address
                </summary>
                <div className="mt-6">
                  <AddressForm compact />
                </div>
              </details>
            </>
          )}
        </div>

        <aside>
          <Card>
            <CardBody>
              <h2 className="font-body text-sm uppercase tracking-tight text-muted">
                Order summary
              </h2>

              <ul className="mt-4 flex flex-col gap-3 border-b border-border pb-4">
                {cart.items.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-baseline justify-between gap-4 font-body text-sm"
                  >
                    <span className="text-text">
                      {item.variant.product_name}
                      <span className="text-muted">
                        {item.variant.variant_name
                          ? ` / ${item.variant.variant_name}`
                          : ""}{" "}
                        &times; {item.quantity}
                      </span>
                    </span>
                    <span className="shrink-0 text-text">
                      {formatMoney(item.line_total)}
                    </span>
                  </li>
                ))}
              </ul>

              <OrderTotals
                className="mt-4"
                subtotal={cart.subtotal}
                tax={cart.tax}
                shippingCost={cart.shipping_cost}
                total={cart.total}
              />
            </CardBody>
          </Card>

          <Link
            href="/cart"
            className="mt-4 inline-block font-body text-sm text-muted underline hover:text-text"
          >
            Edit cart
          </Link>
        </aside>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Checkout
      </h1>
      <div className="mt-8">{children}</div>
    </main>
  );
}
