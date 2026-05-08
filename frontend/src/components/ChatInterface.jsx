import { useState, useRef, useEffect, useMemo } from 'react'

export default function ChatInterface() {
  const [query, setQuery]   = useState('')
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!query.trim() || loading) return

    const userQuery = query
    setQuery('')
    setEvents([{ type: 'user', content: userQuery }])
    setLoading(true)

    try {
      const response = await fetch('/api/v1/agent/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Server error' }))
        setEvents(prev => [...prev, { type: 'error', content: err.detail || 'Request failed' }])
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const lines = decoder.decode(value).split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          const raw = line.slice(6)
          if (raw === '[DONE]') break
          try {
            const event = JSON.parse(raw)
            setEvents(prev => [...prev, event])
          } catch { /* ignore malformed chunks */ }
        }
      }
    } catch (err) {
      setEvents(prev => [...prev, { type: 'error', content: err.message }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 min-h-0 pr-1">
        {events.length === 0 && !loading && (
          <p className="text-gray-400 text-sm text-center mt-8">
            Ask anything about a company's stock performance or filings.
          </p>
        )}
        {events.map((event, i) => {
          // Collect all filing sources seen so far for the final answer
          const sources = event.type === 'final_answer'
            ? events
                .filter(e => e.type === 'tool_result' && e.tool === 'search_filings')
                .flatMap(e => e.result?.results ?? [])
            : null
          return <EventCard key={i} event={event} sources={sources} />
        })}
        {loading && (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            Agent is thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Did Apple meet its 2023 revenue guidance?"
          disabled={loading}
          className="flex-1 border rounded px-3 py-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </div>
  )
}

function EventCard({ event, sources }) {
  const [expanded, setExpanded] = useState(false)

  if (event.type === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm max-w-[80%]">
          {event.content}
        </div>
      </div>
    )
  }

  if (event.type === 'error') {
    return (
      <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
        <span className="font-medium">Error: </span>{event.content}
      </div>
    )
  }

  if (event.type === 'tool_call') {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm">
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2 w-full text-left"
        >
          <span className="text-yellow-600">⚙</span>
          <span className="text-yellow-700 font-medium">Calling</span>
          <span className="font-mono text-yellow-900">{event.tool}</span>
          <span className="ml-auto text-yellow-400 text-xs">{expanded ? '▲' : '▼'}</span>
        </button>
        {expanded && (
          <pre className="mt-2 text-xs text-gray-600 bg-yellow-100 p-2 rounded overflow-x-auto">
            {JSON.stringify(event.args, null, 2)}
          </pre>
        )}
      </div>
    )
  }

  if (event.type === 'tool_result') {
    const isFilings = event.tool === 'search_filings'
    const results = event.result?.results ?? []
    return (
      <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2 w-full text-left"
        >
          <span className="text-green-600">✓</span>
          <span className="text-green-700 font-medium">Result from</span>
          <span className="font-mono text-green-900">{event.tool}</span>
          {isFilings && (
            <span className="ml-1 text-green-600 text-xs">({results.length} chunks)</span>
          )}
          <span className="ml-auto text-green-400 text-xs">{expanded ? '▲' : '▼'}</span>
        </button>
        {expanded && (
          isFilings ? (
            <div className="mt-2 space-y-2">
              {results.map((r, i) => (
                <div key={i} className="bg-white border border-green-100 rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-xs text-gray-700">{r.ticker}</span>
                    <span className="text-xs text-gray-400">{r.doc_type} · {r.year}</span>
                    <span className="ml-auto text-xs font-mono text-green-700">
                      {(r.similarity * 100).toFixed(1)}% match
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">{r.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <pre className="mt-2 text-xs text-gray-600 bg-green-100 p-2 rounded overflow-x-auto max-h-40">
              {JSON.stringify(event.result, null, 2)}
            </pre>
          )
        )}
      </div>
    )
  }

  if (event.type === 'final_answer') {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm space-y-3">
        <div>
          <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Answer</p>
          <p className="text-gray-800 text-sm whitespace-pre-wrap leading-relaxed">
            {event.content}
          </p>
        </div>
        {sources && sources.length > 0 && (
          <SourcesPanel sources={sources} />
        )}
      </div>
    )
  }

  return null
}

function SourcesPanel({ sources }) {
  const [open, setOpen] = useState(false)
  const unique = useMemo(() => {
    const seen = new Set()
    return sources.filter(s => {
      const key = `${s.ticker}-${s.year}-${s.doc_type}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [sources])

  return (
    <div className="border-t border-gray-100 pt-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-700"
      >
        <span className="font-medium">Sources from ingested PDFs</span>
        <span className="bg-gray-100 text-gray-600 rounded-full px-1.5 py-0.5">{sources.length} chunks</span>
        <span className="ml-auto">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-2 mb-2">
            {unique.map((s, i) => (
              <span key={i} className="bg-blue-50 border border-blue-100 text-blue-700 text-xs rounded px-2 py-0.5">
                {s.ticker} · {s.doc_type} · {s.year}
              </span>
            ))}
          </div>
          {sources.map((s, i) => (
            <div key={i} className="bg-gray-50 border border-gray-100 rounded p-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-semibold text-xs text-gray-700">{s.ticker}</span>
                <span className="text-xs text-gray-400">{s.doc_type} · {s.year}</span>
                <span className="ml-auto text-xs font-mono text-green-700">
                  {(s.similarity * 100).toFixed(1)}% match
                </span>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">{s.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
