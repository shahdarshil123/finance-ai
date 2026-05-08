import { useState, useEffect, useRef, useMemo } from 'react'

const STATUS_COLORS = {
  pending:    'text-yellow-500',
  processing: 'text-blue-500',
  completed:  'text-green-500',
  failed:     'text-red-500',
}

const STATUS_DOTS = {
  pending:    'bg-yellow-400',
  processing: 'bg-blue-400 animate-pulse',
  completed:  'bg-green-500',
  failed:     'bg-red-500',
}

export default function DocumentUpload() {
  const [ticker, setTicker]       = useState('')
  const [year, setYear]           = useState(new Date().getFullYear())
  const [loading, setLoading]     = useState(false)
  const [activeId, setActiveId]   = useState(null)
  const [steps, setSteps]         = useState([])
  const [docStatus, setDocStatus] = useState(null)
  const [queue, setQueue]         = useState([])
  const [error, setError]         = useState(null)
  const [viewingId, setViewingId] = useState(null)
  const stepsEndRef               = useRef(null)
  const pollRef                   = useRef(null)

  const stopPolling = () => { clearInterval(pollRef.current); pollRef.current = null }

  useEffect(() => {
    refreshQueue()
    return () => stopPolling()
  }, [])

  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps])

  // Warn if ticker+year already ingested
  const duplicate = useMemo(() => {
    if (!ticker.trim()) return null
    return queue.find(
      d =>
        d.ticker === ticker.toUpperCase() &&
        d.year   === Number(year) &&
        (d.status === 'completed' || d.status === 'processing' || d.status === 'pending')
    )
  }, [ticker, year, queue])

  const refreshQueue = async () => {
    try {
      const res = await fetch('/api/v1/ingest/status')
      if (res.ok) setQueue(await res.json())
    } catch { /* ignore */ }
  }

  const startPolling = (documentId) => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/v1/ingest/progress/${documentId}`)
        if (r.ok) setSteps((await r.json()).steps)
      } catch { /* ignore */ }

      try {
        const r = await fetch('/api/v1/ingest/status')
        if (r.ok) {
          const docs = await r.json()
          setQueue(docs)
          const doc = docs.find(d => d.id === documentId)
          if (doc?.status === 'completed' || doc?.status === 'failed') {
            setDocStatus(doc.status)
            stopPolling()
            // Auto-open viewer when done and file is available
            if (doc.status === 'completed' && doc.has_file) {
              setViewingId(documentId)
            }
          }
        }
      } catch { /* ignore */ }
    }, 1500)
  }

  const handleDownload = async (e) => {
    e.preventDefault()
    if (!ticker.trim() || duplicate) return

    setLoading(true)
    setError(null)
    setSteps([])
    setActiveId(null)
    setDocStatus(null)
    setViewingId(null)

    try {
      const res  = await fetch('/api/v1/ingest/download', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ ticker: ticker.toUpperCase(), year: Number(year) }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')
      setActiveId(data.document_id)
      await refreshQueue()
      startPolling(data.document_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const isProcessing = activeId !== null && docStatus === null
  const viewingDoc   = queue.find(d => d.id === viewingId)

  return (
    <div className="flex gap-6 h-full">

      {/* ── Left panel ── */}
      <div className={`${viewingId ? 'w-80 shrink-0' : 'w-full max-w-xl'} space-y-5 overflow-y-auto`}>

        {/* Download & Ingest form */}
        <div className="bg-white rounded-lg p-5 shadow">
          <h3 className="font-semibold text-gray-800 mb-1">Download & Ingest 10-K</h3>
          <p className="text-xs text-gray-400 mb-4">
            Fetches the filing directly from SEC EDGAR, saves the PDF, and ingests it.
          </p>

          <form onSubmit={handleDownload} className="space-y-4">
            <div className="flex gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Ticker</label>
                <input
                  type="text"
                  value={ticker}
                  onChange={e => setTicker(e.target.value)}
                  placeholder="AAPL"
                  maxLength={10}
                  disabled={loading || isProcessing}
                  className="border rounded px-3 py-2 w-28 uppercase font-mono text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-300"
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
                  disabled={loading || isProcessing}
                  className="border rounded px-3 py-2 w-24 text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              </div>
            </div>

            {/* Duplicate warning */}
            {duplicate && (
              <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-800 flex items-center justify-between">
                <span>
                  <strong>{duplicate.ticker} {duplicate.year}</strong> is already ingested ({duplicate.status}).
                </span>
                {duplicate.has_file && (
                  <button
                    type="button"
                    onClick={() => setViewingId(duplicate.id)}
                    className="ml-3 text-blue-600 hover:underline whitespace-nowrap"
                  >
                    View PDF →
                  </button>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || isProcessing || !ticker.trim() || !!duplicate}
              className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 text-sm flex items-center justify-center gap-2 transition-colors"
            >
              {(loading || isProcessing) && (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
              )}
              {loading ? 'Starting…' : isProcessing ? 'Downloading & Ingesting…' : 'Download & Ingest'}
            </button>

            {error && <p className="text-sm text-red-600">{error}</p>}
          </form>
        </div>

        {/* Terminal-style progress log */}
        {activeId !== null && (
          <div className="bg-gray-900 rounded-lg p-4 shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono text-gray-400 uppercase tracking-widest">
                Processing · Document #{activeId}
              </span>
              {docStatus === 'completed' && <span className="text-xs text-green-400 font-medium">Done</span>}
              {docStatus === 'failed'    && <span className="text-xs text-red-400 font-medium">Failed</span>}
              {!docStatus               && <span className="text-xs text-blue-400 animate-pulse">Running…</span>}
            </div>
            <div className="font-mono text-sm space-y-1 max-h-44 overflow-y-auto">
              {steps.length === 0 && (
                <p className="text-gray-500 animate-pulse">Connecting to SEC EDGAR…</p>
              )}
              {steps.map((step, i) => (
                <p key={i} className={
                  step.startsWith('Failed') ? 'text-red-400' :
                  step === 'Completed.'     ? 'text-green-400' :
                  'text-gray-200'
                }>
                  <span className="text-gray-500 mr-2">›</span>{step}
                </p>
              ))}
              {!docStatus && steps.length > 0 && (
                <p className="text-blue-400 animate-pulse">
                  <span className="text-gray-500 mr-2">›</span>▌
                </p>
              )}
              <div ref={stepsEndRef} />
            </div>
          </div>
        )}

        {/* Ingested documents list */}
        {queue.length > 0 && (
          <div className="bg-white rounded-lg p-5 shadow">
            <h4 className="text-sm font-semibold text-gray-700 mb-3">Ingested Documents</h4>
            <ul className="divide-y divide-gray-100 text-sm">
              {queue.map(doc => (
                <li key={doc.id} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-semibold text-gray-800">{doc.ticker}</span>
                    <span className="text-gray-400">{doc.doc_type} {doc.year}</span>
                    <span className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full inline-block ${STATUS_DOTS[doc.status] ?? 'bg-gray-300'}`} />
                      <span className={`text-xs font-medium ${STATUS_COLORS[doc.status] ?? 'text-gray-500'}`}>
                        {doc.status}
                      </span>
                    </span>
                  </div>
                  {doc.has_file && (
                    <button
                      onClick={() => setViewingId(viewingId === doc.id ? null : doc.id)}
                      className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                        viewingId === doc.id
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'text-blue-600 border-blue-200 hover:bg-blue-50'
                      }`}
                    >
                      {viewingId === doc.id ? 'Close' : 'View PDF'}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {queue.length === 0 && !activeId && (
          <button
            type="button"
            onClick={refreshQueue}
            className="text-xs text-blue-500 hover:underline"
          >
            Load recent documents
          </button>
        )}
      </div>

      {/* ── Right panel: PDF / document viewer ── */}
      {viewingId && (
        <div className="flex-1 min-w-0 bg-white rounded-lg shadow flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b shrink-0">
            <span className="text-sm font-medium text-gray-700">
              {viewingDoc
                ? `${viewingDoc.ticker} · ${viewingDoc.doc_type} ${viewingDoc.year}`
                : 'Document Viewer'}
            </span>
            <div className="flex items-center gap-2">
              <a
                href={`/api/v1/ingest/document/${viewingId}/download`}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V4" />
                </svg>
                Download
              </a>
              <button
                onClick={() => setViewingId(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="Close viewer"
              >
                ×
              </button>
            </div>
          </div>
          <iframe
            key={viewingId}
            src={`/api/v1/ingest/document/${viewingId}`}
            className="flex-1 w-full"
            title="Document Viewer"
          />
        </div>
      )}
    </div>
  )
}
