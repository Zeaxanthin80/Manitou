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
  primary: "bg-primary text-surface hover:bg-text",
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
      className={cn(
        "inline-flex items-center justify-center rounded-md font-body",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        "motion-reduce:transition-none",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
}
