import type { MonitoringSseConnectionState } from '../../monitoring/useMonitoringSse'

interface ProductHeaderProps {
  platformName?: string
  platformStatus: 'unknown' | 'ok' | 'degraded' | 'error'
  platformErrorMessage?: string
  sseConnectionState: MonitoringSseConnectionState
  lastUpdatedAt?: Date
}

function sseDotClass(state: MonitoringSseConnectionState): string {
  switch (state) {
    case 'connected':
      return 'status-dot-normal'
    case 'connecting':
      return 'status-dot-warning'
    default:
      return 'status-dot-muted'
  }
}

function sseLabel(state: MonitoringSseConnectionState): string {
  switch (state) {
    case 'connected':
      return 'Live'
    case 'connecting':
      return 'Connecting'
    case 'disconnected':
      return 'Offline'
  }
}

export function ProductHeader({
  platformName,
  platformStatus,
  platformErrorMessage,
  sseConnectionState,
  lastUpdatedAt,
}: ProductHeaderProps) {
  const platformLabel =
    platformStatus === 'ok'
      ? 'Platform healthy'
      : platformStatus === 'degraded'
        ? 'Platform degraded (non-critical dependency)'
        : platformStatus === 'error'
          ? 'Platform unavailable'
          : 'Platform unknown'

  const platformLabelColor =
    platformStatus === 'error' ? 'var(--status-warning)' : 'var(--text-muted)'

  const showPlatformSecondary = platformStatus !== 'ok'

  return (
    <header
      className="border-b px-6 py-4"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-raised)',
      }}
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1
            className="text-lg font-semibold tracking-tight"
            style={{ color: 'var(--text-primary)' }}
          >
            ODIS
          </h1>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {platformName ?? 'Industrial operational intelligence'}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div
            className="flex items-center gap-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <span
              className={`inline-flex h-2.5 w-2.5 rounded-full ${sseDotClass(sseConnectionState)}`}
              aria-hidden="true"
            />
            <span className="text-sm font-medium uppercase tracking-wide">
              {sseLabel(sseConnectionState)}
            </span>
          </div>

          {showPlatformSecondary && (
            <span style={{ color: platformLabelColor }}>{platformLabel}</span>
          )}

          {lastUpdatedAt && (
            <span style={{ color: 'var(--text-muted)' }}>
              Updated{' '}
              {lastUpdatedAt.toLocaleTimeString(undefined, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </span>
          )}
        </div>
      </div>

      {platformErrorMessage && (
        <p className="mt-2 text-xs" style={{ color: 'var(--status-warning)' }}>
          {platformErrorMessage}
        </p>
      )}
    </header>
  )
}
