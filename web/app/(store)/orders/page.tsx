import Link from "next/link";
import { redirect } from "next/navigation";

import { OrderStatus } from "@/components/order-status";
import { Pagination } from "@/components/pagination";
import { buttonClasses } from "@/components/ui/button";
import { ApiError, listOrders } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

const PER_PAGE = 10;

/**
 * Order history.
 *
 * Note this file sits beside orders/[id]/page.tsx: /orders is the list and
 * /orders/52 the receipt. A static segment always wins over a dynamic one, so
 * the two never collide.
 *
 * Paging is done with a `?page=` search param rather than component state,
 * because the server is what fetches the data -- the page number has to be in
 * the URL for the request to differ at all.
 */
export default async function OrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const token = await getSession();
  // A history page has nothing to show a stranger, and no useful signed-out
  // state, so this redirects rather than rendering a prompt.
  if (!token) redirect("/login");

  const { page } = await searchParams;
  const parsed = Number(page);
  const current = Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
  const offset = (current - 1) * PER_PAGE;

  let orders;
  try {
    orders = await listOrders(token, PER_PAGE, offset);
  } catch (error) {
    // A suspended account holds a valid token, so the API answers 403 rather than
    // 401. Without this the page throws and renders a 500 at someone who should
    // be sent to sign in.
    if (error instanceof ApiError && error.status === 403) redirect("/login");
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    throw error;
  }

  // ?page=999 on a two-page history is an empty list under a "Page 999 of 2"
  // heading. The total is only known after the fetch, so the clamp has to happen
  // here rather than above -- redirecting rather than silently rendering page 1
  // keeps the URL honest about what is being shown.
  const lastPage = Math.max(1, Math.ceil(orders.total / PER_PAGE));
  if (orders.total > 0 && current > lastPage) redirect(`/orders?page=${lastPage}`);

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Your orders
      </h1>

      {orders.total === 0 ? (
        <div className="mt-8">
          <p className="font-body text-base text-muted">
            You have not placed an order yet.
          </p>
          <Link href="/" className={`${buttonClasses({ className: "mt-6" })}`}>
            Browse products
          </Link>
        </div>
      ) : (
        <>
          <ul className="mt-8 flex flex-col">
            {orders.items.map((order) => (
              <li key={order.id} className="border-b border-border py-5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
                  <div>
                    <Link
                      href={`/orders/${order.id}`}
                      className="font-display text-base uppercase tracking-tight text-text hover:text-accent"
                    >
                      Order #{order.id}
                    </Link>
                    <p className="mt-1 font-body text-sm text-muted">
                      {new Date(order.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                      })}
                    </p>
                  </div>

                  <div className="flex items-baseline gap-6">
                    <OrderStatus status={order.status} />
                    <span className="font-display text-lg text-text">
                      {formatMoney(order.total)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <Pagination
            total={orders.total}
            limit={orders.limit}
            offset={orders.offset}
            basePath="/orders"
          />
        </>
      )}
    </main>
  );
}
