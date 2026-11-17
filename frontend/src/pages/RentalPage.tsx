import { useState } from 'react'
import HelpBox from '../components/HelpBox'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatDate, formatMoney, type PropertyData, type SaleScenario } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const percent = (value: number | null, digits = 1) => (value === null ? '–' : `${(value * 100).toFixed(digits).replace('.', ',')} %`)
const monthLabel = (month: string) => new Date(month + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

const EDITABLE: { key: keyof PropertyData; label: string }[] = [
  { key: 'monthly_rent', label: 'Rent per month (€, excl. charges)' },
  { key: 'monthly_charges', label: 'Charge provisions (€)' },
  { key: 'management_fee_rate', label: 'Agency fee (% incl. VAT of rent + charges)' },
  { key: 'rent_insurance_rate', label: 'Guaranteed-rent insurance (%)' },
  { key: 'syndic_quarterly', label: 'Co-ownership call per quarter (€)' },
  { key: 'property_tax_yearly', label: 'Property tax per year (€)' },
  { key: 'market_value', label: 'Your estimate of the market value (€)' },
  { key: 'furnishing_and_works', label: 'Furnishing and works paid (€)' },
]

function PropertyCard({ property, onChanged }: { property: PropertyData; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const [price, setPrice] = useState(property.market_value ? String(property.market_value) : '')
  const [agentFee, setAgentFee] = useState('5')
  const [sale, setSale] = useState<SaleScenario | null>(null)
  const [error, setError] = useState<string | null>(null)

  const chartData = property.months.map((row) => ({ month: row.month, rent: row.rent, mortgage: row.mortgage, costs: row.costs }))
  const negative = property.monthly_result < 0

  async function save() {
    const payload: Record<string, number | null> = {}
    for (const field of EDITABLE) {
      const raw = form[field.key as string]
      if (raw !== undefined) payload[field.key as string] = raw === '' ? null : Number(raw.replace(',', '.'))
    }
    await api.properties.update(property.id, payload as Partial<PropertyData>)
    setEditing(false)
    onChanged()
  }

  async function runSale() {
    setError(null)
    try {
      setSale(await api.properties.sale(property.id, Number(price.replace(',', '.')), Number(agentFee.replace(',', '.')) || 0))
    } catch (saleError) {
      setError((saleError as Error).message)
    }
  }

  return (
    <div>
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{property.name}</h2>
          <span className="spacer" />
          <button onClick={() => { setForm({}); setEditing(!editing) }}>{editing ? 'Close' : 'Edit terms'}</button>
        </div>
        <div className="chips">
          {property.address && <span className="chip">{property.address}</span>}
          {property.furnished && <span className="chip">Furnished</span>}
          {property.surface_m2 && <span className="chip">{property.surface_m2} m²</span>}
          {property.lease_start && <span className="chip">Let since {formatDate(property.lease_start)}</span>}
          {property.agency && <span className="chip">{property.agency}</span>}
          {property.purchase_price && <span className="chip">Bought {euros(property.purchase_price)}{property.purchase_date ? ` on ${formatDate(property.purchase_date)}` : ''}</span>}
        </div>
        {editing && (
          <div style={{ marginTop: 12 }}>
            <div className="grid cols-2">
              {EDITABLE.map((field) => (
                <label className="small" key={field.key}>{field.label}<br />
                  <input style={{ width: '100%' }} defaultValue={property[field.key] === null ? '' : String(property[field.key])}
                    onChange={(event) => setForm({ ...form, [field.key]: event.target.value })} />
                </label>
              ))}
            </div>
            <div className="inline-form" style={{ marginTop: 8 }}><button className="primary" onClick={save}>Save</button></div>
          </div>
        )}
        {property.notes && <p className="small muted" style={{ marginTop: 8 }}>{property.notes}</p>}
      </div>

      <div className="grid cols-4">
        <div className="card stat"><div className="label">Monthly result</div>
          <div className={`value ${negative ? 'negative' : 'positive'}`}>{euros(property.monthly_result)}</div>
          <div className="small muted">rent minus all costs and the mortgage, before tax</div></div>
        <div className="card stat"><div className="label">Lands on your account</div><div className="value">{euros(property.net_from_agency)}</div>
          <div className="small muted">of {euros(property.monthly_rent + property.monthly_charges)} collected, after agency and insurance</div></div>
        <div className="card stat"><div className="label">Out of pocket since {property.months[0] ? monthLabel(property.months[0].month) : '–'}</div>
          <div className="value negative">{euros(property.totals.net)}</div>
          <div className="small muted">rent received in {property.months_with_rent} of {property.months.length} months</div></div>
        <div className="card stat"><div className="label">Yield</div><div className="value">{percent(property.yields.gross)}</div>
          <div className="small muted">gross; {percent(property.yields.net_of_costs)} after costs, mortgage rate {property.yields.loan_rate !== null ? percent(property.yields.loan_rate) : '–'}</div></div>
      </div>

      {property.checks.length > 0 && (
        <div className="card">
          <h2>Worth your attention</h2>
          {property.checks.map((check) => (
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

      <div className="grid cols-2">
        <div className="card">
          <h2>A normal month, from the lease</h2>
          <table>
            <tbody>
              {property.lines.map((line) => (
                <tr key={line.label}><td>{line.label}</td><td className={`amount ${line.amount >= 0 ? 'positive' : ''}`}>{formatMoney(line.amount)}</td></tr>
              ))}
              <tr><td><strong>Result</strong></td><td className={`amount ${negative ? 'negative' : 'positive'}`}><strong>{formatMoney(property.monthly_result)}</strong></td></tr>
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>
            Before the mortgage the flat leaves {formatMoney(property.operating_result)} a month. The mortgage balance is {property.loan ? euros(property.loan.balance) : '–'}
            {property.loan ? ` at ${property.loan.rate} % for ${property.loan.remaining_months} more months` : ''}; see <Link to="/loans">Loans &amp; credits</Link> for what a lower rate or a prepayment would change.
          </p>
          <div className="small" style={{ marginTop: 8 }}>
            <div className="muted" style={{ marginBottom: 4 }}>What moves the result</div>
            {property.levers.map((lever) => <div key={lever.label}>{lever.label}: <span className="positive">+{euros(lever.monthly)} / month</span></div>)}
          </div>
        </div>

        <div className="card">
          <h2>If you sold it</h2>
          <p className="small muted">Enter the price you think you could get. Nothing here is a valuation.</p>
          <div className="inline-form" style={{ marginBottom: 8 }}>
            <label className="small">Sale price (€) <input style={{ width: 100 }} value={price} onChange={(event) => setPrice(event.target.value)} /></label>
            <label className="small">Agent fee (%) <input style={{ width: 50 }} value={agentFee} onChange={(event) => setAgentFee(event.target.value)} /></label>
            <button className="primary" onClick={runSale} disabled={!price}>Compute</button>
          </div>
          {error && <div className="alert error">{error}</div>}
          {sale && (
            <table>
              <tbody>
                <tr><td>Sale price</td><td className="amount">{formatMoney(sale.price)}</td></tr>
                <tr><td>Agent fee</td><td className="amount">−{formatMoney(sale.agent_fee)}</td></tr>
                <tr><td>Mortgage to repay</td><td className="amount">−{formatMoney(sale.loan_balance)}</td></tr>
                <tr><td>Early-repayment indemnity (legal maximum)</td><td className="amount">−{formatMoney(sale.early_repayment_indemnity_max)}</td></tr>
                <tr><td>Capital gains tax (estimate)</td><td className="amount">−{formatMoney(sale.estimated_gain_tax)}</td></tr>
                <tr><td><strong>{sale.net_proceeds >= 0 ? 'You would receive' : 'You would have to bring'}</strong></td>
                  <td className={`amount ${sale.net_proceeds >= 0 ? 'positive' : 'negative'}`}><strong>{formatMoney(Math.abs(sale.net_proceeds))}</strong></td></tr>
              </tbody>
            </table>
          )}
          {sale && sale.months_of_losses_equivalent !== null && (
            <p className="small muted" style={{ marginTop: 8 }}>That equals about {sale.months_of_losses_equivalent} months of what the flat costs you today ({euros(-sale.monthly_result_if_kept)} a month).</p>
          )}
          {sale && <p className="small muted">{sale.note}</p>}
        </div>
      </div>

      <div className="card">
        <h2>What actually happened, month by month</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} stackOffset="sign" maxBarSize={40}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={monthLabel} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
            <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <Legend />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Bar dataKey="rent" name="Rent received" stackId="flow" fill="var(--positive)" />
            <Bar dataKey="mortgage" name="Mortgage" stackId="flow" fill="var(--accent)" />
            <Bar dataKey="costs" name="Co-ownership, tax, furnishing" stackId="flow" fill="var(--expense)" />
          </BarChart>
        </ResponsiveContainer>
        <p className="small muted">
          Taken from your transactions: rent from the rental income category, mortgage from the mortgage category, other costs from the property category.
          The big bars are one-offs: the kitchen cheques in November and December, and the cost of moving the mortgage in May.
        </p>
      </div>
    </div>
  )
}

function NewPropertyForm({ onCreated }: { onCreated: () => void }) {
  const categories = useLoad(() => api.categories.list())
  const loans = useLoad(() => api.loans.list())
  const [form, setForm] = useState<Record<string, string>>({ furnished: 'no' })
  const [error, setError] = useState<string | null>(null)
  const pick = (kind: string, word: string) => categories.data?.find((category) => category.kind === kind && category.name.toLowerCase().includes(word))?.id
  const value = (key: string, fallback = '') => form[key] ?? fallback
  const set = (key: string, text: string) => setForm({ ...form, [key]: text })
  const number = (key: string) => (form[key] && form[key] !== '' ? Number(form[key].replace(',', '.')) : undefined)
  const input = (key: string, label: string, placeholder = '') => (
    <label className="small" key={key}>{label}<br /><input style={{ width: '100%' }} placeholder={placeholder} value={value(key)} onChange={(event) => set(key, event.target.value)} /></label>
  )
  const categorySelect = (key: string, label: string, kind: string, word: string) => (
    <label className="small" key={key}>{label}<br />
      <select style={{ width: '100%' }} value={value(key, String(pick(kind, word) ?? ''))} onChange={(event) => set(key, event.target.value)}>
        <option value="">none</option>
        {categories.data?.filter((category) => category.kind === kind).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
      </select>
    </label>
  )

  async function create() {
    setError(null)
    try {
      if (!value('name').trim()) throw new Error('Give the property a name')
      const loanId = value('loan_id')
      await api.properties.create({
        name: value('name').trim(), address: value('address') || null, furnished: value('furnished') === 'yes', surface_m2: number('surface_m2'),
        purchase_price: number('purchase_price'), purchase_date: value('purchase_date') || null,
        monthly_rent: number('monthly_rent') ?? 0, monthly_charges: number('monthly_charges') ?? 0, lease_start: value('lease_start') || null,
        agency: value('agency') || null, management_fee_rate: number('management_fee_rate') ?? 0, rent_insurance_rate: number('rent_insurance_rate') ?? 0,
        syndic_quarterly: number('syndic_quarterly') ?? 0, property_tax_yearly: number('property_tax_yearly') ?? 0,
        loan_id: loanId ? Number(loanId) : null,
        income_category_id: Number(value('income_category_id', String(pick('income', 'rent') ?? ''))) || null,
        cost_category_id: Number(value('cost_category_id', String(pick('expense', 'property') ?? ''))) || null,
        mortgage_category_id: Number(value('mortgage_category_id', String(pick('expense', 'mortgage') ?? ''))) || null,
      })
      onCreated()
    } catch (createError) {
      setError((createError as Error).message)
    }
  }

  return (
    <div className="card">
      <h2>Add a rented property</h2>
      {error && <div className="alert error">{error}</div>}
      <div className="grid cols-2">
        {input('name', 'Name', 'Flat B42, Lyon')}{input('address', 'Address (optional)')}
        {input('monthly_rent', 'Rent per month, excl. charges (€)')}{input('monthly_charges', 'Charge provisions paid by the tenant (€)')}
        {input('purchase_price', 'Purchase price (€)')}{input('purchase_date', 'Purchase date', '2023-10-27')}
        {input('lease_start', 'Lease start', '2026-06-12')}{input('surface_m2', 'Surface (m²)')}
        {input('management_fee_rate', 'Agency fee (% incl. VAT of rent + charges)', '6')}{input('rent_insurance_rate', 'Guaranteed-rent insurance (%)', '3')}
        {input('syndic_quarterly', 'Co-ownership call per quarter (€)')}{input('property_tax_yearly', 'Property tax per year (€)')}
        <label className="small">Furnished<br /><select value={value('furnished', 'no')} onChange={(event) => set('furnished', event.target.value)}><option value="no">no</option><option value="yes">yes</option></select></label>
        <label className="small">Mortgage (from Credits &amp; loans)<br />
          <select style={{ width: '100%' }} value={value('loan_id')} onChange={(event) => set('loan_id', event.target.value)}>
            <option value="">none</option>
            {loans.data?.loans.map((loan) => <option key={loan.id} value={loan.id}>{loan.name}</option>)}
          </select>
        </label>
        {categorySelect('income_category_id', 'Category where the rent arrives', 'income', 'rent')}
        {categorySelect('cost_category_id', 'Category for its costs (co-ownership, tax…)', 'expense', 'property')}
        {categorySelect('mortgage_category_id', 'Category of the mortgage payments', 'expense', 'mortgage')}
      </div>
      <p className="small muted">The categories tell the app which transactions belong to this property, so its real cash flow can be computed. You can edit all of this later.</p>
      <button className="primary" onClick={create}>Add property</button>
    </div>
  )
}

export default function RentalPage() {
  const properties = useLoad(() => api.properties.list())
  if (properties.error) return <div className="alert error">{properties.error}</div>
  if (!properties.data) return <p className="muted">Loading…</p>
  return (
    <div>
      <h1>Rental property</h1>
      <HelpBox title="What is this page for?" open={properties.data.length === 0}>
        If you rent a property out, add it here with its lease terms and agency fees. The app then shows what it really costs or earns each month once the mortgage, agency fee, co-ownership and tax are counted, and models a sale.
        If you do not rent anything out, mark this step as skipped.
      </HelpBox>
      {properties.data.length === 0 && (
        <>
          <NewPropertyForm onCreated={properties.reload} />
          <button onClick={async () => { await api.plan.update({ skipped_property: true }); properties.reload() }}>I do not rent out a property</button>
        </>
      )}
      {properties.data.map((property) => <PropertyCard key={property.id} property={property} onChanged={properties.reload} />)}
    </div>
  )
}
