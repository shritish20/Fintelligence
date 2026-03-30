import { Routes, Route, Navigate } from 'react-router-dom'
import { SearchPage }       from './pages/SearchPage'
import { CompanyBriefPage } from './pages/CompanyBriefPage'
import { SectorPage }       from './pages/SectorPage'

export function EquityModule() {
  return (
    <div className="max-w-[1800px] mx-auto px-4 py-4">
      <Routes>
        <Route path="/"                  element={<SearchPage />} />
        <Route path="/company/:bseCode"  element={<CompanyBriefPage />} />
        <Route path="/sector"            element={<SectorPage />} />
        <Route path="/sector/:sector"    element={<SectorPage />} />
        <Route path="*"                  element={<Navigate to="/equity" replace />} />
      </Routes>
    </div>
  )
}
