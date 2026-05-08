import ChatInterface from '../components/ChatInterface'

export default function Analysis() {
  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-800">Financial Analysis Agent</h2>
        <p className="text-sm text-gray-500 mt-1">
          Ask about stock performance, revenue guidance, risk factors, or anything in the ingested filings.
        </p>
      </div>
      <div className="flex-1 bg-white rounded-lg shadow p-4 min-h-0">
        <ChatInterface />
      </div>
    </div>
  )
}
