/**
 * Inline SVG icons.
 *
 * Inline rather than an icon package or an <img>: no network request, no extra
 * dependency, and -- the reason that matters here -- `stroke="currentColor"`
 * makes every icon inherit whatever token colour its parent already has. An
 * icon font or a coloured asset would be a hardcoded colour by another name,
 * which Section 4.3 forbids.
 *
 * All of them are aria-hidden. An icon that sits inside a control never carries
 * the accessible name -- the control does, via its own text or aria-label.
 * Announcing the icon too would just say everything twice.
 */

type IconProps = { className?: string };

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

export function CartIcon({ className }: IconProps) {
  return (
    // strokeWidth overridden rather than changed in `base`, which every other
    // icon shares. The cart sits in the header at a larger size than the rest,
    // where 1.5 reads heavier than its neighbours.
    <svg {...base} strokeWidth={1} className={className}>
      <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
      <path d="M3 6h18" />
      <path d="M16 10a4 4 0 0 1-8 0" />
    </svg>
  );
}

export function MenuIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 6h18" />
      <path d="M3 12h18" />
      <path d="M3 18h18" />
    </svg>
  );
}

export function CloseIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

/**
 * The pair below follows the convention every browser and password manager
 * already uses: the OPEN eye is what you see while the password is hidden,
 * because it offers the action "reveal". The struck-through eye appears once
 * the password is showing. Reading them as status rather than as an action is
 * the easy way to get this backwards.
 */
export function EyeIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function EyeOffIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      {/* No pupil on this one. At 20px a stroked circle behind the slash turns
          into a smudge; the outline plus the slash stays legible. */}
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <path d="m3 3 18 18" />
    </svg>
  );
}
