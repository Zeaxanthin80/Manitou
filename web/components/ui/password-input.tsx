"use client";

import { useState } from "react";

import { EyeIcon, EyeOffIcon } from "@/components/ui/icons";
import { Input, type InputProps } from "@/components/ui/input";
import { cn } from "@/lib/cn";

/**
 * A password field with a show/hide toggle.
 *
 * There is no "reveal" attribute in HTML -- the whole mechanism is swapping
 * `type` between "password" and "text" on the same input. Because that is one
 * piece of state, this has to be a Client Component, which is exactly why it is
 * NOT folded into Input. Input forwards props and renders an element; keeping it
 * that way leaves it usable from a Server Component. Same split as Button and
 * buttonClasses.
 *
 * Why offer this at all: hiding a password protects against someone reading the
 * screen, which is a real threat in a cafe and not a threat at all on a phone in
 * your own kitchen. Typing a password blind is the reason people pick shorter,
 * simpler ones and the reason "incorrect password" is so often just a typo. The
 * user is the one who knows who can see their screen, so the choice is theirs --
 * hidden by default, revealed only on a deliberate press.
 */

/** `type` is omitted deliberately: this component owns it. */
export type PasswordInputProps = Omit<InputProps, "type">;

export function PasswordInput({ className, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    // `relative` so the button can be positioned over the input's right end.
    // The wrapper carries no id or aria wiring -- everything FormField hands
    // down still lands on the <input> itself, so the label, the hint and the
    // error association are untouched.
    <div className="relative">
      <Input
        {...props}
        type={visible ? "text" : "password"}
        // Room for the button, so a long password never runs underneath it.
        // 44px of padding against a 44px-wide button.
        className={cn("pr-11", className)}
      />
      <button
        // Load-bearing. A button inside a <form> with no type is a SUBMIT
        // button, so without this, revealing your password would submit the
        // sign-in form instead.
        type="button"
        onClick={() => setVisible((v) => !v)}
        // Follows the input when the form disables its fields, rather than
        // leaving a live control attached to a dead one.
        disabled={props.disabled}
        // The label names the ACTION, and so it changes with the state. Pairing
        // a changing label with aria-pressed would announce "Hide password,
        // pressed", which says the same thing twice and in two directions.
        aria-label={visible ? "Hide password" : "Show password"}
        className={cn(
          "absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md",
          "text-muted transition-colors hover:text-text motion-reduce:transition-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        {visible ? (
          <EyeOffIcon className="size-5" />
        ) : (
          <EyeIcon className="size-5" />
        )}
      </button>

      {/* Whether a screen reader announces an aria-label that changes on the
          element you just activated is genuinely inconsistent between readers.
          A live region is the reliable way to confirm the state actually
          flipped. It says the STATE, where the button says the action, so the
          two do not read as a contradiction. Content present at first render is
          not announced, so this is silent until something changes. */}
      <p role="status" className="sr-only">
        {visible ? "Password is visible" : "Password is hidden"}
      </p>
    </div>
  );
}
