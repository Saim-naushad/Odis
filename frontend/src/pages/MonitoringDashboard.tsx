import { Header } from '../components/Header'
import { AssetList } from '../components/AssetList'
import { AssetDetails } from '../components/AssetDetails'
import { ReasoningTrace } from '../components/ReasoningTrace'
import { RunHistory } from '../components/RunHistory'
import { Timeline } from '../components/Timeline'
import { useMonitoringDashboard } from '../hooks/useMonitoringDashboard'
import { useMonitoringSse } from '../monitoring/useMonitoringSse'

export function MonitoringDashboard() {
  const { connectionState } = useMonitoringSse()
  const state = useMonitoringDashboard({ sseConnectionState: connectionState })

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-50">
      <Header state={state} />
      <main className="flex flex-1 flex-col gap-4 p-4">
        <section className="grid flex-1 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,1.3fr)]">
          <div className="flex flex-col">
            <AssetList
              assets={state.assets}
              selectedAssetId={state.selectedAssetId}
              onSelectAsset={state.setSelectedAssetId}
              selectedRunId={state.selectedRunId}
              latest={state.latestForAsset}
              history={state.history}
              loading={state.assetsLoading || state.latestLoading}
              error={state.assetsError ?? state.latestError ?? state.historyError}
              onRetry={state.retryAssetList}
            />
          </div>
          <div className="flex flex-col">
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
          <div className="flex flex-col gap-4">
            <ReasoningTrace
              trace={state.runDetails?.reasoning_trace}
              loading={state.runDetailsLoading}
              error={state.runDetailsError}
              onRetry={state.retryReasoningTrace}
            />
            <RunHistory
              history={state.history}
              selectedRunId={state.selectedRunId}
              onSelectRun={state.setSelectedRunId}
              loading={state.historyLoading}
              error={state.historyError}
              onRetry={state.retryRunHistory}
            />
            <Timeline
              events={state.timeline}
              loading={state.timelineLoading}
              error={state.timelineError}
              onRetry={state.retryTimeline}
            />
          </div>
        </section>
      </main>
    </div>
  )
}
