import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatDate, formatMoney, type ActionItem } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const dayLabel = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
const PRIORITY: Record<number, { label: string; className: string }> = {
  1: { label: 'Urgent', className: 'high' }, 2: { label: 'Important', className: 'medium' }, 3: { label: 'When you can', className: 'low' },
}
const STORAGE_KEY = 'spendings.actions.done'

function loadDone(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') } catch { return {} }
}

function ActionCard({ action, done, onToggle }: { action: ActionItem; done: boolean; onToggle: () => void }) {
  const priority = PRIORITY[action.priority]
  return (
    <div className="card" style={done ? { opacity: 0.55 } : undefined}>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <span className={`severity ${priority.className}`}>{priority.label}</span>
        <strong style={done ? { textDecoration: 'line-through' } : undefined}>{action.title}</strong>
        <span className="spacer" />
        {action.due && <span className="chip">by {formatDate(action.due)}</span>}
        {action.impact.monthly ? <span className="chip positive">{euros(action.impact.monthly)} / month</span> : null}
        {action.impact.once ? <span className="chip">{euros(action.impact.once)} once</span> : null}
      </div>
      <div className="small"><span className="muted">The issue · </span>{action.issue}</div>
      <div className="small muted" style={{ margin: '8px 0 2px' }}>What to do</div>
      <ol className="small" style={{ margin: '0 0 8px 18px', padding: 0 }}>
        {action.steps.map((step) => <li key={step} style={{ margin: '2px 0' }}>{step}</li>)}
      </ol>
      <div className="inline-form">
        <label className="small"><input type="checkbox" checked={done} onChange={onToggle} /> done</label>
        <span className="spacer" />
        {action.link && <Link to={action.link}><button className="small">{action.link_label ?? 'Open'}</button></Link>}
      </div>
    </div>
  )
}

export default function ActionPlanPage() {
  const plan = useLoad(() => api.actions())
  const [done, setDone] = useState<Record<string, boolean>>(loadDone)

  if (plan.error) return <div className="alert error">{plan.error}</div>
  const data = plan.data
  if (!data) return <p className="muted">Building your plan…</p>
  if (data.empty) return <div className="card"><p>There is nothing to analyse yet. Follow <Link to="/start">Get started</Link> first.</p></div>

  const toggle = (key: string) => {
    const next = { ...done, [key]: !done[key] }
    setDone(next)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch { /* private mode: keep it in memory */ }
  }
  const all = data.horizons.flatMap((horizon) => horizon.actions)
  const doneCount = all.filter((action) => done[action.key]).length
  const { headline, forecast } = data
  const metrics = headline.metrics
  const chartData = forecast?.rows.map((row) => ({ ...row, label: dayLabel(row.date) })) ?? []

  return (
    <div>
      <h1>Action plan</h1>

      <div className="card" style={{ borderColor: headline.tone === 'attention' ? 'var(--negative)' : 'var(--positive)' }}>
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Where you stand</h2>
          <span className="spacer" />
          <span className="small muted">{doneCount} of {all.length} actions done</span>
        </div>
        <ul style={{ margin: '4px 0 12px 18px', padding: 0 }}>
          {headline.bullets.map((bullet) => <li key={bullet} style={{ margin: '4px 0' }}>{bullet}</li>)}
        </ul>
        <div className="grid cols-4">
          <div className="stat"><div className="label">Typical month</div><div className={`value ${metrics.typical_surplus >= 0 ? 'positive' : 'negative'}`}>{euros(metrics.typical_surplus)}</div><div className="small muted">income minus spending</div></div>
          <div className="stat"><div className="label">Credits per month</div><div className="value">{euros(metrics.debt_monthly)}</div><div className="small muted">{metrics.debt_share !== null ? `${Math.round(metrics.debt_share * 100)} % of income` : ''}</div></div>
          <div className="stat"><div className="label">Lowest point, 45 days</div><div className={`value ${metrics.forecast_low && metrics.forecast_low.balance < 0 ? 'negative' : ''}`}>{metrics.forecast_low ? euros(metrics.forecast_low.balance) : '–'}</div>
            <div className="small muted">{metrics.forecast_low ? `on ${dayLabel(metrics.forecast_low.date)}, limit -${euros(metrics.forecast_limit ?? 0)}` : ''}</div></div>
          <div className="stat"><div className="label">Emergency cash</div><div className="value">{euros(metrics.cash_savings)}</div><div className="small muted">{metrics.essential_monthly ? `${(metrics.cash_savings / metrics.essential_monthly).toFixed(1)} months of essentials` : ''}</div></div>
        </div>
      </div>

      {forecast && (
        <div className="card">
          <h2>Your accounts over the next {forecast.rows.length} days</h2>
          <p className="small muted">All current accounts together, from today's balances. It uses what is known: loan instalments, the upcoming payments you entered, fixed monthly debits, your usual salary day (the {forecast.salary_day}th) and rent, and about {euros(forecast.daily_other_spending)} a day for everyday spending. The red line is your authorised overdraft.</p>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} minTickGap={32} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} width={60} />
              <ReferenceLine y={0} stroke="var(--text-muted)" />
              <ReferenceLine y={-forecast.limit} stroke="var(--negative)" strokeDasharray="5 4" label={{ value: 'overdraft limit', fill: 'var(--negative)', fontSize: 11, position: 'insideBottomRight' }} />
              <Tooltip content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as (typeof chartData)[number]
                return (
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: 8, fontSize: 12, color: 'var(--text)' }}>
                    <strong>{row.label}</strong>: {formatMoney(row.balance)}
                    {row.events.map((event) => <div key={event.label + event.amount}>{event.label} {event.amount > 0 ? '+' : ''}{formatMoney(event.amount)}</div>)}
                  </div>
                )
              }} />
              <Line type="stepAfter" dataKey="balance" stroke="var(--accent)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.horizons.map((horizon) => (
        <div key={horizon.key} style={{ marginTop: 20 }}>
          <h2>{horizon.label}</h2>
          {horizon.actions.length === 0 && <p className="muted small">Nothing to do here.</p>}
          {horizon.actions.map((action) => <ActionCard key={action.key} action={action} done={Boolean(done[action.key])} onToggle={() => toggle(action.key)} />)}
        </div>
      ))}

      <div className="card" style={{ marginTop: 20 }}>
        <h2>Your monthly routine</h2>
        <p className="small muted">Ten minutes a month keeps all of the above accurate.</p>
        <table>
          <tbody>
            {data.routine.map((item) => (
              <tr key={item.title}>
                <td><Link to={item.link}>{item.title}</Link>{item.due && <span className="severity medium" style={{ marginLeft: 8 }}>due</span>}</td>
                <td className="muted small">{item.when}</td>
                <td className="muted small">{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
