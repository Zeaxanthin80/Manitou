"use client";

import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { designTokens as t } from "@/lib/design-tokens";
import { formatMoney } from "@/lib/format";

/**
 * The card step.
 *
 * The only file in the app that talks to Stripe.js, and the only one that needs
 * to: everything else reaches Stripe through FastAPI.
 *
 * **The card number never enters this page.** <PaymentElement/> renders an
 * iframe served by js.stripe.com, and same-origin policy means nothing here can
 * read across that boundary -- not the value, not the keystrokes. A compromised
 * dependency running in this bundle still cannot see a card. That is the whole
 * reason for using Stripe's element rather than an <input> of our own: the
 * moment those digits are in our DOM they are in our logs, our error reports
 * and our PCI scope.
 *
 * The client secret arrives as a prop from a Server Component, so the browser
 * still never calls FastAPI directly -- the JWT stays in an httpOnly cookie it
 * cannot read. A client secret is safe to hand over because it authorises
 * exactly one payment: whoever holds it can pay THIS order and nothing else.
 */

/**
 * Called once at module scope, not per render.
 *
 * loadStripe injects Stripe.js and returns a promise. Calling it inside the
 * component would start a fresh download on every mount and hand <Elements/> a
 * new promise identity each render, which remounts the iframe and throws away
 * whatever the customer had typed.
 *
 * The publishable key is NEXT_PUBLIC_ on purpose -- it is inlined into the
 * browser bundle, which is exactly where it is meant to be. It can only start a
 * payment the secret key already authorised. The secret key must never carry
 * this prefix.
 */
const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "",
);

/**
 * Stripe's appearance API, driven from design-tokens.json.
 *
 * The element is in an iframe, so no Tailwind class and no CSS custom property
 * of ours reaches it. Stripe takes literal values instead -- which is why
 * build-tokens.mjs emits lib/design-tokens.ts alongside app/tokens.css. Typing
 * the hex here would be the one thing Section 4.3 forbids outright.
 *
 * colorDanger is color.error rather than color.accent, deliberately:
 * design-tokens.json calls out that the two reds are different so a Sale badge
 * and a declined card can never look alike.
 */
/** One source for the stack, used by both `variables` and `rules` below. */
const BODY_FONT = t.typography.fontFamily.body.join(", ");

const appearance = {
  theme: "stripe" as const,
  variables: {
    colorPrimary: t.color.primary,
    colorBackground: t.color.surface,
    colorText: t.color.text,
    colorTextSecondary: t.color.muted,
    colorDanger: t.color.error,
    fontFamily: BODY_FONT,
    fontSizeBase: t.typography.fontSize.base.size,
    borderRadius: t.radius.md,
    spacingUnit: t.spacing["1"],
  },
  rules: {
    ".Input:focus": {
      outline: `${t.focus.width} solid ${t.focus.color}`,
      outlineOffset: t.focus.offset,
    },

    /**
     * fontFamily again, per component.
     *
     * `variables.fontFamily` above is a theme-level hint that Stripe applies
     * selectively, and MEASURED it was not reaching the text: the browser loaded
     * inter.css and then never requested inter-latin.woff2 -- not a failed
     * request, no request at all. Fonts download lazily, only when a glyph
     * actually needs the face, so "the @font-face arrived and nothing used it"
     * is exactly that signature.
     *
     * Rules target components directly, so these are the elements that actually
     * render text in the card form.
     */
    ".Label": { fontFamily: BODY_FONT },
    ".Input": { fontFamily: BODY_FONT, borderColor: t.color.border },
    ".Tab": { fontFamily: BODY_FONT },
    ".TabLabel": { fontFamily: BODY_FONT },
    ".AccordionItem": { fontFamily: BODY_FONT },
    ".Error": { fontFamily: BODY_FONT },
  },
};

/**
 * Real Inter inside the iframe.
 *
 * **The bug.** `appearance.variables.fontFamily` was set to
 * "Inter, system-ui, sans-serif" and silently did nothing. next/font SELF-HOSTS
 * Inter under a generated family name and declares its @font-face in OUR
 * document; the Elements iframe is a different document and cannot see it. No
 * font called "Inter" existed in there, so it fell through to system-ui and the
 * payment step rendered in a different typeface from every other page.
 *
 * Same shape as the failure build-tokens.mjs documents for @theme vs
 * @theme inline: a font name that resolves in one scope and not another, failing
 * by quietly rendering a fallback rather than by erroring.
 *
 * **Why Google Fonts, against layout.tsx's rule.** Self-hosting was tried first
 * and measured, twice: a CustomFontSource pointing straight at
 * /public/fonts/inter-latin.woff2, then a cssSrc pointing at our own stylesheet
 * with the CORS header to match. In both cases the browser fetched the
 * STYLESHEET and never requested the font -- not a 404, not a CORS rejection,
 * NO REQUEST AT ALL, which is the signature of something refusing the source
 * before a request is made. Switching this one line to fonts.googleapis.com made
 * the woff2 arrive immediately (200, font, 48.5 kB).
 *
 * **The cause is not settled, and that matters for Phase 6.** Two explanations
 * fit equally: Stripe's iframe allowlisting font sources, or plain mixed
 * content -- dev runs on http://localhost:3000 while the iframe is https, and
 * browsers block http subresources in an https document silently. If it is the
 * second, self-hosting will work once Phase 6 serves HTTPS, and this line should
 * go back to our own origin. If the first, it never will. Untestable until there
 * is an HTTPS origin to try.
 *
 * So this knowingly breaks layout.tsx's "the browser makes no request to Google"
 * for exactly one iframe on one screen, as the only thing measured to work --
 * not as a default. Retest in Phase 6.
 */
const fonts = [
  {
    cssSrc:
      "https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap",
  },
];

/**
 * How the methods are listed.
 *
 * `auto` -- the default, and what this shipped with -- collapses to a single
 * card form when there are few methods, and folds Link in as an email field
 * INSIDE that form. Reasonable for a checkout that is only ever cards, and
 * confusing here: the field looks like part of entering a card, when it is
 * actually a separate way to pay.
 *
 * `accordion` gives every method its own labelled row, so Card and Link read as
 * the alternatives they are -- the same shape a shopper sees when a store
 * offers bank transfer or Klarna.
 *
 * paymentMethodOrder puts Card first deliberately. Link only helps someone who
 * already has a Link account; everyone else needs the card row, and a first-time
 * customer should not have to work past an option that does not apply to them.
 * Unrecognised or unavailable names in this list are ignored rather than erroring,
 * so it stays valid if the enabled methods change.
 */
const paymentElementOptions = {
  layout: {
    type: "accordion" as const,
    // Card is open on arrival; no extra click for the common case.
    defaultCollapsed: false,
    // Each row visually separate, so they do not read as one form.
    spacedAccordionItems: true,
  },
  paymentMethodOrder: ["card", "link"],

  /**
   * Card only, decided deliberately.
   *
   * Link's prompt used to sit INSIDE the card row -- a "Secure, fast checkout
   * with Link" strip between the Card heading and the card number, reading as
   * part of entering a card rather than as a different way to pay.
   *
   * Link also BROKERED the other two rows. Bank and Klarna both appeared
   * labelled "Powered by Link", which is also why allow_redirects: "never" never
   * filtered Klarna out -- the intent's payment_method_types are
   * ['card', 'link'], so Klarna arrived as `link` and the redirect rule did not
   * apply to it. Measured in the browser: switching this to "never" removed all
   * three together. There is no setting that keeps those rows without the strip.
   *
   * The trade was taken knowingly. For a single-vendor T-shirt store with
   * baskets in the $20-60 range, Klarna's fee is well above card and instalments
   * on a tee finance nothing anyone needs financed. Reversing this is one line,
   * and offering Klarna as a real method (its own row, no Link) means enabling
   * it in the dashboard and moving allow_redirects to "always" -- which makes
   * return_url load-bearing and sends the customer off-site and back.
   */
  wallets: { link: "never" as const },
};

export function PaymentForm({
  clientSecret,
  orderId,
  amount,
}: {
  clientSecret: string;
  orderId: number;
  amount: string;
}) {
  return (
    <Elements
      stripe={stripePromise}
      options={{ clientSecret, appearance, fonts }}
    >
      <CardStep orderId={orderId} amount={amount} />
    </Elements>
  );
}

/**
 * Split from the wrapper because useStripe/useElements only work INSIDE
 * <Elements/>. A single component calling them beside the provider it renders
 * gets null every time.
 */
function CardStep({ orderId, amount }: { orderId: number; amount: string }) {
  const stripe = useStripe();
  const elements = useElements();
  const router = useRouter();

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Null until Stripe.js has finished loading. Submitting before then would
    // silently do nothing, so the button stays disabled instead.
    if (!stripe || !elements) return;

    setBusy(true);
    setError(null);

    const { error: stripeError } = await stripe.confirmPayment({
      elements,
      // The intent was created with allow_redirects: "never", so no
      // redirect-based method is offered. "if_required" keeps the customer on
      // this page for cards while still allowing Stripe's 3-D Secure modal,
      // which is not a redirect.
      redirect: "if_required",
      confirmParams: {
        // Unused on the card path, but Stripe requires it whenever a method
        // COULD redirect. Points at the receipt so the fallback lands somewhere
        // sensible rather than 404ing.
        return_url: `${window.location.origin}/orders/${orderId}`,
      },
    });

    if (stripeError) {
      // card_error and validation_error carry messages written for shoppers --
      // "Your card was declined", "Your card number is incomplete". Every other
      // type is written for developers and may name internals, so it gets a
      // generic line instead.
      setError(
        stripeError.type === "card_error" ||
          stripeError.type === "validation_error"
          ? (stripeError.message ?? "That payment could not be completed.")
          : "Something went wrong taking payment. Nothing has been charged.",
      );
      setBusy(false);
      return;
    }

    // Payment succeeded at Stripe. The ORDER is still `pending` until the task 4
    // webhook says otherwise -- deliberately, because only Stripe can confirm
    // money moved and the browser is the one party with a reason to lie about
    // it. The receipt reads payment_status and acknowledges the card there.
    //
    // refresh() before push() so the receipt renders with the payment already
    // visible rather than showing a stale "awaiting payment" for a beat.
    router.refresh();
    router.push(`/orders/${orderId}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <PaymentElement options={paymentElementOptions} />

      {error && (
        <p role="alert" className="font-body text-sm text-error">
          {error}
        </p>
      )}

      <Button type="submit" size="lg" disabled={!stripe || busy}>
        {busy ? "Paying..." : `Pay ${formatMoney(amount)}`}
      </Button>

    </form>
  );
}
