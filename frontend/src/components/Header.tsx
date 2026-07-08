import type { MonitoringDashboardState } from '../hooks/useMonitoringDashboard'

interface HeaderProps {
  state: MonitoringDashboardState
}

export function Header({ state }: HeaderProps) {
  const {
    platformStatus,
    platformName,
    reasoningEngineVersion,
    platformPhase,
    lastUpdatedAt,
    platformErrorMessage,
  } = state

  const statusColor =
    platformStatus === 'ok'
      ? 'bg-emerald-500'
      : platformStatus === 'error'
        ? 'bg-red-500'
        : 'bg-slate-500'

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 px-6 py-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-50">
            ODIS Monitoring Console
          </h1>
          <p className="text-xs text-slate-400">
            {platformName ?? 'Industrial operational intelligence platform'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex h-2 w-2 rounded-full ${statusColor}`}
            />
            <span className="uppercase tracking-wide">
              {platformStatus === 'ok'
                ? 'Platform: Healthy'
                : platformStatus === 'error'
                  ? 'Platform: Degraded'
                  : 'Platform: Unknown'}
            </span>
          </div>
          {reasoningEngineVersion && (
            <span className="border-l border-slate-700 pl-4">
              Engine {reasoningEngineVersion}
            </span>
          )}
          {platformPhase && (
            <span className="border-l border-slate-700 pl-4">
              Phase {platformPhase}
            </span>
          )}
          {lastUpdatedAt && (
            <span className="border-l border-slate-700 pl-4 text-slate-400">
              Last update:{' '}
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
        <p className="mt-2 text-xs text-amber-400">
          {platformErrorMessage}
        </p>
      )}
    </header>
  )
}

