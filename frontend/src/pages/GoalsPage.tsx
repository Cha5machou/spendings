import { useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney, type Goal, type GoalKind, type GoalWithProgress, type PlanAffordability, type PlanSettingsData } from '../api'
import HelpBox from '../components/HelpBox'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number | null | undefined) => (value === null || value === undefined ? '–' : formatMoney(Math.round(value)).replace(/,00$/, ''))
const monthLabel = (month: string | null | undefined) => (month ? new Date(month.slice(0, 7) + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '–')

const KIND_LABEL: Record<GoalKind, string> = {
  savings: 'Save and invest', emergency_fund: 'Emergency fund', home_purchase: 'Buy a home', property_sale: 'Sell a property',
  housing_change: 'Change my housing', retirement: 'Retirement', other: 'Other',
}
const FUNDED_LABEL: Record<string, string> = { any: 'All my savings', livrets: 'Livrets', pea: 'PEA', cto: 'CTO / brokerage', av: 'Assurance-vie' }
const HORIZONS: { key: GoalWithProgress['horizon']; label: string }[] = [
  { key: 'short', label: 'Short term · within a year' }, { key: 'medium', label: 'Medium term · 1 to 4 years' },
  { key: 'long', label: 'Long term · more than 4 years' }, { key: 'none', label: 'No date yet' },
]
const PRIORITY_LABEL: Record<number, string> = { 1: 'high priority', 2: '', 3: 'low priority' }

type GoalForm = { title: string; kind: GoalKind; target_amount: string; target_date: string; funded_by: string; priority: string; notes: string }
const emptyForm = (): GoalForm => ({ title: '', kind: 'savings', target_amount: '', target_date: '', funded_by: 'any', priority: '2', notes: '' })

function inMonths(count: number): string {
  const date = new Date()
  date.setMonth(date.getMonth() + count)
  return date.toISOString().slice(0, 10)
}

function Affordability({ title, data }: { title: string; data: PlanAffordability }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <table>
        <tbody>
          <tr><td>Income the bank counts</td><td className="amount">{euros(data.bank_income)} / month</td></tr>
          <tr><td>Existing loan payments</td><td className="amount">{euros(data.existing_debt_payments)} / month</td></tr>
          <tr><td>Room for a new loan</td><td className="amount">{euros(data.room_for_new_loan)} / month</td></tr>
          <tr><td>Down payment</td><td className="amount">{euros(data.down_payment)}</td></tr>
          <tr><td><strong>Highest price you could reach</strong></td><td className="amount"><strong>{euros(data.price_max)}</strong></td></tr>
        </tbody>
      </table>
      <table style={{ marginTop: 12 }}>
        <thead><tr><th>Price</th><th>Payment</th><th>Debt ratio</th><th /></tr></thead>
        <tbody>
          {data.grid.map((row) => (
            <tr key={row.price}>
              <td>{euros(row.price)}</td><td className="amount">{euros(row.payment)}</td>
              <td className={row.feasible ? 'positive' : 'negative'}>{row.ratio !== null ? `${Math.round(row.ratio * 100)} %` : '–'}</td>
              <td className="small muted">{row.feasible ? 'fits' : 'too high'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function GoalsPage() {
  const plan = useLoad(() => api.plan.get())
  const [editing, setEditing] = useState<{ id: number | null; form: GoalForm } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [settingsForm, setSettingsForm] = useState<Record<string, string>>({})
  const [sellOn, setSellOn] = useState<boolean | null>(null)
  const [buyOn, setBuyOn] = useState<boolean | null>(null)
  const [saved, setSaved] = useState(false)

  if (plan.error) return <div className="alert error">{plan.error}</div>
  const data = plan.data
  if (!data) return <p className="muted">Computing…</p>

  const { settings, milestones, context } = data
  const hasProperty = Boolean(data.property_name)
  const sellEnabled = sellOn ?? settings.sale_date !== null
  const buyEnabled = buyOn ?? settings.purchase_date !== null
  const first = data.projection[0]
  const splitTotal = settings.split_pea + settings.split_cto + settings.split_livrets || 1
  const steady = milestones.steady_surplus ?? 0
  const chartData = data.projection.map((row) => ({ ...row, positive: Math.max(row.surplus, 0), negative: Math.min(row.surplus, 0) }))
  const emergencyTarget = Math.round((context.essential_typical * 3) / 100) * 100
  const hasData = context.salary_net > 0 || context.core_spending > 0

  function startNew(preset?: Partial<GoalForm>) {
    setEditing({ id: null, form: { ...emptyForm(), ...preset } })
    setError(null)
  }

  function startEdit(goal: Goal) {
    setEditing({
      id: goal.id, form: {
        title: goal.title, kind: goal.kind, target_amount: goal.target_amount?.toString() ?? '', target_date: goal.target_date ?? '',
        funded_by: goal.funded_by, priority: String(goal.priority), notes: goal.notes ?? '',
      },
    })
    setError(null)
  }

  async function saveGoal() {
    if (!editing) return
    const { form } = editing
    if (!form.title.trim()) { setError('Give the goal a title'); return }
    const payload = {
      title: form.title.trim(), kind: form.kind, funded_by: form.funded_by as Goal['funded_by'], priority: Number(form.priority) as Goal['priority'],
      target_amount: form.target_amount.trim() === '' ? null : Number(form.target_amount.replace(',', '.')),
      target_date: form.target_date || null, notes: form.notes.trim() || null,
    }
    try {
      if (editing.id === null) await api.goals.create(payload)
      else await api.goals.update(editing.id, payload)
      setEditing(null)
      plan.reload()
    } catch (saveError) {
      setError((saveError as Error).message)
    }
  }

  async function saveSettings() {
    const payload: Record<string, number | string | boolean | null> = {}
    for (const [key, raw] of Object.entries(settingsForm)) {
      if (key.endsWith('_date')) payload[key] = raw || null
      else payload[key] = raw.trim() === '' ? null : Number(raw.replace(',', '.'))
    }
    if (!sellEnabled) { payload.sale_date = null; payload.sale_price = null }
    if (!buyEnabled) { payload.purchase_date = null; payload.purchase_price = null }
    if (sellEnabled && !settings.sale_date && !payload.sale_date) payload.sale_date = inMonths(36)
    if (buyEnabled && !settings.purchase_date && !payload.purchase_date) payload.purchase_date = inMonths(36)
    await api.plan.update(payload)
    setSettingsForm({})
    setSellOn(null)
    setBuyOn(null)
    setSaved(true)
    plan.reload()
  }

  const value = (key: keyof PlanSettingsData) => (settingsForm[key] !== undefined ? settingsForm[key] : settings[key] === null ? '' : String(settings[key]))
  const field = (key: keyof PlanSettingsData, label: string, type = 'text') => (
    <label className="small" key={key}>{label}<br />
      <input style={{ width: '100%' }} type={type} value={value(key)} onChange={(event) => { setSaved(false); setSettingsForm({ ...settingsForm, [key]: event.target.value }) }} />
    </label>
  )

  return (
    <div>
      <h1>Goals</h1>
      <HelpBox title="How this works" open={data.goals.length === 0}>
        <ol>
          <li><strong>Write your goals</strong> below: what you want, roughly how much and by when. You can edit or delete them at any time.</li>
          <li><strong>Check the assumptions</strong> (where monthly savings go, your housing cost, an optional sale or purchase).</li>
          <li><strong>Read the projection</strong>: it uses your real income, spending, credits and savings, and tells you whether each goal is on track.</li>
        </ol>
        Nothing here is advice or a forecast of markets: returns are 0 % unless you set one.
      </HelpBox>

      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Your goals</h2>
          <span className="spacer" />
          <button className="primary" onClick={() => startNew()}>+ Add a goal</button>
        </div>

        {data.goals.length === 0 && !editing && (
          <div>
            <p className="muted small">No goal yet. Start from an example, or write your own:</p>
            <div className="chips">
              <button className="chip" onClick={() => startNew({ title: 'Emergency fund', kind: 'emergency_fund', funded_by: 'livrets', target_amount: emergencyTarget > 0 ? String(emergencyTarget) : '', target_date: inMonths(18), priority: '1', notes: '3 months of essential spending, kept on a livret.' })}>Emergency fund{emergencyTarget > 0 ? ` (${euros(emergencyTarget)})` : ''}</button>
              <button className="chip" onClick={() => startNew({ title: 'Down payment for a home', kind: 'home_purchase', funded_by: 'any', target_date: inMonths(60) })}>Buy a home</button>
              {hasProperty && <button className="chip" onClick={() => startNew({ title: 'Sell my rented property', kind: 'property_sale', target_date: inMonths(48) })}>Sell my rented property</button>}
              <button className="chip" onClick={() => startNew({ title: 'Retirement savings', kind: 'retirement', funded_by: 'pea', target_date: inMonths(240) })}>Retirement</button>
              <button className="chip" onClick={() => startNew({ title: 'Save as much as possible', kind: 'savings' })}>Save as much as possible</button>
            </div>
          </div>
        )}

        {HORIZONS.map((horizon) => {
          const goals = data.goals.filter((goal) => goal.horizon === horizon.key)
          if (!goals.length) return null
          return (
            <div key={horizon.key} style={{ marginTop: 12 }}>
              <div className="small muted" style={{ marginBottom: 4 }}>{horizon.label}</div>
              {goals.map((goal) => {
                const progress = goal.progress
                const ratio = progress && goal.target_amount ? Math.max(0, Math.min(1, progress.projected_at_date / goal.target_amount)) : 0
                return (
                  <div className="reco" key={goal.id}>
                    <div>
                      <div className="title">
                        {goal.title} <span className="chip">{KIND_LABEL[goal.kind]}</span>
                        {PRIORITY_LABEL[goal.priority] && <span className="small muted"> {PRIORITY_LABEL[goal.priority]}</span>}
                      </div>
                      <div className="small muted">
                        {goal.target_amount ? `Target ${euros(goal.target_amount)}` : 'No amount'}{goal.target_date ? ` · by ${monthLabel(goal.target_date)}` : ''}
                        {goal.target_amount ? ` · funded by ${FUNDED_LABEL[goal.funded_by]}` : ''}
                      </div>
                      {progress && (
                        <div style={{ marginTop: 6, maxWidth: 420 }}>
                          <div className="progress"><div style={{ width: `${ratio * 100}%`, background: progress.on_track ? 'var(--positive)' : 'var(--expense)' }} /></div>
                          <div className="small" style={{ marginTop: 4 }}>
                            Projected {euros(progress.projected_at_date)} by {monthLabel(goal.target_date)}:{' '}
                            {progress.beyond_projection ? <span className="muted">beyond the projection</span>
                              : progress.on_track ? <span className="positive">on track</span> : <span className="negative">{euros(progress.gap)} short</span>}
                            {progress.reached_month && !progress.on_track ? <span className="muted"> · reached in {monthLabel(progress.reached_month)}</span> : null}
                          </div>
                        </div>
                      )}
                      {goal.notes && <div className="small muted" style={{ marginTop: 4 }}>{goal.notes}</div>}
                      {goal.kind === 'property_sale' && <div className="small muted" style={{ marginTop: 4 }}>Modelled below once a sale date is set in the assumptions.</div>}
                      {goal.kind === 'home_purchase' && <div className="small muted" style={{ marginTop: 4 }}>What you could afford is modelled below once a purchase date is set.</div>}
                    </div>
                    <div className="inline-form">
                      <button className="small" onClick={() => startEdit(goal)}>Edit</button>
                      <button className="small danger" onClick={async () => { if (confirm('Delete this goal?')) { await api.goals.remove(goal.id); plan.reload() } }}>Delete</button>
                    </div>
                  </div>
                )
              })}
            </div>
          )
        })}

        {editing && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <h2>{editing.id === null ? 'New goal' : 'Edit goal'}</h2>
            {error && <div className="alert error">{error}</div>}
            <div className="grid cols-2">
              <label className="small">Title<br /><input style={{ width: '100%' }} value={editing.form.title} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, title: event.target.value } })} /></label>
              <label className="small">Type<br />
                <select value={editing.form.kind} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, kind: event.target.value as GoalKind } })}>
                  {Object.entries(KIND_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select>
              </label>
              <label className="small">Target amount (€, optional)<br /><input style={{ width: '100%' }} value={editing.form.target_amount} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, target_amount: event.target.value } })} /></label>
              <label className="small">Target date (optional)<br /><input style={{ width: '100%' }} type="date" value={editing.form.target_date} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, target_date: event.target.value } })} /></label>
              <label className="small">Funded by<br />
                <select value={editing.form.funded_by} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, funded_by: event.target.value } })}>
                  {Object.entries(FUNDED_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select>
              </label>
              <label className="small">Priority<br />
                <select value={editing.form.priority} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, priority: event.target.value } })}>
                  <option value="1">High</option><option value="2">Normal</option><option value="3">Low</option>
                </select>
              </label>
            </div>
            <label className="small">Notes<br /><textarea style={{ width: '100%' }} rows={2} value={editing.form.notes} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, notes: event.target.value } })} /></label>
            <p className="small muted">With an amount and a date, the goal is checked against the projection below. Without them it is simply a reminder of what you are aiming for.</p>
            <div className="inline-form"><button className="primary" onClick={saveGoal}>Save goal</button><button onClick={() => setEditing(null)}>Cancel</button></div>
          </div>
        )}
      </div>

      {!hasData && (
        <div className="card">
          <h2>The projection</h2>
          <p className="muted">There is nothing to project yet. Add your accounts, payslips, credits and bank statements first (see <a href="/start">Get started</a>): the projection then uses your real income, spending and savings, and tells you whether each goal is on track.</p>
        </div>
      )}
      {hasData && (
        <>
      <h2 style={{ marginTop: 24 }}>The projection</h2>
      <div className="grid cols-4">
        <div className="card stat"><div className="label">This coming month</div><div className={`value ${first.surplus >= 0 ? 'positive' : 'negative'}`}>{euros(first.surplus)}</div>
          <div className="small muted">left after everything, incl. credits</div></div>
        <div className="card stat"><div className="label">Turns positive</div><div className="value">{monthLabel(milestones.first_surplus_month)}</div>
          <div className="small muted">{milestones.overdraft_cleared_month ? `investing starts ${monthLabel(milestones.overdraft_cleared_month)}` : 'no month with money left in the projection'}</div></div>
        <div className="card stat"><div className="label">Steady surplus</div><div className="value positive">{euros(steady)}</div>
          <div className="small muted">per month in year two</div></div>
        <div className="card stat"><div className="label">Savings in 2 years</div><div className="value">{euros(milestones.savings_in_24_months)}</div>
          <div className="small muted">{euros(milestones.savings_in_12_months)} after 1 year, {euros(milestones.savings_in_36_months)} after 3</div></div>
      </div>

      <div className="card">
        <h2>What is left each month</h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} stackOffset="sign" maxBarSize={14}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(month: string) => monthLabel(month)} minTickGap={50} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
            <Tooltip formatter={(amount, name) => [formatMoney(Number(amount)), name]} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Bar dataKey="positive" name="Left to invest" stackId="s" fill="var(--positive)" />
            <Bar dataKey="negative" name="Shortfall" stackId="s" fill="var(--negative)" />
          </BarChart>
        </ResponsiveContainer>
        <p className="small muted">
          Income used: {euros(context.salary_net)} salary{context.rent_net ? ` + ${euros(context.rent_net)} rent after agency costs` : ''}.
          Everyday spending: {euros(context.core_spending + context.flat_costs)} a month without any credit.
          Credits cost {euros(data.projection[0].debt_service)} next month, {euros(data.projection[5]?.debt_service)} in 6 months and {euros(data.projection[11]?.debt_service)} in 12 months: when they end, that money is yours.
        </p>
      </div>

      <div className="card">
        <h2>Your savings over time</h2>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data.projection}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(month: string) => monthLabel(month)} minTickGap={50} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} tickFormatter={(amount: number) => `${Math.round(amount / 1000)}k`} />
            <Tooltip formatter={(amount) => formatMoney(Number(amount))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <Legend />
            <Area type="monotone" dataKey="pea" name="PEA" stackId="a" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.6} />
            <Area type="monotone" dataKey="cto" name="CTO" stackId="a" stroke="#8f5fa0" fill="#8f5fa0" fillOpacity={0.6} />
            <Area type="monotone" dataKey="av_balance" name="Assurance-vie" stackId="a" stroke="#3f8fb0" fill="#3f8fb0" fillOpacity={0.6} />
            <Area type="monotone" dataKey="livrets" name="Livrets" stackId="a" stroke="var(--savings)" fill="var(--savings)" fillOpacity={0.6} />
            <Area type="monotone" dataKey="sale_pot" name="Sale proceeds" stackId="a" stroke="var(--expense)" fill="var(--expense)" fillOpacity={0.6} />
          </AreaChart>
        </ResponsiveContainer>
        <p className="small muted">Contributions only plus the return you set below (0 % by default: a floor, not a forecast). Monthly savings are split {Math.round((settings.split_pea / splitTotal) * 100)} % PEA, {Math.round((settings.split_cto / splitTotal) * 100)} % CTO, {Math.round((settings.split_livrets / splitTotal) * 100)} % livrets{settings.av_monthly ? `, plus ${euros(settings.av_monthly)} a month into the assurance-vie` : ''}.</p>
      </div>

      <div className="card">
        <h2>If your housing cost changes</h2>
        <p className="small muted">You pay about {euros(context.housing_cost)} a month today. What a different rent does to your savings:</p>
        <table>
          <thead><tr><th>Housing cost</th><th>Left next month</th><th>Left after 12 months</th><th>Savings in 2 years</th></tr></thead>
          <tbody>
            {data.housing_scenarios.map((scenario) => (
              <tr key={scenario.delta} style={scenario.delta === settings.housing_delta ? { fontWeight: 700 } : undefined}>
                <td>{euros(scenario.monthly_cost)}{scenario.delta ? <span className="muted small"> (+{scenario.delta})</span> : ''}</td>
                <td className={`amount ${scenario.surplus_next_month < 0 ? 'negative' : ''}`}>{euros(scenario.surplus_next_month)}</td>
                <td className="amount">{euros(scenario.surplus_in_12_months)}</td>
                <td className="amount">{euros(scenario.savings_in_24_months)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.sale && (
        <div className="card">
          <h2>Selling {data.property_name}</h2>
          <p className="small">On {monthLabel(data.sale.date)} at {euros(data.sale.price)} ({data.sale.price_basis}): after the loan ({euros(data.sale.loan_balance)}), the agent ({euros(data.sale.agent_fee)}), the early-repayment indemnity ({euros(data.sale.indemnity)}) and an estimated gain tax ({euros(data.sale.gain_tax)}),
            you would {data.sale.net_proceeds >= 0 ? 'receive' : 'have to bring'} <strong className={data.sale.net_proceeds >= 0 ? 'positive' : 'negative'}>{euros(Math.abs(data.sale.net_proceeds))}</strong>.</p>
        </div>
      )}

      {data.purchase && (
        <>
          <h2 style={{ marginTop: 24 }}>Buying a home, {monthLabel(data.purchase.date)}</h2>
          <p className="small muted">The bank looks at net income before tax{hasProperty ? ` plus ${settings.rent_weight_pct} % of the rent` : ''} and lets all loan payments reach {settings.max_debt_ratio_pct} % of it. Down payment: {settings.purchase_savings_share_pct} % of your PEA, CTO and livrets then ({euros(data.purchase.savings_pool)}){hasProperty ? ', plus the proceeds of the sale if you sell' : ''}.</p>
          <div className="grid cols-2">
            {data.purchase.keep_flat && <Affordability title={`If you keep ${data.property_name ?? 'your property'}`} data={data.purchase.keep_flat} />}
            {data.purchase.sell_flat && <Affordability title={`If you sell ${data.property_name ?? 'it'} first`} data={data.purchase.sell_flat} />}
            {data.purchase.without_flat && <Affordability title="What you could afford" data={data.purchase.without_flat} />}
          </div>
        </>
      )}

        </>
      )}

      <div className="card">
        <h2>Assumptions</h2>
        {saved && <div className="alert success">Saved, the projection is recomputed.</div>}
        {data.split_check !== 100 && <div className="alert error">The three savings percentages add up to {data.split_check} %; they are scaled to 100 %.</div>}
        <div className="small muted" style={{ marginBottom: 4 }}>Where savings go</div>
        <div className="grid cols-2">
          {field('split_pea', 'PEA (%)')}{field('split_cto', 'CTO / brokerage (%)')}{field('split_livrets', 'Livrets (%)')}
          {field('av_monthly', 'Fixed assurance-vie plan (€ / month)')}{field('livrets_target', 'Fill the livrets first up to (€)')}{field('expected_return_pct', 'Yearly return assumed (%)')}
        </div>
        <div className="small muted" style={{ margin: '12px 0 4px' }}>Your month</div>
        <div className="grid cols-2">{field('housing_delta', 'Extra housing cost vs today (€ / month)')}{field('new_credit_monthly', 'New instalment purchases (€ / month)')}</div>

        {hasProperty && (
          <div style={{ marginTop: 12 }}>
            <label className="small"><input type="checkbox" checked={sellEnabled} onChange={(event) => { setSellOn(event.target.checked); setSaved(false) }} /> I plan to sell {data.property_name}</label>
            {sellEnabled && <div className="grid cols-2" style={{ marginTop: 4 }}>{field('sale_date', 'Sale date', 'date')}{field('sale_price', 'Sale price (€, empty = your estimate or purchase price)')}{field('sale_agent_fee_pct', 'Agent fee (%)')}</div>}
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <label className="small"><input type="checkbox" checked={buyEnabled} onChange={(event) => { setBuyOn(event.target.checked); setSaved(false) }} /> I plan to buy a home</label>
          {buyEnabled && (
            <div className="grid cols-2" style={{ marginTop: 4 }}>
              {field('purchase_date', 'Purchase date', 'date')}{field('purchase_price', 'Price (€, empty = show what is affordable)')}
              {field('purchase_savings_share_pct', 'Share of PEA + CTO + livrets used as down payment (%)')}{field('loan_rate_pct', 'Loan rate (%)')}
              {field('loan_years', 'Duration (years)')}{field('loan_insurance_pct', 'Loan insurance (% a year)')}{field('notary_fees_pct', 'Notary fees (% of price)')}
              {hasProperty && field('rent_weight_pct', 'Share of rent the bank counts (%)')}{field('max_debt_ratio_pct', 'Maximum debt ratio (%)')}
            </div>
          )}
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="primary" onClick={saveSettings} disabled={Object.keys(settingsForm).length === 0 && sellOn === null && buyOn === null}>Save and recompute</button>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>Not included: salary raises, rent revisions, tax effects (PER, gains), bonuses or a change of job. Using PEA money for a down payment can close the plan if it is under 5 years old.</p>
      </div>
    </div>
  )
}
