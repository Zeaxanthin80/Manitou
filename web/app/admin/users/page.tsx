import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Pagination } from "@/components/pagination";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, listAdminUsers } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

const PER_PAGE = 20;

/**
 * Every account, admins included.
 *
 * Filters live in the URL rather than component state, matching /admin/orders:
 * the server does the query, so the parameters have to be in the address for the
 * request to differ -- and a filtered view stays shareable.
 */
export default async function AdminUsersPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; q?: string; role?: string; active?: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { page, q, role, active } = await searchParams;
  if (role && !["customer", "admin"].includes(role)) notFound();
  if (active && !["true", "false"].includes(active)) notFound();

  const parsed = Number(page);
  const current = Number.isInteger(parsed) && parsed > 0 ? parsed : 1;

  let users;
  try {
    users = await listAdminUsers(token, {
      q,
      role,
      active: active === undefined ? undefined : active === "true",
      limit: PER_PAGE,
      offset: (current - 1) * PER_PAGE,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const filters: { label: string; params: Record<string, string | undefined> }[] = [
    { label: "All", params: {} },
    { label: "Customers", params: { role: "customer" } },
    { label: "Admins", params: { role: "admin" } },
    { label: "Suspended", params: { active: "false" } },
  ];
  const href = (params: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
    if (q) p.set("q", q);
    const qs = p.toString();
    return qs ? `/admin/users?${qs}` : "/admin/users";
  };

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Users
        </h1>
        <p className="font-body text-sm text-muted">
          {users.total} {users.total === 1 ? "account" : "accounts"}
        </p>
      </div>

      <form action="/admin/users" className="mt-6 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 font-body text-xs uppercase tracking-wide text-muted">
          Search
          <input
            name="q"
            defaultValue={q ?? ""}
            placeholder="Name or email"
            className="w-64 rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
          />
        </label>
        {role && <input type="hidden" name="role" value={role} />}
        {active && <input type="hidden" name="active" value={active} />}
        <button
          type="submit"
          className="rounded-md border border-border px-4 py-2 font-body text-sm text-text hover:bg-background"
        >
          Search
        </button>
      </form>

      <nav aria-label="Filter users" className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
        {filters.map((f) => {
          const activeFilter =
            (f.params.role ?? undefined) === role &&
            (f.params.active ?? undefined) === active;
          return (
            <Link
              key={f.label}
              href={href(f.params)}
              aria-current={activeFilter ? "page" : undefined}
              className={cn(
                "font-body text-sm transition-colors motion-reduce:transition-none",
                activeFilter
                  ? "text-accent underline decoration-2 underline-offset-8"
                  : "text-muted hover:text-text",
              )}
            >
              {f.label}
            </Link>
          );
        })}
      </nav>

      {users.items.length === 0 ? (
        <p className="mt-10 font-body text-base text-muted">No accounts match.</p>
      ) : (
        <>
          <div className="mt-8 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Account</TH>
                  <TH>Role</TH>
                  <TH>Status</TH>
                  <TH className="text-right">Orders</TH>
                  <TH className="text-right">Lifetime</TH>
                  <TH>Joined</TH>
                </TR>
              </THead>
              <TBody>
                {users.items.map((u) => (
                  <TR key={u.id}>
                    <TD>
                      <Link
                        href={`/admin/users/${u.id}`}
                        className={cn(
                          "font-display text-sm uppercase tracking-tight hover:text-accent",
                          u.is_active ? "text-text" : "text-muted",
                        )}
                      >
                        {u.full_name}
                      </Link>
                      <span className="block max-w-xs truncate font-body text-xs text-muted">
                        {u.email}
                      </span>
                    </TD>
                    <TD className="text-muted">{u.role}</TD>
                    <TD>
                      {u.is_active ? (
                        <span className="font-body text-xs uppercase tracking-wide text-muted">
                          Active
                        </span>
                      ) : (
                        <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-wide text-accent">
                          Suspended
                        </span>
                      )}
                    </TD>
                    <TD className="text-right">{u.order_count}</TD>
                    <TD className="text-right font-display">
                      {formatMoney(u.lifetime_value)}
                    </TD>
                    <TD className="whitespace-nowrap text-muted">
                      {new Date(u.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                      })}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>

          <Pagination
            total={users.total}
            limit={users.limit}
            offset={users.offset}
            basePath="/admin/users"
            params={{ q, role, active }}
          />
        </>
      )}
    </main>
  );
}
