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

export type User = {
  id: number;
  email: string;
  full_name: string;
  phone: string | null;
  role: string;
  /** Whether two-factor is on. Never the secret -- only its existence. */
  totp_enabled: boolean;
  created_at: string;
};

export type Token = {
  access_token: string;
  token_type: string;
};

/** What /auth/login returns when the account has two-factor on: proof the
 *  password step passed, and nothing more. The challenge carries scope="2fa" and
 *  is refused by every authenticated endpoint. */
export type MfaChallenge = {
  mfa_required: true;
  challenge: string;
};

/** Narrowing helper. Both shapes come back from the same call, so every caller
 *  has to ask which one it got -- the type system makes forgetting impossible. */
export function isMfaChallenge(r: Token | MfaChallenge): r is MfaChallenge {
  return "mfa_required" in r;
}

export type TwoFactorSetup = {
  secret: string;
  provisioning_uri: string;
  qr_data_uri: string;
};

export type CartLineVariant = {
  id: number;
  sku: string;
  variant_name: string;
  attributes: Record<string, string>;
  product_name: string;
  product_slug: string;
  /** Live price, not a snapshot -- a cart shows today's price. Only order_items
   *  freeze it (see PROJECT_PLAN Section 6.4). */
  price: string;
  in_stock: boolean;
};

export type CartItem = {
  id: number;
  quantity: number;
  variant: CartLineVariant;
  line_total: string;
};

export type Cart = {
  items: CartItem[];
  item_count: number;
  subtotal: string;
  /** Quoted by the API, never computed here. Doing `subtotal * rate` in
   *  JavaScript disagrees with the server's Decimal math on roughly 1 in 800
   *  subtotals at an 8.25% rate -- a page that quotes a cent less than the card
   *  is charged. Money arithmetic happens in exactly one place. */
  tax: string;
  shipping_cost: string;
  total: string;
};

export type Address = {
  id: number;
  line1: string;
  line2: string | null;
  city: string;
  state: string | null;
  postal_code: string;
  country: string;
  type: "shipping" | "billing";
  is_default: boolean;
};

export type OrderItem = {
  id: number;
  variant_id: number;
  /** Frozen at purchase time. Never re-derived from the live product -- that is
   *  the whole point of the snapshot (PROJECT_PLAN Section 6.4). */
  product_name_snapshot: string;
  unit_price_snapshot: string;
  quantity: number;
};

export type OrderSummary = {
  id: number;
  status: string;
  subtotal: string;
  tax: string;
  shipping_cost: string;
  total: string;
  created_at: string;
};

export type OrderDetail = OrderSummary & {
  items: OrderItem[];
  shipping_address: Address;
  billing_address: Address;
};

/* ------------------------------------------------------------------ admin -- */

export type AdminVariant = {
  id: number;
  sku: string;
  variant_name: string;
  attributes: Record<string, string>;
  price_override: string | null;
  quantity_available: number;
  reorder_level: number;
  /** Computed by the API from quantity_available <= reorder_level. Not derived
   *  here -- the threshold rule belongs in one place. */
  needs_reorder: boolean;
};

export type AdminImage = {
  id: number;
  url: string;
  alt_text: string;
  is_primary: boolean;
};

export type AdminProduct = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  category_id: number;
  base_price: string;
  unit_of_measure: string;
  is_active: boolean;
  created_at: string;
  variants: AdminVariant[];
  /** Primary first, then oldest first -- ordered by the API so the gallery does
   *  not reshuffle between requests. */
  images: AdminImage[];
};

export type AdminStatusCount = { status: string; count: number; value: string };
export type AdminTopProduct = {
  /** The snapshot name from order_items, so a renamed product appears under the
   *  name it actually sold as. */
  product_name: string;
  units: number;
  revenue: string;
};
export type AdminLowStock = {
  product_id: number;
  product_name: string;
  variant_id: number;
  sku: string;
  variant_name: string;
  quantity_available: number;
  reorder_level: number;
};

export type AdminSummary = {
  /** paid + shipped + delivered only. Not the sum of every order -- that would
   *  count cancellations as takings. */
  revenue_all_time: string;
  revenue_last_30_days: string;
  orders_counted: number;
  average_order_value: string;
  pending_count: number;
  pending_value: string;
  by_status: AdminStatusCount[];
  top_products: AdminTopProduct[];
  low_stock: AdminLowStock[];
};

export type AdminUserSummary = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  totp_enabled: boolean;
  created_at: string;
  order_count: number;
  lifetime_value: string;
};

export type AdminUserDetail = AdminUserSummary & {
  phone: string | null;
  password_changed_at: string | null;
  addresses: Address[];
  recent_orders: AdminOrderSummary[];
  /** What the API will actually permit against this user right now. The portal
   *  renders one control per entry and computes nothing itself -- the same
   *  contract as AdminOrderDetail.allowed_transitions. It is how the
   *  self-lockout and last-admin guards become visible rather than merely
   *  enforced: your own row simply has no suspend button. */
  allowed_actions: string[];
};

export type AdminAuditEvent = {
  id: number;
  actor_user_id: number | null;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: number | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
};

export type AdminOrderSummary = OrderSummary & {
  user_id: number;
  user_email: string;
  item_count: number;
};

export type AdminOrderDetail = AdminOrderSummary & {
  user_full_name: string;
  items: OrderItem[];
  shipping_address: Address;
  billing_address: Address;
  /** Which statuses this order may move to right now, decided by the API's
   *  ALLOWED_TRANSITIONS map. Never re-derive this in the browser: a second copy
   *  of the workflow in another language is one that will drift, and the portal
   *  would then offer a button the API refuses. */
  allowed_transitions: string[];
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

type Options = { token?: string | null; body?: unknown; method?: string };

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { token, body, method = body ? "POST" : "GET" } = options;

  // Not cached. Next.js does not cache fetch by default without Cache
  // Components, which is what a store wants: prices and stock must be live.
  // Caching is a Phase 8 decision once load testing shows it is needed.
  const res = await fetch(`${API_URL}${path}`, {
    method,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      // The token is attached here, server-side. It never reaches the browser.
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });

  if (!res.ok) {
    // FastAPI puts the reason in `detail`; surface it so a form can show the
    // API's own message instead of a generic failure.
    let detail = `${method} ${path} -> ${res.status}`;
    try {
      const payload = await res.json();
      if (typeof payload?.detail === "string") {
        // HTTPException: `detail` is the sentence the endpoint wrote.
        detail = payload.detail;
      } else if (Array.isArray(payload?.detail)) {
        // Pydantic validation (422) puts an ARRAY of {loc, msg, type} here, not
        // a string. Without this branch every schema-level rejection fell
        // through to the generic message above, so a careful error written in a
        // validator reached the admin as "POST /admin/products/36/images -> 422".
        // Pydantic v2 prefixes a raised ValueError with "Value error, "; that is
        // an implementation detail of the library, not something to show a user.
        const messages = payload.detail
          .map((e: { msg?: string }) => e?.msg?.replace(/^Value error, /, ""))
          .filter(Boolean);
        if (messages.length > 0) detail = messages.join(" ");
      }
    } catch {
      /* non-JSON error body; keep the generic message */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const get = <T>(path: string, token?: string | null) => request<T>(path, { token });

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

/* ----------------------------------------------------------------- auth -- */

/** Returns a Token, OR an MfaChallenge when the account has 2FA enabled. Use
 *  isMfaChallenge() to tell them apart -- the union is deliberate, so that a
 *  caller cannot silently treat a challenge as a session. */
export function login(
  email: string,
  password: string,
): Promise<Token | MfaChallenge> {
  return request<Token | MfaChallenge>("/auth/login", {
    body: { email, password },
  });
}

export function register(input: {
  email: string;
  password: string;
  full_name: string;
}): Promise<User> {
  return request<User>("/auth/register", { body: input });
}

export function getCurrentUser(token: string): Promise<User> {
  return request<User>("/auth/me", { token });
}

/* ----------------------------------------------------------------- cart -- */

export const getCart = (token: string) => request<Cart>("/cart", { token });

export const addCartItem = (token: string, variantId: number, quantity: number) =>
  request<Cart>("/cart/items", {
    token,
    body: { variant_id: variantId, quantity },
  });

export const updateCartItem = (token: string, itemId: number, quantity: number) =>
  request<Cart>(`/cart/items/${itemId}`, {
    token,
    method: "PATCH",
    body: { quantity },
  });

export const removeCartItem = (token: string, itemId: number) =>
  request<void>(`/cart/items/${itemId}`, { token, method: "DELETE" });

/* ------------------------------------------------------ addresses, orders -- */

export const listAddresses = (token: string) =>
  request<Address[]>("/addresses", { token });

export const createAddress = (
  token: string,
  body: Omit<Address, "id">,
) => request<Address>("/addresses", { token, body });

export const placeOrder = (
  token: string,
  shippingAddressId: number,
  billingAddressId: number,
) =>
  request<OrderDetail>("/orders", {
    token,
    body: {
      shipping_address_id: shippingAddressId,
      billing_address_id: billingAddressId,
    },
  });

export const deleteAddress = (token: string, id: number) =>
  request<void>(`/addresses/${id}`, { token, method: "DELETE" });

export const listOrders = (token: string, limit = 20, offset = 0) =>
  request<Page<OrderSummary>>(
    `/orders?limit=${limit}&offset=${offset}`,
    { token },
  );

export const getOrder = (token: string, id: number) =>
  request<OrderDetail>(`/orders/${id}`, { token });

export const listAdminOrders = (
  token: string,
  { limit = 20, offset = 0, status }: { limit?: number; offset?: number; status?: string } = {},
) => {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) q.set("status", status);
  return request<Page<AdminOrderSummary>>(`/admin/orders?${q}`, { token });
};

export const getAdminOrder = (token: string, id: number) =>
  request<AdminOrderDetail>(`/admin/orders/${id}`, { token });

export const updateOrderStatus = (token: string, id: number, status: string) =>
  request<AdminOrderDetail>(`/admin/orders/${id}`, {
    token,
    method: "PATCH",
    body: { status },
  });

/* ------------------------------------------------------- admin: catalog -- */

export const listAdminProducts = (token: string, limit = 50, offset = 0) =>
  request<Page<AdminProduct>>(`/admin/products?limit=${limit}&offset=${offset}`, {
    token,
  });

export const createProduct = (token: string, body: unknown) =>
  request<AdminProduct>("/admin/products", { token, body });

export const updateProduct = (token: string, id: number, body: unknown) =>
  request<AdminProduct>(`/admin/products/${id}`, { token, method: "PATCH", body });

/** Soft delete -- sets is_active = false. Named for what it does, not for the
 *  HTTP verb: a product that has ever sold can never really be removed, because
 *  order_items still points at its variants. */
export const deactivateProduct = (token: string, id: number) =>
  request<void>(`/admin/products/${id}`, { token, method: "DELETE" });

export const addProductImage = (token: string, productId: number, body: unknown) =>
  request<AdminProduct>(`/admin/products/${productId}/images`, { token, body });

export const updateProductImage = (token: string, imageId: number, body: unknown) =>
  request<AdminProduct>(`/admin/images/${imageId}`, { token, method: "PATCH", body });

export const deleteProductImage = (token: string, imageId: number) =>
  request<AdminProduct>(`/admin/images/${imageId}`, { token, method: "DELETE" });

export const addVariant = (token: string, productId: number, body: unknown) =>
  request<AdminProduct>(`/admin/products/${productId}/variants`, { token, body });

export const updateVariant = (token: string, variantId: number, body: unknown) =>
  request<AdminProduct>(`/admin/variants/${variantId}`, { token, method: "PATCH", body });

/** Absolute stock levels, not a delta. The vendor is recording a count they
 *  took, so send what they typed -- a +/- adjustment would race checkout, which
 *  is the one place that legitimately does read-modify-write under a row lock. */
export const updateInventory = (
  token: string,
  variantId: number,
  body: { quantity_available?: number; reorder_level?: number },
) =>
  request<AdminVariant>(`/admin/variants/${variantId}/inventory`, {
    token,
    method: "PATCH",
    body,
  });

export const getAdminSummary = (token: string) =>
  request<AdminSummary>("/admin/summary", { token });

/* ------------------------------------------------- account self-service -- */

export const updateProfile = (
  token: string,
  body: { full_name?: string; phone?: string | null },
) => request<User>("/auth/me", { token, method: "PATCH", body });

/** Returns a FRESH token. The caller must store it: every token issued before
 *  the change is now rejected, including the one that made the request. */
export const changePassword = (
  token: string,
  current_password: string,
  new_password: string,
) =>
  request<Token>("/auth/change-password", {
    token,
    body: { current_password, new_password },
  });

export const changeEmail = (
  token: string,
  current_password: string,
  new_email: string,
) =>
  request<User>("/auth/change-email", {
    token,
    body: { current_password, new_email },
  });

export const deleteAccount = (token: string, current_password: string) =>
  request<void>("/auth/me", {
    token,
    method: "DELETE",
    body: { current_password },
  });

/* -------------------------------------------------------- password reset -- */

export const forgotPassword = (email: string) =>
  request<{ detail: string }>("/auth/forgot-password", { body: { email } });

export const resetPassword = (token: string, new_password: string) =>
  request<void>("/auth/reset-password", { body: { token, new_password } });

/* ------------------------------------------------------------ two-factor -- */

export const twoFactorSetup = (token: string) =>
  request<TwoFactorSetup>("/auth/2fa/setup", { token, body: {} });

/** The recovery codes come back exactly once. There is no endpoint to fetch them
 *  again -- they are bcrypt-hashed on write, so this response is the only place
 *  the plaintext ever exists. */
export const twoFactorEnable = (token: string, code: string) =>
  request<{ recovery_codes: string[] }>("/auth/2fa/enable", {
    token,
    body: { code },
  });

export const twoFactorDisable = (token: string, current_password: string) =>
  request<void>("/auth/2fa/disable", { token, body: { current_password } });

export const twoFactorVerify = (challenge: string, code: string) =>
  request<Token>("/auth/2fa/verify", { body: { challenge, code } });

/* --------------------------------------------------------- admin: users -- */

export const listAdminUsers = (
  token: string,
  {
    q,
    role,
    active,
    limit = 20,
    offset = 0,
  }: { q?: string; role?: string; active?: boolean; limit?: number; offset?: number } = {},
) => {
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) p.set("q", q);
  if (role) p.set("role", role);
  if (active !== undefined) p.set("active", String(active));
  return request<Page<AdminUserSummary>>(`/admin/users?${p}`, { token });
};

export const getAdminUser = (token: string, id: number) =>
  request<AdminUserDetail>(`/admin/users/${id}`, { token });

export const updateAdminUser = (
  token: string,
  id: number,
  body: { is_active?: boolean; role?: string },
) => request<AdminUserDetail>(`/admin/users/${id}`, { token, method: "PATCH", body });

export const sendAdminPasswordReset = (token: string, id: number) =>
  request<{ detail: string }>(`/admin/users/${id}/password-reset`, { token, body: {} });

export const adminDisableTwoFactor = (token: string, id: number) =>
  request<void>(`/admin/users/${id}/disable-2fa`, { token, body: {} });

export const adminAnonymise = (token: string, id: number, current_password: string) =>
  request<void>(`/admin/users/${id}/anonymise`, { token, body: { current_password } });

/** Read-only by design. There is deliberately no create, update or delete
 *  counterpart: audit_events is append-only in the database via a trigger, and
 *  an API door would make that guarantee decorative. */
export const listAuditEvents = (
  token: string,
  {
    action,
    target_type,
    target_id,
    limit = 50,
    offset = 0,
  }: {
    action?: string;
    target_type?: string;
    target_id?: number;
    limit?: number;
    offset?: number;
  } = {},
) => {
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (action) p.set("action", action);
  if (target_type) p.set("target_type", target_type);
  if (target_id !== undefined) p.set("target_id", String(target_id));
  return request<Page<AdminAuditEvent> & { actions: string[] }>(
    `/admin/audit?${p}`,
    { token },
  );
};
