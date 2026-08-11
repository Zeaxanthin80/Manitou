/**
 * Typed client for the FastAPI backend.
 *
 * The types below mirror the Pydantic response schemas in backend/app/schemas/.
 * They are written by hand rather than generated: one more build step for six
 * types is not worth it yet, and a mismatch surfaces immediately as a TypeScript
 * error when a page reads a field the API does not send.
 *
 * Money arrives as STRINGS, not numbers. numeric(10,2) serialises to "24.00" so
 * no value is ever put through a float. Format for display with formatMoney;
 * never parseFloat a price and never do arithmetic on it in the browser -- the
 * API is the only place money is calculated.
 *
 * Called from Server Components, so API_URL stays server-side and the browser
 * never talks to FastAPI directly.
 */

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/* ---------------------------------------------------------------- types -- */

export type Image = {
  url: string;
  alt_text: string;
  is_primary: boolean;
};

export type Category = {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
};

export type Variant = {
  id: number;
  sku: string;
  variant_name: string;
  attributes: Record<string, string>;
  /** Effective price -- price_override when set, otherwise the product's base. */
  price: string;
  in_stock: boolean;
};

export type ProductListItem = {
  id: number;
  name: string;
  slug: string;
  base_price: string;
  unit_of_measure: string;
  category_id: number;
  primary_image: Image | null;
  /** Cheapest and dearest sellable price across the variants, after applying
   *  each price_override. Equal when every variant costs the same. */
  min_price: string;
  max_price: string;
};

export type ProductDetail = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  base_price: string;
  unit_of_measure: string;
  category: Category;
  images: Image[];
  variants: Variant[];
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/* --------------------------------------------------------------- client -- */

async function get<T>(path: string): Promise<T> {
  // Not cached. Next.js does not cache fetch by default without Cache
  // Components, which is what a store wants: prices and stock must be live.
  // Caching is a Phase 8 decision once load testing shows it is needed.
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });

  if (!res.ok) {
    throw new ApiError(res.status, `GET ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function listProducts(params: {
  category?: string;
  q?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Page<ProductListItem>> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return get<Page<ProductListItem>>(`/products${query ? `?${query}` : ""}`);
}

export function getProduct(slug: string): Promise<ProductDetail> {
  return get<ProductDetail>(`/products/${encodeURIComponent(slug)}`);
}

export function listCategories(): Promise<Category[]> {
  return get<Category[]>("/categories");
}

export function getCategory(slug: string): Promise<Category> {
  return get<Category>(`/categories/${encodeURIComponent(slug)}`);
}
