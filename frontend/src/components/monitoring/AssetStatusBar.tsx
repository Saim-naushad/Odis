import type { ReactNode } from 'react'
import type { DigitalTwinResponse } from '../../types/monitoring'
import { healthStatusBadgeClass } from '../../utils/healthStatus'
import { riskBadgeClass } from '../../utils/statusBadges'

interface AssetStatusBarProps {
  selectedAssetId?: string
  digitalTwin?: DigitalTwinResponse
  loading: boolean
  error?: string
}

function healthAccentColor(status: string): string {
  switch (status) {
    case 'CRITICAL':
      return 'var(--status-critical)'
    case 'WARNING':
      return 'var(--status-warning)'
    case 'NORMAL':
      return 'var(--status-normal)'
    default:
      return 'var(--status-info)'
  }
}

function healthBarColor(status: string): string {
  return healthAccentColor(status)
}

function MetricCard({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div
      className="rounded border px-4 py-3"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-base)',
      }}
    >
      <p
        className="text-[10px] font-semibold uppercase tracking-wide"
        style={{ color: 'var(--text-muted)' }}
      >
        {label}
      </p>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function StatusSkeleton() {
  return (
    <div className="flex flex-col gap-5 lg:flex-row lg:items-stretch lg:justify-between">
      <div className="min-w-0 flex-1 space-y-3">
        <div
          className="h-7 w-48 rounded"
          style={{ background: 'var(--surface-border)' }}
        />
        <div
          className="h-4 w-64 rounded"
          style={{ background: 'var(--surface-border)', opacity: 0.6 }}
        />
        <div
          className="mt-2 h-16 max-w-xl rounded border p-3"
          style={{ borderColor: 'var(--surface-border)', background: 'var(--surface-base)' }}
        >
          <div
            className="h-3 w-24 rounded"
            style={{ background: 'var(--surface-border)', opacity: 0.5 }}
          />
          <div
            className="mt-2 h-4 w-full rounded"
            style={{ background: 'var(--surface-border)', opacity: 0.4 }}
          />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 lg:w-[22rem]">
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="h-24 rounded border"
            style={{ borderColor: 'var(--surface-border)', background: 'var(--surface-base)' }}
          />
        ))}
      </div>
    </div>
  )
}

export function AssetStatusBar({
  selectedAssetId,
  digitalTwin,
  loading,
  error,
}: AssetStatusBarProps) {
  const operationalState = digitalTwin?.operational_state

  return (
    <section
      className="min-h-[260px] border-b px-6 py-6 lg:px-8"
      style={{
        borderColor: 'var(--surface-border)',
        borderTopWidth: operationalState ? '3px' : undefined,
        borderTopColor: operationalState
          ? healthAccentColor(operationalState.health_status)
          : undefined,
        background: 'var(--surface-raised)',
      }}
      aria-label="Asset status"
    >
      {error ? (
        <p className="text-xs" style={{ color: 'var(--status-warning)' }}>
          {error}
        </p>
      ) : operationalState && digitalTwin ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <h2
                  className="text-2xl font-semibold tracking-tight"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {digitalTwin.asset_name || digitalTwin.asset_id}
                </h2>
                {loading && (
                  <span
                    className="text-[10px] uppercase tracking-wide"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Refreshing…
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
                {digitalTwin.asset_type}
                <span className="mx-2" style={{ color: 'var(--text-muted)' }}>
                  ·
                </span>
                {digitalTwin.location.identifier}
              </p>

              <div
                className="mt-5 max-w-2xl rounded border px-4 py-3"
                style={{
                  borderColor: 'var(--surface-border)',
                  background: 'var(--surface-base)',
                }}
              >
                <p
                  className="text-[10px] font-semibold uppercase tracking-wide"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Primary driver
                </p>
                <p
                  className="mt-2 text-base leading-relaxed"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {operationalState.primary_driver}
                </p>
              </div>
            </div>

            <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-3 lg:w-auto lg:min-w-[22rem]">
              <MetricCard label="Health">
                <div className="flex items-baseline gap-1">
                  <span
                    className="text-4xl font-semibold leading-none tabular-nums"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {operationalState.health_score}
                  </span>
                  <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                    /100
                  </span>
                </div>
                <div
                  className="mt-2 h-2 overflow-hidden rounded-full"
                  style={{ background: 'var(--surface-border)' }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.max(0, Math.min(100, operationalState.health_score))}%`,
                      background: healthBarColor(operationalState.health_status),
                    }}
                  />
                </div>
                <div className="mt-2">
                  <span
                    className={`status-badge ${healthStatusBadgeClass(operationalState.health_status)}`}
                  >
                    {operationalState.health_status}
                  </span>
                </div>
              </MetricCard>

              <MetricCard label="Risk">
                <span
                  className={`status-badge ${riskBadgeClass(operationalState.risk_level)}`}
                >
                  {operationalState.risk_level}
                </span>
                <p className="mt-3 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  Operational risk based on latest reasoning assessment.
                </p>
              </MetricCard>

              <MetricCard label="Confidence">
                <p
                  className="text-3xl font-semibold tabular-nums"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {operationalState.confidence}
                  <span className="text-base" style={{ color: 'var(--text-muted)' }}>
                    %
                  </span>
                </p>
                <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                  Decision confidence
                </p>
              </MetricCard>
            </div>
          </div>

          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            Last assessed{' '}
            {new Date(operationalState.last_updated).toLocaleString()}
          </p>
        </div>
      ) : selectedAssetId ? (
        <StatusSkeleton />
      ) : (
        <StatusSkeleton />
      )}
    </section>
  )
}
