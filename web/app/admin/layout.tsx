import { notFound, redirect } from "next/navigation";

import { currentUser } from "@/app/actions/auth";
import { AdminNav } from "@/components/admin-nav";
import { ToastProvider } from "@/components/ui/toast";

export const metadata = { title: "Vendor portal" };

/**
 * The portal's role gate.
 *
 * This check is UX, not security. The real control is require_admin on the API,
 * which reads `role` from the DATABASE rather than the token -- so revoking
 * someone's admin takes effect immediately instead of whenever their JWT
 * expires. Everything below renders data the API would refuse to send anyway;
 * the gate just avoids rendering a portal that would then fail on every request.
 *
 * Two different answers for two different situations:
 *   signed out  -> redirect to /login. They may well be an admin; ask them.
 *   not an admin -> notFound(). 403 would confirm that /admin exists and that
 *                   they simply lack the role, which is the same reasoning that
 *                   makes someone else's order a 404 rather than a 403.
 *
 * Running on every admin request is the point: a layout is not a one-time check,
 * it re-runs for each navigation into the segment.
 */
export default async function AdminLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.role !== "admin") notFound();

  return (
    // Mounted here rather than in the root layout: the storefront has no use for
    // toasts yet, and useToast() throws outside a provider, so scoping it keeps
    // that error meaningful.
    <ToastProvider>
      <AdminNav email={user.email} fullName={user.full_name} />
      {children}
    </ToastProvider>
  );
}
