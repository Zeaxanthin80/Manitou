import Link from "next/link";
import { redirect } from "next/navigation";

import { currentAddresses } from "@/app/actions/address";
import { currentUser, logoutAction } from "@/app/actions/auth";
import { AddressForm } from "@/components/address-form";
import { ProfileForm } from "@/components/profile-form";
import { AddressList } from "@/components/address-list";
import { OrderStatus } from "@/components/order-status";
import { Button, buttonClasses } from "@/components/ui/button";
import { ApiError, listOrders } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

/**
 * Account.
 *
 * Three things a signed-in customer needs in one place: who they are, where
 * their orders went, and the addresses they can reuse at checkout.
 *
 * The recent-orders strip is deliberately a preview of three rather than the
 * full history -- /orders already does that properly with paging, and two pages
 * competing to be the order list is how they drift apart.
 */
export default async function AccountPage() {
  const token = await getSession();
  if (!token) redirect("/login");

  const [user, addresses] = await Promise.all([currentUser(), currentAddresses()]);
  // currentUser() returns null on a rejected token rather than clearing the
  // cookie -- cookies cannot be modified during a render.
  if (!user) redirect("/login");

  let recent;
  try {
    recent = await listOrders(token, 3, 0);
  } catch (error) {
    // A suspended account holds a valid token, so the API answers 403 rather than
    // 401. Without this the page throws and renders a 500 at someone who should
    // be sent to sign in.
    if (error instanceof ApiError && error.status === 403) redirect("/login");
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    throw error;
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Your account
        </h1>
        <form action={logoutAction}>
          <Button type="submit" variant="ghost" size="sm">
            Sign out
          </Button>
        </form>
      </div>

      <section className="mt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Details
          </h2>
          <Link
            href="/account/security"
            className="font-body text-sm text-muted underline hover:text-text"
          >
            Password, email &amp; security
          </Link>
        </div>
        <div className="mt-4">
          <ProfileForm user={user} />
        </div>
        <p className="mt-4 font-body text-sm text-muted">
          {user.email} &middot; member since{" "}
          {new Date(user.created_at).toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
          })}
        </p>
      </section>

      <section className="mt-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Recent orders
          </h2>
          {recent.total > 0 && (
            <Link
              href="/orders"
              className="font-body text-sm text-muted underline hover:text-text"
            >
              View all {recent.total}
            </Link>
          )}
        </div>

        {recent.total === 0 ? (
          <p className="mt-4 font-body text-sm text-muted">
            You have not placed an order yet.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col">
            {recent.items.map((order) => (
              <li
                key={order.id}
                className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-b border-border py-4"
              >
                <Link
                  href={`/orders/${order.id}`}
                  className="font-display text-sm uppercase tracking-tight text-text hover:text-accent"
                >
                  Order #{order.id}
                </Link>
                <div className="flex items-baseline gap-6">
                  <OrderStatus status={order.status} />
                  <span className="font-body text-sm text-text">
                    {formatMoney(order.total)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12">
        <h2 className="font-body text-sm uppercase tracking-tight text-muted">
          Addresses
        </h2>
        <AddressList addresses={addresses} />

        <details className="mt-8">
          <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-muted hover:text-text">
            Add an address
          </summary>
          <div className="mt-6 max-w-lg">
            <AddressForm />
          </div>
        </details>
      </section>

      <Link href="/" className={buttonClasses({ variant: "ghost", className: "mt-12" })}>
        Continue shopping
      </Link>
    </main>
  );
}
