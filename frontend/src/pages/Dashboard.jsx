import { useState } from 'react'
import CompanySelector from '../components/CompanySelector'
import StockChart from '../components/StockChart'

export default function Dashboard() {
  const [stockData, setStockData] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSelect = async (ticker, startDate, endDate) => {
    setLoading(true)
    setError(null)
    setStockData(null)
    setMetrics(null)

    try {
      const [histRes, metricsRes] = await Promise.all([
        fetch(`/api/v1/stocks/${ticker}/history?start=${startDate}&end=${endDate}`),
        fetch(`/api/v1/stocks/${ticker}/metrics?start=${startDate}&end=${endDate}`),
      ])

      if (!histRes.ok) throw new Error(`No data found for ${ticker}`)

      const hist = await histRes.json()
      const met = await metricsRes.json()

      setStockData({ ticker, data: hist.data })
      setMetrics(met)
    } catch (err) {
      setError(err.message)
    }

    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <CompanySelector onSelect={handleSelect} loading={loading} />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">
          {error}
        </div>
      )}

      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <MetricCard label="Start Price" value={`$${metrics.start_price}`} />
          <MetricCard label="End Price" value={`$${metrics.end_price}`} />
          <MetricCard
            label="Total Return"
            value={`${metrics.total_return_pct}%`}
            signed
            number={metrics.total_return_pct}
          />
          <MetricCard
            label={`vs ${metrics.benchmark_comparison?.benchmark ?? 'S&P 500'}`}
            value={`${metrics.benchmark_comparison?.alpha_pct ?? '—'}%`}
            signed
            number={metrics.benchmark_comparison?.alpha_pct}
          />
        </div>
      )}

      {stockData && <StockChart data={stockData.data} ticker={stockData.ticker} />}

      {!stockData && !loading && (
        <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400 text-sm">
          Enter a ticker and date range above to load the stock chart.
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, signed, number }) {
  const color = !signed
    ? 'text-gray-900'
    : number > 0
    ? 'text-green-600'
    : number < 0
    ? 'text-red-600'
    : 'text-gray-900'

  return (
    <div className="bg-white rounded-lg p-4 shadow">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  )
}
