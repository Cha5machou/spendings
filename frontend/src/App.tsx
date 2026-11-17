import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
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
import PlanPage from './pages/PlanPage'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/plan', label: 'Goals & plan' },
  { to: '/insights', label: 'Analysis' },
  { to: '/wealth', label: 'Savings & net worth' },
  { to: '/income', label: 'Income' },
  { to: '/loans', label: 'Loans & credits' },
  { to: '/rental', label: 'Rental property' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/documents', label: 'Documents' },
  { to: '/accounts', label: 'Accounts' },
  { to: '/categories', label: 'Categories' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <aside className="sidebar">
          <div className="brand">Spendings</div>
          <nav>
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
                {link.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/plan" element={<PlanPage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/wealth" element={<WealthPage />} />
            <Route path="/income" element={<IncomePage />} />
            <Route path="/loans" element={<LoansPage />} />
            <Route path="/rental" element={<RentalPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
