import "server-only";

import { cookies } from "next/headers";

/**
 * The JWT lives in an httpOnly cookie, never in localStorage.
 *
 * JavaScript cannot read an httpOnly cookie, so an XSS payload -- injected by a
 * compromised dependency or a rendering mistake -- cannot exfiltrate the token.
 * localStorage offers no such protection: anything running in the page can read
 * it. That tradeoff is set out in docs/reference/p2-01-api-authentication.html.
 *
 * The cost is that the browser can no longer send the Authorization header
 * itself, so the token never leaves the server: Server Components and Server
 * Actions read the cookie and forward it to FastAPI as a Bearer header. The
 * browser talks only to Next.js; Next.js talks to the API.
 *
 * `import "server-only"` makes importing this file from a Client Component a
 * BUILD error rather than a runtime surprise -- the guard that stops the token
 * reaching the browser bundle by accident.
 */

const COOKIE = "manitou_session";

export async function setSession(token: string, expiresAt: Date) {
  const store = await cookies();
  store.set(COOKIE, token, {
    httpOnly: true, // unreadable by JavaScript -- the whole point
    // Lax lets the cookie ride ordinary top-level navigations (following a link
    // back into the site) while withholding it from cross-site POSTs, which is
    // the CSRF vector. Strict would log the user out on every inbound link.
    sameSite: "lax",
    // Sent over HTTPS only. Off in development because localhost is plain HTTP;
    // Phase 6 serves HTTPS, where this must be on.
    secure: process.env.NODE_ENV === "production",
    expires: expiresAt,
    path: "/",
  });
}

export async function getSession(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE)?.value ?? null;
}

export async function clearSession() {
  const store = await cookies();
  store.delete(COOKIE);
}
