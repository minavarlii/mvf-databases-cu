import type { ReactNode } from 'react'

function Icon({ size = 20, className, children }: { size?: number; className?: string; children: ReactNode }) {
  return (
    <svg
      className={className ? `i ${className}` : 'i'}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

interface IconProps {
  size?: number
  className?: string
}

export const DatabaseIcon = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" />
    <path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13" />
    <path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8" />
  </Icon>
)

export const ArrowRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
)

export const ArrowLeftIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </Icon>
)

export const CompareIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4.5" width="7" height="15" rx="2" />
    <rect x="13.5" y="4.5" width="7" height="15" rx="2" />
  </Icon>
)

export const ChatIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 5h12a2.5 2.5 0 0 1 2.5 2.5v7A2.5 2.5 0 0 1 18 17h-7l-4.5 3.5V17H6a2.5 2.5 0 0 1-2.5-2.5v-7A2.5 2.5 0 0 1 6 5z" />
    <path d="M9 10.5h.01M15 10.5h.01" />
    <path d="M10 13.2c1.1.8 2.9.8 4 0" />
  </Icon>
)

export const VectorSearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10.5" cy="10.5" r="6" />
    <path d="M19.5 19.5l-4.5-4.5" />
    <path d="M10.5 7.8v5.4M7.8 10.5h5.4" />
  </Icon>
)

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.2-4.2" />
  </Icon>
)

export const BookIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 6.5c-1.8-1.3-4.3-2-7.5-2v13c3.2 0 5.7.7 7.5 2 1.8-1.3 4.3-2 7.5-2v-13c-3.2 0-5.7.7-7.5 2z" />
    <path d="M12 6.5v13" />
  </Icon>
)

export const SparkleIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M11 3.5l1.9 4.9 4.9 1.9-4.9 1.9L11 17.1l-1.9-4.9-4.9-1.9 4.9-1.9z" />
    <path d="M18.5 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
  </Icon>
)

export const ExternalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14 4.5h5.5V10M19.5 4.5L11 13" />
    <path d="M18 14v3.5a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2H10" />
  </Icon>
)

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Icon>
)

export const CrossIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
  </Icon>
)

export const ServerIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4" width="17" height="7" rx="3" />
    <rect x="3.5" y="13" width="17" height="7" rx="3" />
    <path d="M7.5 7.5h.01M7.5 16.5h.01" />
  </Icon>
)

export const RetryIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
    <path d="M19.5 4.5v4h-4" />
  </Icon>
)

export const CopyIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="8.5" y="8.5" width="11" height="11" rx="2.5" />
    <path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" />
  </Icon>
)

export const ChevronDownIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6.5 9.5l5.5 5.5 5.5-5.5" />
  </Icon>
)

export const WarningIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10.3 4.6L3.4 16.8A2 2 0 0 0 5.1 19.8h13.8a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0z" />
    <path d="M12 9.5v4M12 16.8h.01" />
  </Icon>
)

export const SlidersIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="10" cy="17" r="2" />
  </Icon>
)

export const ChartIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 4v16h16" />
    <path d="M8.5 16v-4M12.5 16V8M16.5 16v-6" />
  </Icon>
)

export const ClockIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
)

export const SpinnerIcon =({ size, className }: IconProps) => (
  <Icon size={size} className={className ? `spin ${className}` : 'spin'}>
    <path d="M12 3a9 9 0 1 1-9 9" />
  </Icon>
)
