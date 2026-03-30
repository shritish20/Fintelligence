import { Routes, Route, Navigate } from 'react-router-dom'
import { SearchPage }    from './pages/SearchPage'
import { FundBriefPage } from './pages/FundBriefPage'
import { ComparePage }   from './pages/ComparePage'
import { PortfolioPage } from './pages/PortfolioPage'

export function MFModule() {
  return (
    <div className="max-w-[1800px] mx-auto px-4 py-4">
      <Routes>
        <Route path="/"                    element={<SearchPage />} />
        <Route path="/fund/:schemeCode"    element={<FundBriefPage />} />
        <Route path="/compare"             element={<ComparePage />} />
        <Route path="/portfolio"           element={<PortfolioPage />} />
        <Route path="*"                    element={<Navigate to="/mf" replace />} />
      </Routes>
    </div>
  )
}
