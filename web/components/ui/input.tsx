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
        // `subtle`, not `muted`: muted is body-text contrast (7.6:1), so a sample
        // value read as something already typed. A placeholder should be seen
        // and then ignored -- 3.4:1 is the line for that.
        "placeholder:text-subtle disabled:cursor-not-allowed disabled:opacity-50",
        invalid ? "border-error" : "border-border",
        className,
      )}
      {...props}
    />
  );
}
