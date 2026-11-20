// Small inline icon set (stroke icons, currentColor) used across the UI.
type P = { size?: number };
const base = (size = 18) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const SparkIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M12 3l1.8 4.9L19 9.7l-4.6 2.6L12 21l-2.4-8.7L5 9.7l5.2-1.8L12 3z" />
  </svg>
);
export const ChatIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M5 18l-1 3 3.5-1.5A8.5 8.5 0 1 0 5 18z" />
    <path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" strokeWidth={2.6} />
  </svg>
);
export const BoltIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />
  </svg>
);
export const ShieldIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);
export const GaugeIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M4 18a8 8 0 1 1 16 0" />
    <path d="M12 18l4-6" />
  </svg>
);
export const GlobeIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z" />
  </svg>
);
export const FeatherIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M20 4c-6 0-12 4-13 13l-3 3" />
    <path d="M7 17c6 0 10-3 11-9M12 9h5" />
  </svg>
);
export const CodeIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16" />
  </svg>
);
export const ArrowIcon = ({ size }: P) => (
  <svg {...base(size)}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
