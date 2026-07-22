import { useEffect } from 'react'
import { AssetDetails } from '../AssetDetails'
import { FaultInvestigationHistoryPanel } from './FaultInvestigationHistoryPanel'
import { ReasoningTrace } from '../ReasoningTrace'
import { RunHistory } from '../RunHistory'
import type { useMonitoringDashboard } from '../../hooks/useMonitoringDashboard'
import type { FaultInvestigationState } from '../../hooks/useFaultInvestigation'

interface ExpertDetailsDrawerProps {
  open: boolean
  onClose: () => void
  state: ReturnType<typeof useMonitoringDashboard>
  faultInvestigation: FaultInvestigationState
}

export function ExpertDetailsDrawer({
  open,
  onClose,
  state,
  faultInvestigation,
}: ExpertDetailsDrawerProps) {
  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Expert details">
      <div
        className="absolute inset-0"
        style={{ background: 'rgb(2 6 23 / 0.7)' }}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className="absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l shadow-xl"
        style={{
          borderColor: 'var(--surface-border)',
          background: 'var(--surface-base)',
        }}
      >
        <header
          className="flex items-center justify-between border-b px-4 py-3"
          style={{ borderColor: 'var(--surface-border)' }}
        >
          <div>
            <h2
              className="text-sm font-semibold"
              style={{ color: 'var(--text-primary)' }}
            >
              Expert details
            </h2>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Reasoning runs and diagnostics
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-2 py-1 text-xs transition-colors hover:opacity-80"
            style={{
              borderColor: 'var(--surface-border)',
              color: 'var(--text-secondary)',
            }}
          >
            Close
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <FaultInvestigationHistoryPanel
            history={faultInvestigation.history}
            loading={faultInvestigation.historyLoading}
            error={faultInvestigation.historyError}
            onRetry={() => void faultInvestigation.retryHistory()}
          />
          <RunHistory
            history={state.history}
            selectedRunId={state.selectedRunId}
            onSelectRun={state.setSelectedRunId}
            loading={state.historyLoading}
            error={state.historyError}
            onRetry={state.retryRunHistory}
          />
          <ReasoningTrace
            trace={state.runDetails?.reasoning_trace}
            loading={state.runDetailsLoading}
            error={state.runDetailsError}
            onRetry={state.retryReasoningTrace}
          />
          <AssetDetails
            latest={state.latestForAsset}
            runDetails={state.runDetails}
            loading={
              state.latestLoading ||
              state.runDetailsLoading ||
              state.historyLoading
            }
            error={
              state.latestError ??
              state.runDetailsError ??
              state.historyError
            }
            onRetry={state.retryAssetDetails}
          />
        </div>
      </aside>
    </div>
  )
}
