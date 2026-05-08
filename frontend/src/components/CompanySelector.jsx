import { useState } from 'react'

export default function CompanySelector({ onSelect, loading }) {
  const [ticker, setTicker] = useState('')
  const [startDate, setStartDate] = useState('2023-01-01')
  const [endDate, setEndDate] = useState('2024-01-01')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (ticker.trim()) onSelect(ticker.trim().toUpperCase(), startDate, endDate)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap gap-4 items-end bg-white p-4 rounded-lg shadow">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Ticker</label>
        <input
          type="text"
          value={ticker}
          onChange={e => setTicker(e.target.value)}
          placeholder="AAPL"
          maxLength={10}
          className="border rounded px-3 py-2 w-28 uppercase font-mono"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
        <input
          type="date"
          value={startDate}
          onChange={e => setStartDate(e.target.value)}
          className="border rounded px-3 py-2"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
        <input
          type="date"
          value={endDate}
          onChange={e => setEndDate(e.target.value)}
          className="border rounded px-3 py-2"
        />
      </div>
      <button
        type="submit"
        disabled={loading || !ticker.trim()}
        className="bg-blue-600 text-white px-5 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Loading...' : 'Analyze'}
      </button>
    </form>
  )
}
