import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

/**
 * Storefront chrome.
 *
 * Everything a shopper sees renders inside this; /admin does not, which is the
 * whole reason the route group exists. The group name is in parentheses so it
 * never appears in a URL -- /cart is still /cart.
 *
 * The flex column with `flex-1` on main is what keeps the footer at the bottom
 * of the viewport on a short page (an empty cart) instead of floating halfway up.
 */
export default function StoreLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <div className="flex-1">{children}</div>
      <SiteFooter />
    </div>
  );
}
