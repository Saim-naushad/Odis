import type { ReactNode } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TelemetryChart } from './TelemetryChart'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="responsive-chart">{children}</div>
  ),
  LineChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Line: () => <div data-testid="line" />,
}))

describe('TelemetryChart', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders raw telemetry chart with measurement and unit labels', () => {
    render(
      <TelemetryChart
        mode="raw"
        measurementType="stack_temperature"
        unit="C"
        resolution="raw"
        rawData={[
          {
            timestamp: '2026-01-01T00:00:00Z',
            value: 65,
            label: 'Jan 1, 12:00:00 AM',
          },
        ]}
        loading={false}
      />,
    )

    expect(screen.getByText('stack_temperature (C)')).toBeInTheDocument()
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Showing raw samples from GET /monitoring/assets/{id}/telemetry.',
      ),
    ).toBeInTheDocument()
  })

  it('renders aggregate chart and API hint', () => {
    render(
      <TelemetryChart
        mode="aggregate"
        measurementType="stack_temperature"
        unit="C"
        resolution="hourly"
        aggregateData={[
          {
            timestamp: '2026-01-01T01:00:00Z',
            avg_value: 68,
            min_value: 60,
            max_value: 72,
            sample_count: 12,
            label: 'Jan 1, 1:00 AM',
          },
        ]}
        loading={false}
      />,
    )

    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Showing hourly aggregates from GET /monitoring/assets/{id}/telemetry/aggregate.',
      ),
    ).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(
      <TelemetryChart
        mode="raw"
        resolution="raw"
        loading={true}
      />,
    )

    expect(screen.getByText('Loading telemetry chart…')).toBeInTheDocument()
  })

  it('shows empty state', () => {
    render(
      <TelemetryChart
        mode="raw"
        resolution="raw"
        rawData={[]}
        loading={false}
      />,
    )

    expect(
      screen.getByText(
        'No telemetry data for the selected measurement and time range.',
      ),
    ).toBeInTheDocument()
  })

  it('shows API error state with retry', () => {
    const onRetry = vi.fn()

    render(
      <TelemetryChart
        mode="raw"
        resolution="raw"
        loading={false}
        error="Initial load failed: network error"
        onRetry={onRetry}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('network error')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
