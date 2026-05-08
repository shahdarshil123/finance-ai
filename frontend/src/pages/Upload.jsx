import DocumentUpload from '../components/DocumentUpload'

export default function Upload() {
  return (
    <div className="h-full flex flex-col">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-800">Upload 10-K Filings</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload PDF filings to ingest them into the vector database for AI analysis.
        </p>
      </div>
      <div className="flex-1 min-h-0">
        <DocumentUpload />
      </div>
    </div>
  )
}
