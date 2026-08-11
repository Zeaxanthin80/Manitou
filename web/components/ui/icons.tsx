/**
 * Inline SVG icons.
 *
 * Inline rather than an icon package or an <img>: no network request, no extra
 * dependency, and -- the reason that matters here -- `stroke="currentColor"`
 * makes every icon inherit whatever token colour its parent already has. An
 * icon font or a coloured asset would be a hardcoded colour by another name,
 * which Section 4.3 forbids.
 *
 * All three are aria-hidden. An icon that sits inside a control never carries
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
    <svg {...base} className={className}>
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
