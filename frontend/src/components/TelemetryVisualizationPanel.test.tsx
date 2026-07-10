import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TelemetryVisualizationPanel } from './TelemetryVisualizationPanel'
import { monitoringClient } from '../api/monitoringClient'
import type {
  TelemetryAggregateSeriesResponse,
  TelemetrySeriesResponse,
} from '../types/monitoring'

vi.mock('./TelemetryChart', () => ({
  TelemetryChart: ({
    measurementType,
    unit,
    mode,
    loading,
    error,
    rawData,
    aggregateData,
  }: {
    measurementType?: string
    unit?: string
    mode: 'raw' | 'aggregate'
    loading: boolean
    error?: string
    rawData?: Array<{ value: number }>
    aggregateData?: Array<{ avg_value: number }>
  }) => (
    <div data-testid="telemetry-chart">
      <span>{measurementType}</span>
      <span>{unit}</span>
      <span>{mode}</span>
      <span>{loading ? 'loading' : 'ready'}</span>
      {error ? <span>{error}</span> : null}
      <span>
        points:
        {mode === 'raw'
          ? (rawData?.length ?? 0)
          : (aggregateData?.length ?? 0)}
      </span>
    </div>
  ),
}))

vi.mock('../api/monitoringClient', () => ({
  monitoringClient: {
    getTelemetryHistoryForAsset: vi.fn(),
    getTelemetryAggregatesForAsset: vi.fn(),
  },
}))

const rawSeries: TelemetrySeriesResponse[] = [
  {
    asset_id: 'asset-1',
    measurement_type: 'stack_temperature',
    unit: 'C',
    samples: [
      { timestamp: '2026-01-01T00:00:00Z', value: 65 },
      { timestamp: '2026-01-01T01:00:00Z', value: 66 },
    ],
  },
  {
    asset_id: 'asset-1',
    measurement_type: 'humidity',
    unit: '%',
    samples: [{ timestamp: '2026-01-01T00:00:00Z', value: 40 }],
  },
]

const hourlySeries: TelemetryAggregateSeriesResponse[] = [
  {
    asset_id: 'asset-1',
    measurement_type: 'stack_temperature',
    unit: 'C',
    bucket: '1h',
    samples: [
      {
        timestamp: '2026-01-01T00:00:00Z',
        avg_value: 65,
        min_value: 60,
        max_value: 70,
        sample_count: 6,
      },
    ],
  },
]

function renderPanel(assetId?: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <TelemetryVisualizationPanel assetId={assetId} />
    </QueryClientProvider>,
  )
}

describe('TelemetryVisualizationPanel', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.mocked(monitoringClient.getTelemetryHistoryForAsset).mockReset()
    vi.mocked(monitoringClient.getTelemetryAggregatesForAsset).mockReset()
    vi.mocked(monitoringClient.getTelemetryAggregatesForAsset).mockResolvedValue(
      hourlySeries,
    )
    vi.mocked(monitoringClient.getTelemetryHistoryForAsset).mockResolvedValue(
      rawSeries,
    )
  })

  it('renders raw telemetry after switching to raw resolution', async () => {
    renderPanel('asset-1')

    await waitFor(() => {
      expect(screen.getByTestId('telemetry-chart')).toHaveTextContent('ready')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Raw' }))

    await waitFor(() => {
      expect(monitoringClient.getTelemetryHistoryForAsset).toHaveBeenCalled()
    })

    await waitFor(() => {
      const chart = screen.getByTestId('telemetry-chart')
      expect(chart).toHaveTextContent('raw')
      expect(chart).toHaveTextContent('humidity')
      expect(chart).toHaveTextContent('points:1')
    })
  })

  it('renders aggregate telemetry by default', async () => {
    renderPanel('asset-1')

    await waitFor(() => {
      expect(screen.getByTestId('telemetry-chart')).toHaveTextContent('aggregate')
      expect(screen.getByTestId('telemetry-chart')).toHaveTextContent('points:1')
    })

    expect(monitoringClient.getTelemetryAggregatesForAsset).toHaveBeenCalledWith(
      'asset-1',
      expect.any(AbortSignal),
      expect.objectContaining({ bucket: '1h' }),
    )
  })

  it('changes resolution when the time range changes', async () => {
    renderPanel('asset-1')

    fireEvent.click(screen.getByRole('button', { name: 'Last 30 days' }))

    await waitFor(() => {
      expect(monitoringClient.getTelemetryAggregatesForAsset).toHaveBeenCalledWith(
        'asset-1',
        expect.any(AbortSignal),
        expect.objectContaining({ bucket: '1d' }),
      )
    })
  })

  it('allows measurement selection without mixing units', async () => {
    renderPanel('asset-1')

    fireEvent.click(screen.getByRole('button', { name: 'Raw' }))

    await waitFor(() => {
      expect(screen.getByLabelText('Measurement type')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Measurement type'), {
      target: { value: 'stack_temperature' },
    })

    await waitFor(() => {
      const chart = screen.getByTestId('telemetry-chart')
      expect(chart).toHaveTextContent('stack_temperature')
      expect(chart).toHaveTextContent('C')
      expect(chart).toHaveTextContent('points:2')
    })
  })

  it('shows empty asset prompt when no asset is selected', () => {
    renderPanel()

    expect(
      screen.getByText('Select an asset to view telemetry.'),
    ).toBeInTheDocument()
  })

  it('surfaces API errors', async () => {
    vi.mocked(monitoringClient.getTelemetryAggregatesForAsset).mockRejectedValue(
      new Error('network error'),
    )

    renderPanel('asset-1')

    await waitFor(() => {
      expect(screen.getByTestId('telemetry-chart')).toHaveTextContent(
        'network error',
      )
    })
  })
})
