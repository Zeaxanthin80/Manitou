"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  ApiError,
  changeEmail,
  changePassword,
  deleteAccount,
  forgotPassword,
  resetPassword,
  twoFactorDisable,
  twoFactorEnable,
  twoFactorSetup,
  updateProfile,
} from "@/lib/api";
import type { TwoFactorSetup } from "@/lib/api";
import { clearChallenge, clearSession, getSession, setSession } from "@/lib/session";

/**
 * Account self-service actions.
 *
 * Every one checks the session itself. The pages are already gated, but a Server
 * Action is a directly reachable POST endpoint, not a private function the UI
 * happens to call -- and these change credentials.
 */

export type AccountState = {
  error?: string;
  ok?: string;
  /** Shown exactly once, by enableTwoFactorAction. The API hashes them on write,
   *  so this response is the only place the plaintext ever exists. */
  recoveryCodes?: string[];
  setup?: TwoFactorSetup;
};

const SIGNED_OUT = "Your session expired. Please sign in again.";

/** Read the JWT's own expiry so the cookie dies exactly when the token does --
 *  the same helper loginAction uses, kept here to avoid a circular import. */
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

const text = (fd: FormData, key: string) => String(fd.get(key) ?? "").trim();

export async function updateProfileAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  try {
    await updateProfile(token, {
      full_name: text(formData, "full_name"),
      phone: text(formData, "phone") || null,
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  revalidatePath("/account");
  revalidatePath("/", "layout"); // the header shows the name
  return { ok: "Saved." };
}

export async function changePasswordAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  try {
    const fresh = await changePassword(
      token,
      text(formData, "current_password"),
      text(formData, "new_password"),
    );

    // THE critical line in this file. The API rejects every token issued before
    // the change -- including the one this request was made with. Storing the
    // returned token is what keeps this device signed in while every other
    // device stops on its next request. Skip it and the customer changes their
    // password and is instantly logged out, which looks like the feature is
    // broken.
    await setSession(fresh.access_token, tokenExpiry(fresh.access_token));
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  return { ok: "Password changed. Other devices have been signed out." };
}

export async function changeEmailAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  const newEmail = text(formData, "new_email");
  try {
    await changeEmail(token, text(formData, "current_password"), newEmail);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  revalidatePath("/account");
  revalidatePath("/", "layout");
  return {
    ok: `Email changed to ${newEmail}. We told your previous address, in case it wasn't you.`,
  };
}

export async function closeAccountAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  // The API requires the password. This second field is the UI's own guard: one
  // filled box and a click is too little friction for something irreversible.
  if (text(formData, "confirm") !== "DELETE") {
    return { error: 'Type DELETE to confirm.' };
  }

  try {
    await deleteAccount(token, text(formData, "current_password"));
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  // The account is now suspended, so the cookie points at a token the API will
  // refuse. Clearing it is what stops the next page render erroring.
  await clearSession();
  await clearChallenge();
  redirect("/?closed=1");
}

/* ------------------------------------------------------------ two-factor -- */

export async function startTwoFactorAction(
  _prev: AccountState,
  _formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  try {
    return { setup: await twoFactorSetup(token) };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }
}

export async function enableTwoFactorAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  try {
    const { recovery_codes } = await twoFactorEnable(token, text(formData, "code"));
    revalidatePath("/account/security");
    return {
      ok: "Two-factor authentication is on.",
      // Returned through the action state because there is nowhere to fetch
      // them from later -- the API hashes them and never shows them again.
      recoveryCodes: recovery_codes,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }
}

export async function disableTwoFactorAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  try {
    await twoFactorDisable(token, text(formData, "current_password"));
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  revalidatePath("/account/security");
  return { ok: "Two-factor authentication is off." };
}

/* -------------------------------------------------------- password reset -- */

export async function forgotPasswordAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  // No session check: the whole point is that the person cannot sign in.
  try {
    const { detail } = await forgotPassword(text(formData, "email"));
    // The API answers identically for a known address, an unknown one and a
    // suspended account. Passing its sentence straight through is what keeps
    // this page from becoming an account-enumeration oracle.
    return { ok: detail };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }
}

export async function resetPasswordAction(
  _prev: AccountState,
  formData: FormData,
): Promise<AccountState> {
  try {
    await resetPassword(text(formData, "token"), text(formData, "new_password"));
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  // Deliberately no session: the API returns 204 rather than a token, so a link
  // in an inbox never produces a signed-in browser. They sign in next, which
  // also proves the new password is what they think it is.
  redirect("/login?reset=1");
}
