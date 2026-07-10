import type { MonitoringSseConnectionState } from '../../monitoring/useMonitoringSse'

interface SystemFooterProps {
  sseConnectionState: MonitoringSseConnectionState
  lastUpdatedAt?: Date
  reasoningEngineVersion?: string
  platformPhase?: string
}

function sseLabel(state: MonitoringSseConnectionState): string {
  switch (state) {
    case 'connected':
      return 'SSE connected'
    case 'connecting':
      return 'SSE connecting'
    default:
      return 'SSE offline'
  }
}

export function SystemFooter({
  sseConnectionState,
  lastUpdatedAt,
  reasoningEngineVersion,
  platformPhase,
}: SystemFooterProps) {
  const metaParts = [
    reasoningEngineVersion ? `Engine ${reasoningEngineVersion}` : undefined,
    platformPhase ? `Phase ${platformPhase}` : undefined,
  ].filter(Boolean)

  return (
    <footer
      className="flex flex-wrap items-center justify-between gap-2 border-t px-6 py-2 text-[10px]"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-raised)',
        color: 'var(--text-muted)',
      }}
    >
      <span>{metaParts.join(' · ') || 'ODIS'}</span>
      <div className="flex items-center gap-3">
        <span>{sseLabel(sseConnectionState)}</span>
        {lastUpdatedAt && (
          <span>
            Last sync{' '}
            {lastUpdatedAt.toLocaleTimeString(undefined, {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </span>
        )}
      </div>
    </footer>
  )
}
