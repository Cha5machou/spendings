import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney, type InsightCategory } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }

function monthLabel(month: string): string {
  return new Date(month + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })
}

function monthBounds(month: string): { start: string; end: string } {
  const [year, number] = month.split('-').map(Number)
  const last = new Date(year, number, 0).getDate()
  return { start: `${month}-01`, end: `${month}-${String(last).padStart(2, '0')}` }
}

const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')

export default function InsightsPage() {
  const [months, setMonths] = useState(12)
  const [selectedId, setSelectedId] = useState<number | null | undefined>(undefined)
  const [showEnded, setShowEnded] = useState(false)
  const navigate = useNavigate()
  const insights = useLoad(() => api.insights(months), [months])
  const data = insights.data

  function openTransactions(category: InsightCategory, month?: string) {
    const params = new URLSearchParams()
    if (category.category_id) params.set('category_id', String(category.category_id))
    if (month) {
      const bounds = monthBounds(month)
      params.set('start', bounds.start)
      params.set('end', bounds.end)
    }
    navigate(`/transactions?${params}`)
  }

  if (insights.error) return <div className="alert error">{insights.error}</div>
  if (!data) return <p className="muted">Analysing…</p>
  if (data.empty) {
    return <div className="card"><p>Nothing to analyse yet. Import statements on the <Link to="/documents">Documents</Link> page first.</p></div>
  }

  const { overview } = data
  const windowMonths = data.months.filter((entry) => !entry.partial).map((entry) => entry.month)
  const columns = [...windowMonths, ...data.months.filter((entry) => entry.partial).map((entry) => entry.month)]
  const expenseRows = data.categories.filter((row) => row.kind === 'expense')
  const groups: { label: string; rows: InsightCategory[] }[] = [
    { label: 'Essential', rows: expenseRows.filter((row) => row.necessity === 'essential') },
    { label: 'Flexible', rows: expenseRows.filter((row) => row.necessity === 'flexible') },
    { label: 'Unclassified', rows: expenseRows.filter((row) => !row.necessity) },
    { label: 'Income', rows: data.categories.filter((row) => row.kind === 'income') },
    { label: 'Saved / invested', rows: data.categories.filter((row) => row.kind === 'savings') },
  ].filter((group) => group.rows.length > 0)
  const selected = data.categories.find((row) => row.category_id === selectedId)
  const recurringShown = data.recurring.filter((entry) => showEnded || entry.active)
  const recurringMonthly = recurringShown.filter((entry) => entry.active).reduce((sum, entry) => sum + entry.monthly_amount, 0)
  const surplus = overview.typical_surplus
  const stackTotal = Math.max(overview.typical_income, overview.typical_spending + Math.max(overview.typical_saved_or_invested, 0), 1)

  return (
    <div>
      <h1>Analysis</h1>
      <div className="toolbar">
        {[6, 12, 24].map((count) => (
          <button key={count} className={count === months ? 'primary' : ''} onClick={() => setMonths(count)}>{count} months</button>
        ))}
        <span className="spacer" />
        <span className="small muted">
          {overview.months} complete months, {monthLabel(overview.window_start!)} to {monthLabel(overview.window_end!)}. The current month is shown separately.
        </span>
      </div>

      <div className="grid cols-4">
        <div className="card stat"><div className="label">Typical income / month</div><div className="value positive">{euros(overview.typical_income)}</div>
          {overview.income_one_off_total > 0 && <div className="small muted">excl. {euros(overview.income_one_off_total)} one-off</div>}</div>
        <div className="card stat"><div className="label">Typical spending / month</div><div className="value negative">{euros(overview.typical_spending)}</div>
          {overview.one_off_total > 0 && <div className="small muted">excl. {euros(overview.one_off_total)} one-offs over the period</div>}</div>
        <div className="card stat"><div className="label">{surplus >= 0 ? 'Surplus' : 'Deficit'} / month</div>
          <div className={`value ${surplus >= 0 ? 'positive' : 'negative'}`}>{euros(surplus)}</div>
          {overview.savings_rate !== null && <div className="small muted">savings rate {Math.round(overview.savings_rate * 100)} % (target 20 %)</div>}</div>
        <div className="card stat"><div className="label">Savings you could unlock</div><div className="value positive">{euros(data.potential_monthly_savings)}</div>
          <div className="small muted">per month, from the actions below</div></div>
      </div>

      <div className="card">
        <h2>Where a typical month goes</h2>
        <div className="stack" title="Essential, flexible, saved, left over">
          <div style={{ width: `${(overview.essential_spending / stackTotal) * 100}%`, background: 'var(--accent)' }} />
          <div style={{ width: `${(overview.flexible_spending / stackTotal) * 100}%`, background: 'var(--expense)' }} />
          <div style={{ width: `${(overview.unclassified_spending / stackTotal) * 100}%`, background: 'var(--text-muted)' }} />
          <div style={{ width: `${(Math.max(overview.typical_saved_or_invested, 0) / stackTotal) * 100}%`, background: 'var(--savings)' }} />
        </div>
        <div className="chips" style={{ marginTop: 8 }}>
          <span className="chip"><span className="dot" style={{ background: 'var(--accent)' }} />Essential {euros(overview.essential_spending)}</span>
          <span className="chip"><span className="dot" style={{ background: 'var(--expense)' }} />Flexible {euros(overview.flexible_spending)}</span>
          {overview.unclassified_spending > 0 && <span className="chip"><span className="dot" style={{ background: 'var(--text-muted)' }} />Unclassified {euros(overview.unclassified_spending)}</span>}
          <span className="chip"><span className="dot" style={{ background: 'var(--savings)' }} />Saved / invested {euros(overview.typical_saved_or_invested)}</span>
          <span className="chip muted">of {euros(overview.typical_income)} income. Essential includes debt payments.</span>
        </div>
      </div>

      <div className="card">
        <h2>What to improve</h2>
        {data.recommendations.map((item) => (
          <div className="reco" key={item.key}>
            <div>
              <div className="title"><span className={`severity ${item.severity}`}>{item.severity}</span>{item.title}</div>
              <div className="small muted" style={{ marginTop: 4 }}>{item.detail}</div>
              {item.category_id && (
                <div className="small" style={{ marginTop: 4 }}>
                  <a href="#explorer" onClick={() => setSelectedId(item.category_id)}>See this category</a>
                </div>
              )}
            </div>
            <div className="impact">{item.monthly_impact ? `${item.saving ? '+' : ''}${euros(item.monthly_impact)} / mo` : ''}</div>
          </div>
        ))}
        <p className="small muted" style={{ marginTop: 12 }}>
          These checks are computed from your own transactions, not generated, so they update as you tag and import. Amounts are estimates; verify before acting.
        </p>
      </div>

      <div className="card" id="explorer">
        <h2>Spending explorer</h2>
        <p className="small muted">Each cell is the month's net amount for the category (refunds netted). Click a cell to see its transactions, a name to chart it below.</p>
        <div className="scroll-x">
          <table className="matrix">
            <thead>
              <tr>
                <th>Category</th>
                {columns.map((month) => <th key={month} style={data.months.find((entry) => entry.month === month)?.partial ? { fontStyle: 'italic' } : undefined}>{monthLabel(month)}{data.months.find((entry) => entry.month === month)?.partial ? '*' : ''}</th>)}
                <th>Average</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => {
                const groupColumnTotals = columns.map((_, index) => group.rows.reduce((sum, row) => sum + (index < windowMonths.length ? row.series[index] : row.current_month), 0))
                return [
                  <tr className="group" key={group.label}>
                    <td>{group.label}</td>
                    {groupColumnTotals.map((total, index) => <td key={index}>{euros(total)}</td>)}
                    <td>{euros(group.rows.reduce((sum, row) => sum + row.average, 0))}</td>
                  </tr>,
                  ...group.rows.map((row) => {
                    const rowMax = Math.max(1, ...row.series, row.current_month)
                    const color = row.kind === 'income' ? 'var(--positive)' : row.kind === 'savings' ? 'var(--savings)' : 'var(--expense)'
                    return (
                      <tr key={row.category_id ?? 'none'} className={selectedId === row.category_id ? 'selected' : ''}>
                        <td className="name" onClick={() => setSelectedId(row.category_id)} title={`${row.name} (${row.pattern})`}>
                          <span className="dot" style={{ background: row.color ?? 'var(--text-muted)' }} />{row.name}
                        </td>
                        {columns.map((month, index) => {
                          const value = index < windowMonths.length ? row.series[index] : row.current_month
                          const intensity = value > 0 ? Math.round((value / rowMax) * 55) : 0
                          return (
                            <td key={month} className="cell" style={{ background: intensity ? `color-mix(in srgb, ${color} ${intensity}%, transparent)` : undefined }}
                              onClick={() => openTransactions(row, month)}>
                              {Math.abs(value) < 0.5 ? '' : Math.round(value)}
                            </td>
                          )
                        })}
                        <td><strong>{Math.round(row.average)}</strong></td>
                      </tr>
                    )
                  }),
                ]
              })}
            </tbody>
          </table>
        </div>
        <p className="small muted">* month in progress, not part of the averages.</p>
      </div>

      {selected && (
        <div className="card">
          <div className="toolbar">
            <h2 style={{ margin: 0 }}><span className="dot" style={{ background: selected.color ?? 'var(--text-muted)' }} />{selected.name}</h2>
            <span className="spacer" />
            <button onClick={() => openTransactions(selected)}>All transactions</button>
            <button onClick={() => setSelectedId(undefined)}>Close</button>
          </div>
          <div className="chips" style={{ marginBottom: 8 }}>
            <span className="chip">Average {euros(selected.average)} / month</span>
            <span className="chip">Median {euros(selected.median)}</span>
            <span className="chip">Last 3 months {euros(selected.recent_average)} vs {euros(selected.earlier_average)} before</span>
            <span className="chip">Pattern: {selected.pattern}</span>
            {selected.share !== null && <span className="chip">{Math.round(selected.share * 100)} % of spending</span>}
            {selected.one_off_total > 0 && <span className="chip">One-offs {euros(selected.one_off_total)}</span>}
          </div>
          <div className="grid cols-2">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={windowMonths.map((month, index) => ({ month, amount: selected.series[index] }))} maxBarSize={36}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={monthLabel} />
                <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
                <ReferenceLine y={selected.average} stroke="var(--text-muted)" strokeDasharray="4 4" />
                <Bar dataKey="amount" name={selected.name} fill={selected.color ?? 'var(--expense)'} radius={[4, 4, 0, 0]} cursor="pointer"
                  onClick={(entry) => openTransactions(selected, (entry as unknown as { month: string }).month)} />
              </BarChart>
            </ResponsiveContainer>
            <div>
              <div className="small muted" style={{ marginBottom: 4 }}>Where it goes</div>
              <table>
                <tbody>
                  {selected.top_merchants.map((merchant) => (
                    <tr key={merchant.name}>
                      <td>{merchant.name}</td>
                      <td className="muted small">{merchant.count}×</td>
                      <td className="amount">{formatMoney(merchant.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Recurring payments</h2>
          <span className="spacer" />
          <span className="small muted">{euros(recurringMonthly)} a month, {euros(recurringMonthly * 12)} a year (active)</span>
          <label className="small"><input type="checkbox" checked={showEnded} onChange={(event) => setShowEnded(event.target.checked)} /> show ended</label>
        </div>
        <table>
          <thead><tr><th>Payee</th><th>Category</th><th>Per month</th><th>Per year</th><th>Seen</th></tr></thead>
          <tbody>
            {recurringShown.map((entry) => (
              <tr key={entry.name + entry.first_month} style={entry.active ? undefined : { opacity: 0.55 }}>
                <td title={entry.example_label}>{entry.name}{!entry.fixed_amount && <span className="muted small"> (varies)</span>}</td>
                <td className="muted">{entry.category_name}</td>
                <td className="amount">{formatMoney(entry.monthly_amount)}</td>
                <td className="amount">{formatMoney(entry.yearly_cost)}</td>
                <td className="muted small">{entry.months_seen} months{entry.active ? '' : `, ended ${monthLabel(entry.last_month)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid cols-2">
        {data.overdraft.map((account) => (
          <div className="card" key={account.account_id}>
            <h2>{account.account_name}</h2>
            <p className="small muted">
              Overdrawn {account.days_negative} of {account.days_tracked} days
              {account.days_beyond_limit > 0 && <>, <span className="negative">beyond the {euros(account.overdraft_limit)} limit on {account.days_beyond_limit} days</span></>}.
              Lowest {account.lowest_balance !== null ? euros(account.lowest_balance) : '–'}{account.lowest_balance_date ? ` on ${account.lowest_balance_date}` : ''}.
            </p>
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={account.by_month} maxBarSize={24}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={monthLabel} />
                <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
                <ReferenceLine y={0} stroke="var(--text-muted)" />
                <ReferenceLine y={-account.overdraft_limit} stroke="var(--negative)" strokeDasharray="4 4" label={{ value: 'limit', fill: 'var(--negative)', fontSize: 11, position: 'insideBottomRight' }} />
                <Bar dataKey="lowest_balance" name="Lowest balance of the month" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>

      {data.one_offs.length > 0 && (
        <div className="card">
          <h2>One-offs kept out of the "typical month"</h2>
          <table>
            <tbody>
              {data.one_offs.map((entry) => (
                <tr key={entry.id}>
                  <td className="muted small">{entry.date}</td>
                  <td>{entry.label}</td>
                  <td className="muted">{entry.category_name}</td>
                  <td className={`amount ${entry.amount >= 0 ? 'positive' : ''}`}>{formatMoney(entry.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
