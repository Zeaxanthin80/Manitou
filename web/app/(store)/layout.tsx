import { SiteHeader } from "@/components/site-header";

/**
 * Storefront chrome.
 *
 * Everything a shopper sees renders inside this; /admin does not, which is the
 * whole reason the route group exists. The group name is in parentheses so it
 * never appears in a URL -- /cart is still /cart.
 */
export default function StoreLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <SiteHeader />
      {children}
    </>
  );
}
