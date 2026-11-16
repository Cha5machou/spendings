import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney } from '../api'
import { useLoad } from '../hooks'

const RANGES = [
  { label: '3 months', months: 3 },
  { label: '6 months', months: 6 },
  { label: '12 months', months: 12 },
  { label: 'All', months: 0 },
]

function rangeStart(months: number): string | undefined {
  if (!months) return '2000-01-01'
  const start = new Date()
  start.setMonth(start.getMonth() - months + 1, 1)
  return start.toISOString().slice(0, 10)
}

export default function DashboardPage() {
  const [months, setMonths] = useState(6)
  const [accountId, setAccountId] = useState<number | undefined>()
  const accounts = useLoad(() => api.accounts.list())
  const dashboard = useLoad(() => api.dashboard({ start: rangeStart(months), account_id: accountId }), [months, accountId])

  const data = dashboard.data
  const expenseCategories = data?.by_category.filter((entry) => entry.total < 0 && entry.kind !== 'savings' && entry.kind !== 'transfer') ?? []
  const largestExpense = Math.max(1, ...expenseCategories.map((entry) => -entry.total))

  return (
    <div>
      <h1>Dashboard</h1>
      <div className="toolbar">
        {RANGES.map((range) => (
          <button key={range.label} className={range.months === months ? 'primary' : ''} onClick={() => setMonths(range.months)}>
            {range.label}
          </button>
        ))}
        <span className="spacer" />
        <select value={accountId ?? ''} onChange={(event) => setAccountId(event.target.value ? Number(event.target.value) : undefined)}>
          <option value="">All accounts</option>
          {accounts.data?.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      </div>

      {dashboard.error && <div className="alert error">{dashboard.error}</div>}
      {!data && !dashboard.error && <p className="muted">Loading…</p>}

      {data && data.by_month.length === 0 && (
        <div className="card">
          <p>No transactions yet. Create an <Link to="/accounts">account</Link>, then upload a bank statement on the <Link to="/documents">Documents</Link> page.</p>
        </div>
      )}

      {data && (
        <>
          <div className="grid cols-4">
            <div className="card stat"><div className="label">Income</div><div className="value positive">{formatMoney(data.income)}</div></div>
            <div className="card stat"><div className="label">Expenses</div><div className="value negative">{formatMoney(data.expenses)}</div></div>
            <div className="card stat"><div className="label">Saved / invested</div><div className="value">{formatMoney(data.savings)}</div></div>
            <div className="card stat">
              <div className="label">Net</div>
              <div className={`value ${data.net >= 0 ? 'positive' : 'negative'}`}>{formatMoney(data.net)}</div>
              {data.uncategorized_count > 0 && (
                <div className="small"><Link to="/transactions?uncategorized=1">{data.uncategorized_count} uncategorized</Link></div>
              )}
            </div>
          </div>

          <div className="card">
            <h2>Monthly income, expenses and savings</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.by_month} barGap={2} maxBarSize={48}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="month" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} axisLine={false} tickLine={false} width={70} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }} />
                <Legend />
                <Bar dataKey="income" name="Income" fill="var(--income)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expenses" name="Expenses" fill="var(--expense)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="savings" name="Savings" fill="var(--savings)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="grid cols-2">
            <div className="card">
              <h2>Expenses by category</h2>
              {expenseCategories.map((entry) => (
                <div className="bar-row" key={entry.category_id ?? 'none'}>
                  <span>
                    <span className="dot" style={{ background: entry.color ?? 'var(--text-muted)' }} />
                    {entry.category_id ? <Link to={`/transactions?category_id=${entry.category_id}`}>{entry.category_name}</Link> : <Link to="/transactions?uncategorized=1">{entry.category_name}</Link>}
                  </span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${(-entry.total / largestExpense) * 100}%`, background: entry.color ?? 'var(--text-muted)' }} /></div>
                  <span className="amount" style={{ textAlign: 'right' }}>{formatMoney(-entry.total)} <span className="muted small">({entry.count})</span></span>
                </div>
              ))}
            </div>
            <div className="card">
              <h2>Top merchants / payees</h2>
              <table>
                <tbody>
                  {data.top_merchants.map((merchant) => (
                    <tr key={merchant.category_name}>
                      <td>{merchant.category_name}</td>
                      <td className="muted small">{merchant.count}×</td>
                      <td className="amount">{formatMoney(-merchant.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
