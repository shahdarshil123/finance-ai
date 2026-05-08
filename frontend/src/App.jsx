import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import Analysis from './pages/Analysis'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'

export default function App() {
  const navClass = ({ isActive }) =>
    isActive
      ? 'text-blue-600 font-semibold border-b-2 border-blue-600 pb-1'
      : 'text-gray-500 hover:text-blue-600 pb-1'

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100">
        <nav className="bg-white shadow-sm px-6 py-4 flex items-center gap-8">
          <span className="font-bold text-blue-600 text-lg tracking-tight">FinanceAI</span>
          <NavLink to="/" end className={navClass}>Dashboard</NavLink>
          <NavLink to="/upload" className={navClass}>Upload</NavLink>
          <NavLink to="/analysis" className={navClass}>Analysis</NavLink>
        </nav>
        <main className="max-w-6xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/analysis" element={<Analysis />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
