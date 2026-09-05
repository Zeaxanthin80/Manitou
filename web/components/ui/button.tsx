import { cn } from "@/lib/cn";

/**
 * A real <button>. Never a styled <div> -- the native element brings keyboard
 * operation (Enter and Space), focus order, and the correct screen-reader role
 * for free, and every one of those has to be hand-built otherwise.
 *
 * No 'use client' here: this renders an element and forwards props. A consumer
 * that attaches onClick becomes the client boundary itself, so this component
 * stays usable from Server Components too.
 */

type Variant = "primary" | "accent" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  // Every pairing below is one of the combinations verified in task 2.
  // hover:bg-primary/90, not hover:bg-text: `primary` and `text` are the same
  // hex, so the old hover state changed nothing and nobody noticed for four
  // phases. Ten percent of the surface showing through is a visible answer.
  primary: "bg-primary text-surface hover:bg-primary/90",
  accent: "bg-accent text-surface hover:bg-error",
  ghost: "bg-transparent text-text border border-border hover:bg-background",
  danger: "bg-error text-surface hover:bg-accent",
};

const SIZES: Record<Size, string> = {
  sm: "text-xs px-2 py-1 gap-1",
  md: "text-sm px-4 py-2 gap-2",
  lg: "text-base px-6 py-3 gap-2",
};

export type ButtonProps = React.ComponentProps<"button"> & {
  variant?: Variant;
  size?: Size;
};

/**
 * The button's visual recipe, on its own.
 *
 * For the case where the thing looks like a button but must NOT be one: a
 * control that navigates is a link, and a link has to be an <a> so it can be
 * opened in a new tab, copied, and announced as a link rather than a button.
 * Wrapping a <Link> in a <button> would produce invalid nested-interactive
 * markup; this gives the <Link> the styling instead.
 */
export function buttonClasses({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: Variant;
  size?: Size;
  className?: string;
} = {}) {
  return cn(
    "inline-flex items-center justify-center rounded-md font-body",
    "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    "motion-reduce:transition-none",
    VARIANTS[variant],
    SIZES[size],
    className,
  );
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      // Defaulting to "button" matters: an unspecified type inside a <form> is
      // "submit", so a stray button silently submits the form.
      type={type}
      className={buttonClasses({ variant, size, className })}
      {...props}
    />
  );
}
