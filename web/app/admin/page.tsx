import Link from "next/link";

import { Card, CardBody, CardTitle } from "@/components/ui/card";

/**
 * Portal landing page.
 *
 * A placeholder until task 5 replaces it with the real sales/inventory summary.
 * It exists now so /admin resolves and the role gate can be tested on its own,
 * which is the whole point of doing task 1 by itself.
 */
const SECTIONS = [
  {
    href: "/admin/orders",
    title: "Orders",
    body: "Review every order and advance it through paid, shipped and delivered.",
  },
  {
    href: "/admin/products",
    title: "Products",
    body: "Create and edit products, variants and images. Hide a product without deleting it.",
  },
  {
    href: "/admin/inventory",
    title: "Inventory",
    body: "Set stock levels and reorder points, and see what is running low.",
  },
];

export default function AdminHome() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Vendor portal
      </h1>
      <p className="mt-3 max-w-prose font-body text-base text-muted">
        The sales and inventory summary arrives in task 5. Until then, the
        sections below are where the work happens.
      </p>

      <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href} className="group">
            <Card className="h-full transition-colors group-hover:border-text motion-reduce:transition-none">
              <CardBody>
                <CardTitle>{s.title}</CardTitle>
                <p className="mt-2 font-body text-sm text-muted">{s.body}</p>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
