import { useState } from 'react'

export default function DocumentUpload() {
  const [ticker, setTicker] = useState('')
  const [year, setYear] = useState(new Date().getFullYear())
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleUpload = async (e) => {
    e.preventDefault()
    if (!file || !ticker.trim()) return

    setLoading(true)
    setStatus(null)

    const form = new FormData()
    form.append('file', file)
    form.append('ticker', ticker.toUpperCase())
    form.append('year', year)

    try {
      const res = await fetch('/api/v1/ingest/pdf', { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setStatus({ ok: true, message: `Ingested successfully (document ID: ${data.document_id})` })
      setFile(null)
    } catch (err) {
      setStatus({ ok: false, message: err.message })
    }

    setLoading(false)
  }

  return (
    <div className="bg-white rounded-lg p-4 shadow">
      <h3 className="font-semibold mb-3">Upload 10-K Filing (PDF)</h3>
      <form onSubmit={handleUpload} className="space-y-3">
        <div className="flex gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Ticker</label>
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
            <label className="block text-xs text-gray-500 mb-1">Fiscal Year</label>
            <input
              type="number"
              value={year}
              onChange={e => setYear(e.target.value)}
              min={2000}
              max={2030}
              className="border rounded px-3 py-2 w-24"
            />
          </div>
        </div>

        <input
          type="file"
          accept=".pdf"
          onChange={e => setFile(e.target.files[0])}
          className="w-full text-sm"
        />

        <button
          type="submit"
          disabled={loading || !file || !ticker.trim()}
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {loading ? 'Processing — this may take a minute...' : 'Upload & Process'}
        </button>

        {status && (
          <p className={`text-sm ${status.ok ? 'text-green-600' : 'text-red-600'}`}>
            {status.message}
          </p>
        )}
      </form>
    </div>
  )
}
