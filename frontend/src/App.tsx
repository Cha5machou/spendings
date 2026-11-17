import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import TransactionsPage from './pages/TransactionsPage'
import DocumentsPage from './pages/DocumentsPage'
import AccountsPage from './pages/AccountsPage'
import CategoriesPage from './pages/CategoriesPage'
import InsightsPage from './pages/InsightsPage'
import LoansPage from './pages/LoansPage'
import RentalPage from './pages/RentalPage'
import WealthPage from './pages/WealthPage'
import IncomePage from './pages/IncomePage'
import GoalsPage from './pages/GoalsPage'
import AskPage from './pages/AskPage'
import StartPage from './pages/StartPage'
import { AuthGate, useAuth } from './auth'
import { api } from './api'
import { useLoad } from './hooks'

// The order is the order a newcomer should follow: each step feeds the analyses.
const SETUP = [
  { to: '/accounts', label: 'Accounts', step: 'accounts' },
  { to: '/income', label: 'Payslips', step: 'payslips' },
  { to: '/loans', label: 'Credits & loans', step: 'loans' },
  { to: '/rental', label: 'Rental property', step: 'property' },
  { to: '/documents', label: 'Bank statements', step: 'documents' },
  { to: '/transactions', label: 'Transactions', step: 'transactions' },
  { to: '/plan', label: 'Goals', step: 'goals' },
]
const ANALYSE = [
  { to: '/', label: 'Dashboard' },
  { to: '/insights', label: 'Analysis' },
  { to: '/wealth', label: 'Savings & net worth' },
  { to: '/ask', label: 'Ask' },
]

function UserBadge() {
  const { enabled, email, signOut } = useAuth()
  if (!enabled) return null
  return (
    <div className="small muted" style={{ padding: '16px 10px 0' }}>
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{email}</div>
      <button className="small" style={{ marginTop: 4 }} onClick={signOut}>Sign out</button>
    </div>
  )
}

function Sidebar() {
  const { pathname } = useLocation()
  const setup = useLoad(() => api.setup.get(), [pathname])
  const stepDone = new Map((setup.data?.steps ?? []).map((step) => [step.key, step.done]))
  const className = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  return (
    <aside className="sidebar">
      <div className="brand">Spendings</div>
      <nav>
        <NavLink to="/start" className={className}>Get started</NavLink>
        <div className="nav-section">1 · Set up</div>
        {SETUP.map((item, index) => (
          <NavLink key={item.to} to={item.to} className={className}>
            <span className={`step-number ${stepDone.get(item.step) ? 'done' : ''}`}>{stepDone.get(item.step) ? '✓' : index + 1}</span>{item.label}
          </NavLink>
        ))}
        <div className="nav-section">2 · Analyse</div>
        {ANALYSE.map((item) => <NavLink key={item.to} to={item.to} end={item.to === '/'} className={className}>{item.label}</NavLink>)}
        <div className="nav-section">Settings</div>
        <NavLink to="/categories" className={className}>Categories &amp; rules</NavLink>
      </nav>
      <UserBadge />
    </aside>
  )
}

/** New users land on the guided setup; once the essentials exist, the dashboard is home. */
function Home() {
  const setup = useLoad(() => api.setup.get())
  if (!setup.data) return <p className="muted">Loading…</p>
  return setup.data.complete ? <DashboardPage /> : <Navigate to="/start" replace />
}

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <div className="layout">
          <Sidebar />
          <main className="content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/start" element={<StartPage />} />
              <Route path="/accounts" element={<AccountsPage />} />
              <Route path="/income" element={<IncomePage />} />
              <Route path="/loans" element={<LoansPage />} />
              <Route path="/rental" element={<RentalPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/transactions" element={<TransactionsPage />} />
              <Route path="/plan" element={<GoalsPage />} />
              <Route path="/insights" element={<InsightsPage />} />
              <Route path="/wealth" element={<WealthPage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/categories" element={<CategoriesPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthGate>
  )
}
