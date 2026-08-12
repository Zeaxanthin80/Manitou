"use server";

import { redirect } from "next/navigation";

import {
  ApiError,
  getCurrentUser,
  isMfaChallenge,
  login,
  register,
  twoFactorVerify,
} from "@/lib/api";
import {
  clearChallenge,
  clearSession,
  getChallenge,
  getSession,
  setChallenge,
  setSession,
} from "@/lib/session";
import type { User } from "@/lib/api";

/**
 * Auth as Server Actions.
 *
 * A form posts straight to these -- no route handler, no client-side fetch, and
 * the password never travels anywhere except from the browser to this server
 * function and on to FastAPI.
 *
 * Worth knowing (the Next.js docs are explicit about it): a Server Action is a
 * real POST endpoint reachable directly, not only through your form. These two
 * are public by nature, but every future action that touches a cart or an order
 * must check the session itself rather than assuming the UI gated it.
 */

export type FormState = { error?: string; mfaRequired?: boolean };

/** Read the JWT's own `exp` claim so the cookie dies exactly when the token
 *  does. Hardcoding a duration here would let the two drift apart, leaving a
 *  cookie that looks valid and a token the API rejects.
 *
 *  This only READS the payload for its expiry -- it does not verify the
 *  signature, and must never be used to decide anything about identity or role.
 *  Only the API validates tokens. */
function tokenExpiry(token: string): Date {
  try {
    const [, payload] = token.split(".");
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    if (typeof exp === "number") return new Date(exp * 1000);
  } catch {
    /* fall through */
  }
  return new Date(Date.now() + 60 * 60 * 1000);
}

export async function loginAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  try {
    const result = await login(email, password);

    // Two shapes come back from one call. An account with two-factor gets a
    // challenge, which is NOT a session -- it grants access to nothing until it
    // is exchanged for a real token at the code step.
    if (isMfaChallenge(result)) {
      await setChallenge(result.challenge);
      return { mfaRequired: true };
    }

    await setSession(result.access_token, tokenExpiry(result.access_token));
  } catch (error) {
    if (error instanceof ApiError) {
      // The API returns one identical 401 for an unknown email and a wrong
      // password, so this cannot leak which accounts exist. Passing its message
      // through preserves that property.
      return { error: error.message };
    }
    throw error;
  }

  // Outside the try: redirect() works by throwing, so catching around it would
  // swallow the navigation and look like a silent failure.
  redirect("/");
}

export async function registerAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const fullName = String(formData.get("full_name") ?? "");

  try {
    await register({ email, password, full_name: fullName });
    // Registration does not return a token, so log in straight away rather
    // than making a new customer fill in the same details twice. A brand-new
    // account cannot have 2FA on, but narrow anyway rather than assert -- the
    // union exists precisely so nobody has to remember that.
    const result = await login(email, password);
    if (isMfaChallenge(result)) {
      await setChallenge(result.challenge);
      return { mfaRequired: true };
    }
    await setSession(result.access_token, tokenExpiry(result.access_token));
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  redirect("/");
}

export async function logoutAction() {
  await clearSession();
  await clearChallenge();
  redirect("/");
}


/**
 * The second step: exchange the pending challenge plus a code for a session.
 *
 * Accepts either a six-digit authenticator code or a recovery code -- the API
 * tries both and answers with one 401 either way, so this does not need to know
 * which the customer typed.
 */
export async function verifyMfaAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const challenge = await getChallenge();
  if (!challenge) {
    // The five-minute window lapsed, or they arrived here directly.
    return { error: "That sign-in attempt expired. Please sign in again." };
  }

  const code = String(formData.get("code") ?? "").trim();

  try {
    const token = await twoFactorVerify(challenge, code);
    await setSession(token.access_token, tokenExpiry(token.access_token));
    await clearChallenge();
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  redirect("/");
}


/** Whether a half-finished sign-in is waiting for a code. Read by the login page
 *  to decide which of the two steps to render. */
export async function mfaPending(): Promise<boolean> {
  return (await getChallenge()) !== null;
}

/** The current user, or null. Used by Server Components to render signed-in
 *  state.
 *
 *  A rejected token returns null and does NOT clear the cookie. Next.js only
 *  permits modifying cookies inside a Server Action or Route Handler -- doing it
 *  during a render throws "Cookies can only be modified in a Server Action or
 *  Route Handler", because the response headers are already on their way.
 *
 *  Leaving the stale cookie costs nothing. Its expiry is set from the token's
 *  own `exp`, so an expired token means an expired cookie and the browser drops
 *  it unprompted. The only case that lingers is a still-valid token for a
 *  deleted user, which simply renders as signed-out until they log in again --
 *  and logging in overwrites the cookie anyway. */
export async function currentUser(): Promise<User | null> {
  const token = await getSession();
  if (!token) return null;
  try {
    return await getCurrentUser(token);
  } catch (error) {
    // 403 as well as 401. A suspended account holds a perfectly valid token, so
    // the API answers 403 ("I know who you are, and no") rather than 401 -- and
    // without this the storefront would throw and render a 500 at someone who
    // should simply see the signed-out view. Task 10 adds the page that explains
    // what happened; this only owes them a working site.
    if (error instanceof ApiError && [401, 403].includes(error.status)) return null;
    throw error;
  }
}
