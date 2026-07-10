interface TelemetryEmptyStateProps {
  variant: 'no-asset' | 'no-data' | 'loading'
}

function GhostChart() {
  return (
    <svg
      viewBox="0 0 320 120"
      className="mx-auto h-28 w-full max-w-md opacity-40"
      aria-hidden="true"
    >
      <line x1="24" y1="100" x2="296" y2="100" stroke="var(--text-muted)" strokeWidth="1" />
      <line x1="24" y1="20" x2="24" y2="100" stroke="var(--text-muted)" strokeWidth="1" />
      <polyline
        points="24,80 72,65 120,72 168,48 216,55 264,32 296,40"
        fill="none"
        stroke="var(--text-secondary)"
        strokeWidth="2"
        strokeDasharray="4 4"
      />
      <circle cx="264" cy="32" r="3" fill="var(--text-secondary)" />
    </svg>
  )
}

export function TelemetryEmptyState({ variant }: TelemetryEmptyStateProps) {
  const title =
    variant === 'loading'
      ? 'Loading telemetry'
      : variant === 'no-data'
        ? 'No measurements in range'
        : 'Telemetry trends'

  const description =
    variant === 'loading'
      ? 'Fetching measurement history for the selected asset…'
      : variant === 'no-data'
        ? 'Try a wider time range or a different measurement type.'
        : 'Select an asset to view live measurement history, correlate trends with timeline events, and investigate operational changes.'

  return (
    <div
      className="flex min-h-[280px] flex-1 flex-col items-center justify-center rounded border px-6 py-10 text-center"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-base)',
      }}
      role="status"
    >
      <GhostChart />

      <p
        className="mt-6 text-sm font-medium"
        style={{ color: 'var(--text-primary)' }}
      >
        {title}
      </p>
      <p
        className="mt-2 max-w-sm text-xs leading-relaxed"
        style={{ color: 'var(--text-secondary)' }}
      >
        {description}
      </p>

      {variant === 'no-asset' && (
        <div
          className="mt-6 flex flex-wrap justify-center gap-2 text-[10px] uppercase tracking-wide"
          style={{ color: 'var(--text-muted)' }}
        >
          <span className="rounded border px-2 py-1" style={{ borderColor: 'var(--surface-border)' }}>
            Time range
          </span>
          <span className="rounded border px-2 py-1" style={{ borderColor: 'var(--surface-border)' }}>
            Resolution
          </span>
          <span className="rounded border px-2 py-1" style={{ borderColor: 'var(--surface-border)' }}>
            Measurement
          </span>
        </div>
      )}
    </div>
  )
}
