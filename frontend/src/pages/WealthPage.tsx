import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatDate, formatMoney } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const SERIES_COLORS = ['var(--accent)', '#8f5fa0', 'var(--savings)', '#3f8fb0', 'var(--expense)']
const CLASS_COLORS: Record<string, string> = {
  etf: 'var(--accent)', stock: '#8f5fa0', fund: '#3f8fb0', structured_bond: 'var(--expense)', crypto: '#c9a227', leveraged: 'var(--negative)', cash: 'var(--savings)', other: 'var(--text-muted)',
}
const dateLabel = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

export default function WealthPage() {
  const wealth = useLoad(() => api.wealth.get())
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [values, setValues] = useState<Record<number, string>>({})
  const [message, setMessage] = useState<string | null>(null)

  if (wealth.error) return <div className="alert error">{wealth.error}</div>
  const data = wealth.data
  if (!data) return <p className="muted">Loading…</p>

  const { net_worth: netWorth } = data
  const savingsAndInvestments = netWorth.cash_savings + netWorth.invested
  const totalAllocation = Math.max(data.allocation.reduce((sum, entry) => sum + entry.value, 0), 1)
  const peak = data.history.reduce((best, entry) => (entry.total > best.total ? entry : best), data.history[0])

  async function saveBalances() {
    const entries = Object.entries(values).filter(([, raw]) => raw.trim() !== '')
    for (const [accountId, raw] of entries) await api.wealth.snapshot(Number(accountId), day, Number(raw.replace(',', '.')))
    setValues({})
    setMessage(`Saved ${entries.length} balance${entries.length === 1 ? '' : 's'} for ${formatDate(day)}.`)
    wealth.reload()
  }

  return (
    <div>
      <h1>Savings &amp; net worth</h1>
      <div className="grid cols-4">
        <div className="card stat"><div className="label">Savings & investments</div><div className="value">{euros(savingsAndInvestments)}</div>
          {peak && <div className="small muted">peak {euros(peak.total)} in {dateLabel(peak.date)}</div>}</div>
        <div className="card stat"><div className="label">Financial net worth</div><div className={`value ${netWorth.financial >= 0 ? 'positive' : 'negative'}`}>{euros(netWorth.financial)}</div>
          <div className="small muted">accounts + savings − consumer credits</div></div>
        <div className="card stat"><div className="label">Net worth with the flat</div><div className={`value ${netWorth.total >= 0 ? 'positive' : 'negative'}`}>{euros(netWorth.total)}</div>
          <div className="small muted">flat at {netWorth.property_basis}</div></div>
        <div className="card stat"><div className="label">Emergency cash</div><div className="value">{euros(netWorth.cash_savings)}</div>
          <div className="small muted">Livret A + LDDS</div></div>
      </div>

      {data.checks.length > 0 && (
        <div className="card">
          <h2>Worth your attention</h2>
          {data.checks.map((check) => (
            <div className="reco" key={check.title}>
              <div>
                <div className="title"><span className={`severity ${check.severity}`}>{check.severity}</span>{check.title}</div>
                <div className="small muted" style={{ marginTop: 4 }}>{check.detail}</div>
              </div>
              <div />
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h2>Savings and investments over time</h2>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={data.history}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="date" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={dateLabel} minTickGap={40} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
            <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => formatDate(String(label))} contentStyle={tooltipStyle} />
            <Legend />
            {data.accounts.map((account, index) => (
              <Area key={account.account_id} type="monotone" dataKey={String(account.account_id)} name={account.name} stackId="wealth"
                stroke={SERIES_COLORS[index % SERIES_COLORS.length]} fill={SERIES_COLORS[index % SERIES_COLORS.length]} fillOpacity={0.55} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>What you own and owe</h2>
          <table>
            <tbody>
              <tr><td>Current accounts</td><td className={`amount ${netWorth.checking < 0 ? 'negative' : ''}`}>{formatMoney(netWorth.checking)}</td></tr>
              <tr><td>Livret A, LDDS</td><td className="amount">{formatMoney(netWorth.cash_savings)}</td></tr>
              <tr><td>PEA, assurance-vie, brokerage</td><td className="amount">{formatMoney(netWorth.invested)}</td></tr>
              <tr><td>Consumer credits</td><td className="amount negative">−{formatMoney(netWorth.consumer_debt)}</td></tr>
              <tr><td><strong>Financial net worth</strong></td><td className="amount"><strong>{formatMoney(netWorth.financial)}</strong></td></tr>
              <tr><td>Flat ({netWorth.property_basis})</td><td className="amount">{formatMoney(netWorth.property_value)}</td></tr>
              <tr><td>Mortgage</td><td className="amount negative">−{formatMoney(netWorth.mortgage)}</td></tr>
              <tr><td><strong>Net worth</strong></td><td className="amount"><strong>{formatMoney(netWorth.total)}</strong></td></tr>
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>
            The flat's equity is the price minus the mortgage; selling would cost agent fees and the early-repayment indemnity, see <Link to="/rental">Rental property</Link>.
          </p>
        </div>

        <div className="card">
          <h2>Allocation</h2>
          <div className="stack" style={{ marginBottom: 8 }}>
            {data.allocation.map((entry) => <div key={entry.asset_class} title={entry.label} style={{ width: `${(entry.value / totalAllocation) * 100}%`, background: CLASS_COLORS[entry.asset_class] ?? 'var(--text-muted)' }} />)}
          </div>
          <table>
            <tbody>
              {data.allocation.map((entry) => (
                <tr key={entry.asset_class}>
                  <td><span className="dot" style={{ background: CLASS_COLORS[entry.asset_class] ?? 'var(--text-muted)' }} />{entry.label}</td>
                  <td className="muted small">{Math.round((entry.value / totalAllocation) * 100)} %</td>
                  <td className="amount">{formatMoney(entry.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Accounts</h2>
        <table>
          <thead><tr><th>Account</th><th>Balance</th><th>As of</th><th>Last 12 months</th><th>Since first record</th><th>New balance</th></tr></thead>
          <tbody>
            {data.accounts.map((account) => (
              <tr key={account.account_id}>
                <td>{account.name}</td>
                <td className="amount">{formatMoney(account.balance)}</td>
                <td className="muted small">{account.as_of ? formatDate(account.as_of) : '–'}</td>
                <td className={`amount ${account.change_12m !== null && account.change_12m < 0 ? 'negative' : ''}`}>{account.change_12m !== null ? formatMoney(account.change_12m) : '–'}</td>
                <td className={`amount ${account.since_first !== null && account.since_first < 0 ? 'negative' : ''}`}>{account.since_first !== null ? formatMoney(account.since_first) : '–'}</td>
                <td><input style={{ width: 90 }} placeholder="€" value={values[account.account_id] ?? ''} onChange={(event) => setValues({ ...values, [account.account_id]: event.target.value })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="inline-form" style={{ marginTop: 8 }}>
          <label className="small">Balances on <input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>
          <button className="primary" onClick={saveBalances}>Save balances</button>
          {message && <span className="small positive">{message}</span>}
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>Variations include deposits and withdrawals, not only market performance: the assurance-vie fell mainly because you took money out of it. Enter the new balances once a month to keep the curve going.</p>
      </div>

      <div className="card">
        <h2>Positions</h2>
        <table>
          <thead><tr><th>Position</th><th>Type</th><th>Value</th><th>Share of account</th><th>Gain or loss</th></tr></thead>
          <tbody>
            {data.accounts.filter((account) => data.holdings.some((holding) => holding.account_id === account.account_id)).map((account) => {
              const positions = data.holdings.filter((holding) => holding.account_id === account.account_id)
              const total = positions.reduce((sum, holding) => sum + holding.value, 0)
              return [
                <tr key={`h${account.account_id}`}><td colSpan={5} className="small muted" style={{ paddingTop: 12 }}>{account.name}</td></tr>,
                ...positions.map((holding) => (
                  <tr key={holding.name}>
                    <td>{holding.name}<div className="small muted">{holding.identifier}</div></td>
                    <td><span className="dot" style={{ background: CLASS_COLORS[holding.asset_class] ?? 'var(--text-muted)' }} />{holding.asset_class.replace('_', ' ')}</td>
                    <td className="amount">{formatMoney(holding.value)}</td>
                    <td className="muted small">{Math.round((holding.value / total) * 100)} %</td>
                    <td className="muted">{holding.gain_loss !== null ? `(${formatMoney(holding.gain_loss)})` : ''}</td>
                  </tr>
                )),
              ]
            })}
          </tbody>
        </table>
        <p className="small muted" style={{ marginTop: 8 }}>
          Values and the gain or loss column are copied from your tracker of 16 November 2026. The tracker prints the gain or loss in brackets without a sign, so I show it as printed and do not use it in any calculation.
        </p>
      </div>
    </div>
  )
}
