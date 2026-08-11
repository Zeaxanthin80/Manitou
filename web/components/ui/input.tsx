import { cn } from "@/lib/cn";

/**
 * A real <input>, forwarding every prop. `invalid` only styles the control --
 * FormField is what wires aria-invalid and the error message association, so
 * that the visual state and the announced state can never disagree.
 */

export type InputProps = React.ComponentProps<"input"> & { invalid?: boolean };

export function Input({ className, invalid, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "w-full rounded-md border bg-surface px-3 py-2 font-body text-base text-text",
        "placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-50",
        invalid ? "border-error" : "border-border",
        className,
      )}
      {...props}
    />
  );
}
