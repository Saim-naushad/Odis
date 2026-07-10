import { useState } from 'react'
import { ActionPlaybook } from '../components/monitoring/ActionPlaybook'
import { ActiveAlertBanner } from '../components/monitoring/ActiveAlertBanner'
import { AssetStatusBar } from '../components/monitoring/AssetStatusBar'
import { ExpertDetailsDrawer } from '../components/monitoring/ExpertDetailsDrawer'
import { FleetAttentionStrip } from '../components/monitoring/FleetAttentionStrip'
import { ProductHeader } from '../components/monitoring/ProductHeader'
import { SystemFooter } from '../components/monitoring/SystemFooter'
import { InvestigationRail } from '../components/monitoring/InvestigationRail'
import { TelemetryVisualizationPanel } from '../components/TelemetryVisualizationPanel'
import { useMonitoringDashboard } from '../hooks/useMonitoringDashboard'
import { useMonitoringSse } from '../monitoring/useMonitoringSse'

export function MonitoringDashboard() {
  const { connectionState } = useMonitoringSse()
  const state = useMonitoringDashboard({ sseConnectionState: connectionState })
  const twin = state.digitalTwin
  const [expertOpen, setExpertOpen] = useState(false)

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ background: 'var(--surface-base)', color: 'var(--text-primary)' }}
    >
      <div className="flex flex-col gap-2">
        <ProductHeader
          platformName={state.platformName}
          platformStatus={state.platformStatus}
          platformErrorMessage={state.platformErrorMessage}
          sseConnectionState={connectionState}
          lastUpdatedAt={state.lastUpdatedAt}
        />
        <FleetAttentionStrip
          assets={state.assets}
          selectedAssetId={state.selectedAssetId}
          selectedDigitalTwin={twin}
          loading={state.assetsLoading || state.digitalTwinLoading}
          error={state.assetsError ?? state.digitalTwinError}
          onSelectAsset={state.setSelectedAssetId}
          onRetry={state.retryAssetList}
        />
      </div>

      <AssetStatusBar
        selectedAssetId={state.selectedAssetId}
        digitalTwin={twin}
        loading={state.digitalTwinLoading}
        error={state.digitalTwinError}
      />

      {twin?.notification && <ActiveAlertBanner notification={twin.notification} />}

      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,65fr)_minmax(0,35fr)]">
        {/* Primary operational workspace */}
        <div className="flex min-w-0 flex-col gap-4">
          <ActionPlaybook
            selectedAssetId={state.selectedAssetId}
            recommendation={twin?.recommendation}
            loading={state.digitalTwinLoading}
            error={state.digitalTwinError}
          />
          <div className="flex-1">
            <TelemetryVisualizationPanel
              assetId={state.selectedAssetId}
              sseConnectionState={connectionState}
            />
          </div>
        </div>

        <InvestigationRail
          events={twin?.timeline_preview ?? []}
          loading={state.digitalTwinLoading}
          error={state.digitalTwinError}
          onRetryTimeline={state.retryTimeline}
          onOpenExpert={() => setExpertOpen(true)}
          expertDisabled={!state.selectedAssetId}
        />
      </main>

      <SystemFooter
        sseConnectionState={connectionState}
        lastUpdatedAt={state.lastUpdatedAt}
        reasoningEngineVersion={state.reasoningEngineVersion}
        platformPhase={state.platformPhase}
      />

      <ExpertDetailsDrawer
        open={expertOpen}
        onClose={() => setExpertOpen(false)}
        state={state}
      />
    </div>
  )
}
