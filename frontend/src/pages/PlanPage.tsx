import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney, type PlanAffordability, type PlanData, type PlanSettingsData } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number | null | undefined) => (value === null || value === undefined ? '–' : formatMoney(Math.round(value)).replace(/,00$/, ''))
const monthLabel = (month: string | null) => (month ? new Date(month + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '–')

type Field = { key: keyof PlanSettingsData; label: string; step?: string; type?: string }
const FIELD_GROUPS: { title: string; fields: Field[] }[] = [
  { title: 'Where savings go', fields: [
    { key: 'split_pea', label: 'PEA (%)' }, { key: 'split_cto', label: 'CTO / Trade Republic (%)' }, { key: 'split_livrets', label: 'Livrets (%)' },
    { key: 'av_monthly', label: 'Assurance-vie plan (€ / month)' }, { key: 'livrets_target', label: 'Fill the livrets first up to (€)' },
    { key: 'expected_return_pct', label: 'Yearly return assumed (%)' },
  ] },
  { title: 'Your month', fields: [
    { key: 'housing_delta', label: 'Extra housing cost vs today (€ / month)' }, { key: 'new_credit_monthly', label: 'New instalment purchases (€ / month)' },
  ] },
  { title: 'Sale of the Saint-Cyr flat', fields: [
    { key: 'sale_date', label: 'Sale date', type: 'date' }, { key: 'sale_price', label: 'Sale price (€, empty = purchase price)' }, { key: 'sale_agent_fee_pct', label: 'Agent fee (%)' },
  ] },
  { title: 'Home in Aix', fields: [
    { key: 'purchase_date', label: 'Purchase date', type: 'date' }, { key: 'purchase_price', label: 'Price (€, empty = show what is affordable)' },
    { key: 'purchase_savings_share_pct', label: 'Share of PEA + CTO + livrets used as down payment (%)' }, { key: 'loan_rate_pct', label: 'Loan rate (%)' },
    { key: 'loan_years', label: 'Duration (years)' }, { key: 'loan_insurance_pct', label: 'Loan insurance (% a year)' }, { key: 'notary_fees_pct', label: 'Notary fees (% of price)' },
    { key: 'rent_weight_pct', label: 'Share of rent the bank counts (%)' }, { key: 'max_debt_ratio_pct', label: 'Maximum debt ratio (%)' },
  ] },
]

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
          <tr><td><strong>Highest price you could reach</strong></td><td className={`amount ${data.price_max < 150000 ? 'negative' : 'positive'}`}><strong>{euros(data.price_max)}</strong></td></tr>
        </tbody>
      </table>
      <table style={{ marginTop: 12 }}>
        <thead><tr><th>Price</th><th>Payment</th><th>Debt ratio</th><th /></tr></thead>
        <tbody>
          {data.grid.map((row) => (
            <tr key={row.price}>
              <td>{euros(row.price)}</td>
              <td className="amount">{euros(row.payment)}</td>
              <td className={row.feasible ? 'positive' : 'negative'}>{row.ratio !== null ? `${Math.round(row.ratio * 100)} %` : '–'}</td>
              <td className="small muted">{row.feasible ? 'fits' : 'too high'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PlanPage() {
  const plan = useLoad(() => api.plan.get())
  const [form, setForm] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  if (plan.error) return <div className="alert error">{plan.error}</div>
  const data: PlanData | null = plan.data
  if (!data) return <p className="muted">Computing the plan…</p>

  const { settings, milestones, context } = data
  const splitTotal = settings.split_pea + settings.split_cto + settings.split_livrets || 1
  const steady = milestones.steady_surplus ?? 0
  const sale = data.sale
  const allocation = [
    { label: 'PEA', value: (steady * settings.split_pea) / splitTotal },
    { label: 'CTO (Trade Republic)', value: (steady * settings.split_cto) / splitTotal },
    { label: 'Livret A / LDDS', value: (steady * settings.split_livrets) / splitTotal },
    { label: 'Assurance-vie plan (fixed)', value: settings.av_monthly },
  ]
  const chartData = data.projection.map((row) => ({ ...row, surplus_positive: Math.max(row.surplus, 0), surplus_negative: Math.min(row.surplus, 0) }))

  async function save() {
    const payload: Record<string, number | string | boolean | null> = {}
    for (const [key, raw] of Object.entries(form)) {
      if (key === 'sale_price' && raw.trim() === '') payload.clear_sale_price = true
      else if (key === 'purchase_price' && raw.trim() === '') payload.clear_purchase_price = true
      else if (key === 'sale_date' || key === 'purchase_date') payload[key] = raw || null
      else if (raw.trim() !== '') payload[key] = Number(raw.replace(',', '.'))
    }
    await api.plan.update(payload as Partial<PlanSettingsData>)
    setForm({})
    setSaved(true)
    plan.reload()
  }

  const valueOf = (key: keyof PlanSettingsData) => (form[key] !== undefined ? form[key] : settings[key] === null ? '' : String(settings[key]))

  return (
    <div>
      <h1>Goals &amp; plan</h1>
      <p className="muted small">Built from your own numbers and the priorities you gave: save as much as possible into PEA and CTO, the rest into livrets, keep the assurance-vie plan as it is, sell Saint-Cyr around 2029-2030 and buy in Aix. Every assumption is editable at the bottom.</p>

      <div className="grid cols-3" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="card">
          <div className="small muted">SHORT TERM · next 6 months</div>
          <h2>Stop the monthly deficit</h2>
          <p className="small">Today your month ends about {euros(data.projection[0].surplus)} {data.projection[0].surplus < 0 ? 'short' : 'to the good'}. It turns positive in <strong>{monthLabel(milestones.first_surplus_month)}</strong> as the small credits end, and the overdrafts are cleared by <strong>{monthLabel(milestones.overdraft_cleared_month)}</strong>. Until then nothing can be invested.</p>
        </div>
        <div className="card">
          <div className="small muted">MEDIUM TERM · 2027 to 2029</div>
          <h2>Invest {euros(steady)} a month</h2>
          <p className="small">Once the credits are gone you keep about <strong>{euros(steady)}</strong> a month on top of the {euros(settings.av_monthly)} for the assurance-vie. Contributions alone take your savings to <strong>{euros(milestones.savings_2027_12)}</strong> at the end of 2027, <strong>{euros(milestones.savings_2028_12)}</strong> at the end of 2028 and <strong>{euros(milestones.savings_2029_06)}</strong> in mid-2029, with {settings.expected_return_pct} % a year of market return assumed.</p>
        </div>
        <div className="card">
          <div className="small muted">LONG TERM · 2029 to 2030</div>
          <h2>Sell Saint-Cyr, buy in Aix</h2>
          <p className="small">
            {sale ? <>Selling on {monthLabel(sale.date.slice(0, 7))} at {euros(sale.price)} ({sale.price_basis}) leaves <strong className={sale.net_proceeds >= 0 ? 'positive' : 'negative'}>{euros(sale.net_proceeds)}</strong> after the mortgage ({euros(sale.loan_balance)}), the agent and the early-repayment indemnity. </> : null}
            Without selling you could only reach about <strong className="negative">{euros(data.purchase.keep_flat.price_max)}</strong>; after selling, about <strong className="positive">{euros(data.purchase.sell_flat.price_max)}</strong>.
          </p>
        </div>
      </div>

      <div className="card">
        <h2>What is left each month, and why it grows</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} stackOffset="sign" maxBarSize={14}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(month: string) => monthLabel(month).replace(' ', ' ')} minTickGap={50} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
            <Tooltip formatter={(value, name) => [formatMoney(Number(value)), name]} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Bar dataKey="surplus_positive" name="Left to invest" stackId="s" fill="var(--positive)" />
            <Bar dataKey="surplus_negative" name="Shortfall" stackId="s" fill="var(--negative)" />
          </BarChart>
        </ResponsiveContainer>
        <p className="small muted">Your credits cost {euros(data.projection[0].debt_service)} next month, {euros(data.projection.find((row) => row.month === '2027-03')?.debt_service)} in March 2027 and {euros(data.projection.find((row) => row.month === '2027-09')?.debt_service)} from September 2027: that drop is where the savings come from. Details on <Link to="/loans">Loans &amp; credits</Link>.
          Income used: {euros(context.salary_net)} salary + {euros(context.rent_net)} rent after agency costs. Spending used: {euros(context.core_spending + context.flat_costs)} a month without any credit.</p>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Where the monthly {euros(steady)} goes</h2>
          <table>
            <tbody>
              {allocation.map((entry) => <tr key={entry.label}><td>{entry.label}</td><td className="amount">{euros(entry.value)} / month</td></tr>)}
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>
            Livrets only receive money once the overdraft is cleared, so the emergency cash stays near {euros(context.balances.livrets)} until {monthLabel(milestones.overdraft_cleared_month)}.
            {settings.livrets_target === 0 && <> Your plan keeps no buffer first; if you want one, set “Fill the livrets first up to” below. It is your call, but a buffer is what stops the next overdraft.</>}
          </p>
        </div>

        <div className="card">
          <h2>A flat share instead of your room</h2>
          <p className="small muted">You pay about {euros(context.housing_cost)} a month today (room and parking). What a higher rent does to your savings:</p>
          <table>
            <thead><tr><th>Housing cost</th><th>Left next month</th><th>Left from Sept 2027</th><th>Savings end 2028</th></tr></thead>
            <tbody>
              {data.housing_scenarios.map((scenario) => (
                <tr key={scenario.delta} style={scenario.delta === settings.housing_delta ? { fontWeight: 700 } : undefined}>
                  <td>{euros(scenario.monthly_cost)}{scenario.delta ? <span className="muted small"> (+{scenario.delta})</span> : ''}</td>
                  <td className={`amount ${scenario.surplus_next_month < 0 ? 'negative' : ''}`}>{euros(scenario.surplus_next_month)}</td>
                  <td className="amount">{euros(scenario.surplus_2027_09)}</td>
                  <td className="amount">{euros(scenario.savings_end_2028)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>Every 100 € of extra rent costs about {euros((data.housing_scenarios[0].savings_end_2028 ?? 0) - (data.housing_scenarios[1].savings_end_2028 ?? 0))} of savings by the end of 2028. From September 2027, a housing cost of {euros(data.housing_scenarios.find((scenario) => scenario.delta === 200)?.monthly_cost)} would still leave {euros(data.housing_scenarios.find((scenario) => scenario.delta === 200)?.surplus_2027_09)} a month.</p>
        </div>
      </div>

      <div className="card">
        <h2>Your savings over time</h2>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={data.projection}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(month: string) => monthLabel(month)} minTickGap={50} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
            <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <Legend />
            <Area type="monotone" dataKey="pea" name="PEA" stackId="a" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.6} />
            <Area type="monotone" dataKey="cto" name="CTO" stackId="a" stroke="#8f5fa0" fill="#8f5fa0" fillOpacity={0.6} />
            <Area type="monotone" dataKey="av_balance" name="Assurance-vie" stackId="a" stroke="#3f8fb0" fill="#3f8fb0" fillOpacity={0.6} />
            <Area type="monotone" dataKey="livrets" name="Livrets" stackId="a" stroke="var(--savings)" fill="var(--savings)" fillOpacity={0.6} />
            <Area type="monotone" dataKey="sale_pot" name="Sale proceeds" stackId="a" stroke="var(--expense)" fill="var(--expense)" fillOpacity={0.6} />
          </AreaChart>
        </ResponsiveContainer>
        <p className="small muted">Contributions only, plus the market return you set below (0 % by default, so this is a floor, not a forecast). Using PEA money for the down payment can close the plan if it is under 5 years old, and CTO gains are taxed on withdrawal; neither is counted here.</p>
      </div>

      <h2 style={{ marginTop: 24 }}>Buying in Aix, {monthLabel(data.purchase.date.slice(0, 7))}</h2>
      <p className="small muted">The bank looks at net income before tax plus {settings.rent_weight_pct} % of the rent, and lets total loan payments reach {settings.max_debt_ratio_pct} % of it. Down payment: {settings.purchase_savings_share_pct} % of your PEA, CTO and livrets then ({euros(data.purchase.savings_pool)}), plus the proceeds of the sale if you sell.</p>
      <div className="grid cols-2">
        <Affordability title="If you keep Saint-Cyr" data={data.purchase.keep_flat} />
        <Affordability title="If you sell Saint-Cyr first" data={data.purchase.sell_flat} />
      </div>

      <div className="card">
        <h2>Assumptions</h2>
        {saved && <div className="alert success">Saved, the plan is recomputed.</div>}
        {data.split_check !== 100 && <div className="alert error">The three savings percentages add up to {data.split_check} %; they are scaled to 100 %.</div>}
        {FIELD_GROUPS.map((group) => (
          <div key={group.title} style={{ marginBottom: 12 }}>
            <div className="small muted" style={{ marginBottom: 4 }}>{group.title}</div>
            <div className="grid cols-2">
              {group.fields.map((field) => (
                <label className="small" key={field.key}>{field.label}<br />
                  <input style={{ width: '100%' }} type={field.type ?? 'text'} value={valueOf(field.key)} onChange={(event) => { setSaved(false); setForm({ ...form, [field.key]: event.target.value }) }} />
                </label>
              ))}
            </div>
          </div>
        ))}
        <button className="primary" onClick={save} disabled={Object.keys(form).length === 0}>Save and recompute</button>
        <p className="small muted" style={{ marginTop: 8 }}>
          Not included: salary raises, rent revisions, tax effects (PER, furnished-rental regime, gains), a bonus, or a change of job. The 2029 sale price defaults to what you paid; set your own estimate for a realistic figure.
        </p>
      </div>
    </div>
  )
}
