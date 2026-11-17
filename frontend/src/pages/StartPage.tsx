import { Link } from 'react-router-dom'
import { api } from '../api'
import { useLoad } from '../hooks'

export default function StartPage() {
  const setup = useLoad(() => api.setup.get())
  const data = setup.data
  if (setup.error) return <div className="alert error">{setup.error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const done = data.steps.filter((step) => step.done).length
  const skippable: Record<string, 'skipped_loans' | 'skipped_property'> = { loans: 'skipped_loans', property: 'skipped_property' }

  return (
    <div>
      <h1>Get started</h1>
      <p className="muted">
        Spendings turns your bank statements, payslips and credits into a clear picture of your money and a plan for your goals.
        Follow the steps in order; it takes about fifteen minutes. Everything stays in your own database.
      </p>

      <div className="card">
        <div className="toolbar">
          <strong>{done} of {data.steps.length} steps done</strong>
          <span className="spacer" />
          {data.complete && <Link to="/"><button className="primary">See my action plan</button></Link>}
        </div>
        <div className="progress"><div style={{ width: `${(done / data.steps.length) * 100}%` }} /></div>

        <div style={{ marginTop: 8 }}>
          {data.steps.map((step, index) => (
            <div className="setup-step" key={step.key}>
              <span className={`step-number ${step.done ? 'done' : ''}`}>{step.done ? '✓' : index + 1}</span>
              <div>
                <div><strong>{step.title}</strong>{!step.required && <span className="muted small"> · optional</span>}</div>
                <div className="small muted">{step.detail}</div>
              </div>
              <div className="inline-form">
                {!step.done && skippable[step.key] && (
                  <button className="small" onClick={async () => { await api.plan.update({ [skippable[step.key]]: true }); setup.reload() }}>I have none</button>
                )}
                <Link to={step.route}><button className={`small ${data.next === step.key ? 'primary' : ''}`}>{step.done ? 'Review' : 'Open'}</button></Link>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Then explore</h2>
        <ul>
          <li><Link to="/">Action plan</Link>: what the issues are and what to do this week, this month and beyond.</li>
          <li><Link to="/dashboard">Dashboard</Link>: income, expenses and savings by month.</li>
          <li><Link to="/insights">Analysis</Link>: where the money goes, recurring payments, what to improve.</li>
          <li><Link to="/wealth">Savings &amp; net worth</Link>: everything you own and owe.</li>
          <li><Link to="/ask">Ask</Link>: questions about your own numbers, in plain language.</li>
        </ul>
      </div>
    </div>
  )
}
