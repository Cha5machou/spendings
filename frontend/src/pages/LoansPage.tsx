import HelpBox from '../components/HelpBox'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatDate, formatMoney, type Loan, type LoanKind, type PayoffPlan, type WhatIf } from '../api'
import { useLoad } from '../hooks'

const KIND_LABEL: Record<LoanKind, string> = {
  mortgage: 'Mortgage', personal: 'Personal & car loans', revolving: 'Revolving credit', installment: 'Pay-in-instalments (PayPal, Cofidis…)', other: 'Other',
}
const KIND_COLOR: Record<LoanKind, string> = {
  mortgage: 'var(--accent)', personal: 'var(--expense)', revolving: '#8f5fa0', installment: 'var(--savings)', other: 'var(--text-muted)',
}
const KIND_ORDER: LoanKind[] = ['mortgage', 'personal', 'revolving', 'installment', 'other']
const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const monthLabel = (month: string) => new Date(month.slice(0, 7) + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

type FormState = Record<string, string> & { kind: string; is_active: string }

function toForm(loan?: Loan): FormState {
  const text = (value: unknown) => (value === null || value === undefined ? '' : String(value))
  return {
    name: text(loan?.name), lender: text(loan?.lender), kind: loan?.kind ?? 'personal',
    remaining_balance: text(loan?.remaining_balance), balance_date: text(loan?.balance_date), annual_rate: text(loan?.annual_rate),
    taeg: text(loan?.taeg), monthly_payment: text(loan?.monthly_payment), insurance_monthly: text(loan?.insurance_monthly),
    next_payment_date: text(loan?.next_payment_date), payments_remaining: text(loan?.payments_remaining), end_date: text(loan?.end_date),
    original_amount: text(loan?.original_amount), payment_pattern: text(loan?.payment_pattern), notes: text(loan?.notes),
    is_active: loan?.is_active === false ? 'no' : 'yes',
  }
}

function fromForm(form: FormState): Partial<Loan> {
  const number = (key: string) => (form[key] === '' ? null : Number(form[key].replace(',', '.')))
  const required = (key: string) => number(key) ?? 0
  const optionalText = (key: string) => (form[key].trim() === '' ? null : form[key].trim())
  return {
    name: form.name.trim(), lender: optionalText('lender'), kind: form.kind as LoanKind,
    remaining_balance: required('remaining_balance'), balance_date: optionalText('balance_date'), annual_rate: required('annual_rate'),
    taeg: number('taeg'), monthly_payment: required('monthly_payment'), insurance_monthly: required('insurance_monthly'),
    next_payment_date: optionalText('next_payment_date'), payments_remaining: number('payments_remaining'), end_date: optionalText('end_date'),
    original_amount: number('original_amount'), payment_pattern: optionalText('payment_pattern'), notes: optionalText('notes'),
    is_active: form.is_active === 'yes',
  }
}

const FIELDS: { key: string; label: string; type?: string; hint?: string }[] = [
  { key: 'remaining_balance', label: 'Balance stated by the lender (€)', hint: 'Capital still due on the balance date' },
  { key: 'balance_date', label: 'Balance date', type: 'date' },
  { key: 'annual_rate', label: 'Nominal rate (%)' },
  { key: 'taeg', label: 'TAEG (%)' },
  { key: 'monthly_payment', label: 'Instalment (€, all-in)' },
  { key: 'insurance_monthly', label: 'of which insurance (€)' },
  { key: 'next_payment_date', label: 'Next instalment after the balance date', type: 'date' },
  { key: 'payments_remaining', label: 'Instalments remaining', hint: 'When the lender gives a number' },
  { key: 'end_date', label: 'End date stated by the lender', type: 'date' },
  { key: 'original_amount', label: 'Amount borrowed (€)' },
  { key: 'payment_pattern', label: 'Text in the bank label', hint: 'To spot the real debit on the account' },
]

export default function LoansPage() {
  const loans = useLoad(() => api.loans.list())
  const [editing, setEditing] = useState<{ id: number | null; form: FormState } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [extra, setExtra] = useState('0')
  const [strategy, setStrategy] = useState('avalanche')
  const [includeMortgage, setIncludeMortgage] = useState(false)
  const [plan, setPlan] = useState<PayoffPlan | null>(null)

  const [whatIfLoanId, setWhatIfLoanId] = useState<number | null>(null)
  const [lumpSum, setLumpSum] = useState('20000')
  const [newRate, setNewRate] = useState('')
  const [fees, setFees] = useState('')
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null)

  const data = loans.data
  if (loans.error) return <div className="alert error">{loans.error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const active = data.loans.filter((loan) => loan.is_active && loan.current_balance > 0)
  const closed = data.loans.filter((loan) => !(loan.is_active && loan.current_balance > 0))
  const { totals } = data
  const mortgage = active.find((loan) => loan.kind === 'mortgage')
  const whatIfLoan = active.find((loan) => loan.id === (whatIfLoanId ?? mortgage?.id ?? active[0]?.id))

  const kindOfLoan = new Map(data.timeline_loans.map((loan) => [String(loan.id), loan.kind]))
  const chartData = data.timeline.map((row) => {
    const byKind: Record<string, number> = {}
    for (const [key, value] of Object.entries(row)) {
      const kind = kindOfLoan.get(key)
      if (kind) byKind[kind] = (byKind[kind] ?? 0) + Number(value)
    }
    return { month: row.month, ...byKind }
  })
  const kindsInChart = KIND_ORDER.filter((kind) => data.timeline_loans.some((loan) => loan.kind === kind))

  const endings = active
    .filter((loan) => loan.kind !== 'mortgage' && loan.projected_end && loan.next_payment)
    .map((loan) => ({ loan, end: loan.projected_end! }))
    .sort((a, b) => a.end.localeCompare(b.end))
  const endingsByMonth = new Map<string, { names: string[]; freed: number }>()
  for (const { loan, end } of endings) {
    const key = end.slice(0, 7)
    const entry = endingsByMonth.get(key) ?? { names: [], freed: 0 }
    entry.names.push(loan.name)
    entry.freed += loan.monthly_payment
    endingsByMonth.set(key, entry)
  }

  async function save() {
    if (!editing) return
    setError(null)
    try {
      const payload = fromForm(editing.form)
      if (!payload.name) throw new Error('Give the loan a name')
      if (editing.id === null) await api.loans.create(payload)
      else await api.loans.update(editing.id, payload)
      setEditing(null)
      loans.reload()
    } catch (saveError) {
      setError((saveError as Error).message)
    }
  }

  async function runPayoff() {
    setPlan(await api.loans.payoff(Number(extra) || 0, strategy, includeMortgage))
  }

  async function runWhatIf() {
    if (!whatIfLoan) return
    setError(null)
    try {
      setWhatIf(await api.loans.whatIf(whatIfLoan.id, {
        lump_sum: lumpSum ? Number(lumpSum) : undefined,
        new_rate: newRate ? Number(newRate.replace(',', '.')) : undefined,
        fees: fees ? Number(fees) : undefined,
      }))
    } catch (whatIfError) {
      setError((whatIfError as Error).message)
    }
  }

  return (
    <div>
      <h1>Credits &amp; loans</h1>
      <HelpBox title="Where do I find the numbers?" open={data.loans.length === 0}>
        <ul>
          <li>On your lender's website or in your loan contract: <strong>remaining capital</strong> (capital restant dû), <strong>rate</strong> (taux), the <strong>instalment</strong> including insurance, the <strong>next payment date</strong> and the <strong>end date</strong>.</li>
          <li><strong>Instalment purchases</strong> (PayPal in 3 or 4 times, Cofidis, Klarna): add each purchase as its own credit, type <em>Pay-in-instalments</em>, rate 0, with the number of instalments left.</li>
          <li>If you have the <strong>loan offer PDF with the amortisation table</strong>, open the credit with <em>Edit</em> and import it: the projection then follows the official schedule.</li>
          <li>Update the balance whenever the lender gives you a new one; the projection restarts from it.</li>
        </ul>
      </HelpBox>
      {data.loans.length === 0 && (
        <div className="card">
          <p>No credit yet. If you have none, that is fine:</p>
          <button onClick={async () => { await api.plan.update({ skipped_loans: true }); loans.reload() }}>I have no credits or loans</button>
        </div>
      )}
      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert success">{message}</div>}

      <div className="grid cols-4">
        <div className="card stat"><div className="label">Total debt</div><div className="value negative">{euros(totals.total_debt)}</div>
          <div className="small muted">{active.length} active credits</div></div>
        <div className="card stat"><div className="label">Paid each month</div><div className="value">{euros(totals.monthly_payments)}</div>
          {totals.debt_to_income !== null && (
            <div className="small muted"><span className={totals.debt_to_income > 0.33 ? 'negative' : ''}>{Math.round(totals.debt_to_income * 100)} % of income</span>, banks accept 33 %</div>
          )}</div>
        <div className="card stat"><div className="label">Average rate</div><div className="value">{totals.average_rate.toFixed(2)} %</div>
          <div className="small muted">weighted by balance</div></div>
        <div className="card stat"><div className="label">Interest + insurance to come</div><div className="value negative">{euros(totals.remaining_interest_and_insurance)}</div>
          {totals.last_payment_date && <div className="small muted">until {formatDate(totals.last_payment_date)}</div>}</div>
      </div>

      <div className="card">
        <h2>What leaves your accounts each month</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} maxBarSize={28}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={monthLabel} interval={2} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} tickFormatter={(value: number) => `${Math.round(value)}`} />
            <Tooltip formatter={(value, name) => [formatMoney(Number(value)), KIND_LABEL[name as LoanKind] ?? name]} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
            <Legend formatter={(name) => KIND_LABEL[name as LoanKind] ?? name} />
            {kindsInChart.map((kind) => <Bar key={kind} dataKey={kind} stackId="debt" fill={KIND_COLOR[kind]} />)}
          </BarChart>
        </ResponsiveContainer>
        {endingsByMonth.size > 0 && (
          <div className="small" style={{ marginTop: 8 }}>
            <div className="muted" style={{ marginBottom: 4 }}>When credits end, your monthly payments drop:</div>
            {[...endingsByMonth.entries()].map(([month, entry]) => (
              <div key={month}>{monthLabel(month)}: {entry.names.join(', ')} <span className="positive">frees {euros(entry.freed)} / month</span></div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Your credits</h2>
          <span className="spacer" />
          <button className="primary" onClick={() => setEditing({ id: null, form: toForm() })}>+ Add credit</button>
        </div>
        <table>
          <thead>
            <tr><th>Credit</th><th>Balance</th><th>Instalment</th><th>Rate</th><th>Left</th><th>Interest to come</th><th>Last debit seen</th><th /></tr>
          </thead>
          <tbody>
            {KIND_ORDER.map((kind) => {
              const rows = active.filter((loan) => loan.kind === kind)
              if (!rows.length) return null
              return [
                <tr key={kind}><td colSpan={8} className="small muted" style={{ paddingTop: 12 }}><span className="dot" style={{ background: KIND_COLOR[kind] }} />{KIND_LABEL[kind]}</td></tr>,
                ...rows.map((loan) => (
                  <tr key={loan.id}>
                    <td>
                      {loan.name}
                      <div className="small muted">{loan.lender}{loan.has_schedule ? ' · official schedule' : ''}</div>
                      {loan.progress !== null && (
                        <div className="bar-track" style={{ marginTop: 4, maxWidth: 160 }}><div className="bar-fill" style={{ width: `${Math.max(0, Math.min(1, loan.progress)) * 100}%`, background: KIND_COLOR[loan.kind] }} /></div>
                      )}
                    </td>
                    <td className="amount">{formatMoney(loan.current_balance)}</td>
                    <td className="amount">{formatMoney(loan.next_payment?.total ?? 0)}<div className="small muted">next {loan.next_payment ? formatDate(loan.next_payment.date) : '–'}</div></td>
                    <td>{loan.annual_rate ? `${loan.annual_rate} %` : <span className="muted">0 %</span>}{loan.taeg ? <div className="small muted">TAEG {loan.taeg} %</div> : null}</td>
                    <td>{loan.months_left} mo<div className="small muted">{loan.projected_end ? `to ${formatDate(loan.projected_end)}` : ''}</div></td>
                    <td className="amount">{formatMoney(loan.remaining_interest + loan.remaining_insurance)}</td>
                    <td className="small muted">{loan.last_seen_payment ? `${formatMoney(-loan.last_seen_payment.amount)} on ${formatDate(loan.last_seen_payment.date)}` : loan.payment_pattern ? 'not found' : '–'}</td>
                    <td><button className="small" onClick={() => setEditing({ id: loan.id, form: toForm(loan) })}>Edit</button></td>
                  </tr>
                )),
              ]
            })}
          </tbody>
        </table>
        {closed.length > 0 && (
          <p className="small muted" style={{ marginTop: 8 }}>
            Settled or inactive: {closed.map((loan) => (
              <button key={loan.id} className="small" style={{ marginRight: 6 }} onClick={() => setEditing({ id: loan.id, form: toForm(loan) })}>{loan.name}</button>
            ))}
          </p>
        )}
      </div>

      {editing && (
        <div className="card">
          <h2>{editing.id === null ? 'New credit' : 'Edit credit'}</h2>
          <div className="grid cols-2">
            <label className="small">Name<br /><input style={{ width: '100%' }} value={editing.form.name} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, name: event.target.value } })} /></label>
            <label className="small">Lender<br /><input style={{ width: '100%' }} value={editing.form.lender} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, lender: event.target.value } })} /></label>
            <label className="small">Type<br />
              <select value={editing.form.kind} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, kind: event.target.value } })}>
                {KIND_ORDER.map((kind) => <option key={kind} value={kind}>{KIND_LABEL[kind]}</option>)}
              </select>
            </label>
            <label className="small">Active<br />
              <select value={editing.form.is_active} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, is_active: event.target.value } })}>
                <option value="yes">yes</option><option value="no">no (settled)</option>
              </select>
            </label>
            {FIELDS.map((field) => (
              <label className="small" key={field.key}>{field.label}<br />
                <input style={{ width: '100%' }} type={field.type ?? 'text'} value={editing.form[field.key]} title={field.hint}
                  onChange={(event) => setEditing({ ...editing, form: { ...editing.form, [field.key]: event.target.value } })} />
              </label>
            ))}
          </div>
          <label className="small">Notes<br /><textarea style={{ width: '100%' }} rows={3} value={editing.form.notes} onChange={(event) => setEditing({ ...editing, form: { ...editing.form, notes: event.target.value } })} /></label>
          <p className="small muted">The projection starts from the balance and date above, then applies the instalment and rate month by month. Update the balance whenever the lender gives a new one.</p>
          <div className="inline-form">
            <button className="primary" onClick={save}>Save</button>
            <button onClick={() => setEditing(null)}>Cancel</button>
            {editing.id !== null && (
              <>
                <label className="small">Import the amortisation table from the loan offer (PDF):{' '}
                  <input type="file" accept="application/pdf" onChange={async (event) => {
                    const file = event.target.files?.[0]
                    if (!file || editing.id === null) return
                    try {
                      const result = await api.loans.importSchedule(editing.id, file)
                      setMessage(`Imported ${result.rows} instalments, ${formatDate(result.first)} to ${formatDate(result.last)}.`)
                      loans.reload()
                    } catch (importError) {
                      setError((importError as Error).message)
                    }
                  }} />
                </label>
                <span className="spacer" />
                <button className="danger" onClick={async () => { if (confirm('Delete this credit?')) { await api.loans.remove(editing.id!); setEditing(null); loans.reload() } }}>Delete</button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="grid cols-2">
        <div className="card">
          <h2>Payoff planner</h2>
          <p className="small muted">You keep paying the same total as today. Each time a credit ends, its payment moves to the next target, and any extra you add goes there too.</p>
          <div className="inline-form" style={{ marginBottom: 8 }}>
            <label className="small">Extra per month (€) <input style={{ width: 80 }} value={extra} onChange={(event) => setExtra(event.target.value)} /></label>
            <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
              <option value="avalanche">Highest rate first (saves most interest)</option>
              <option value="snowball">Smallest balance first</option>
            </select>
            <label className="small"><input type="checkbox" checked={includeMortgage} onChange={(event) => setIncludeMortgage(event.target.checked)} /> include mortgage</label>
            <button className="primary" onClick={runPayoff}>Simulate</button>
          </div>
          {plan && (
            <div>
              <div className="chips" style={{ marginBottom: 8 }}>
                <span className="chip">Interest saved <strong className={plan.interest_saved > 0 ? 'positive' : ''}>{formatMoney(plan.interest_saved)}</strong></span>
                <span className="chip">Debt-free {formatDate(plan.plan.debt_free)} instead of {formatDate(plan.baseline.debt_free)}</span>
                <span className="chip">Budget {formatMoney(plan.monthly_budget)} / month</span>
              </div>
              <table>
                <thead><tr><th>Cleared in this order</th><th>Date</th><th>Without plan</th></tr></thead>
                <tbody>{plan.order.map((entry) => (
                  <tr key={entry.name}><td>{entry.name}</td><td>{monthLabel(entry.date)}</td><td className="muted">{monthLabel(entry.baseline_date)}</td></tr>
                ))}</tbody>
              </table>
              <p className="small muted">Clearing a 0 % credit early saves no interest, it only frees cash flow sooner. The interest saved is the number that matters.</p>
            </div>
          )}
        </div>

        <div className="card">
          <h2>What if…</h2>
          <p className="small muted">Test a lump-sum prepayment, or a lower rate (renegotiation or buy-back), on one credit.</p>
          <div className="inline-form" style={{ marginBottom: 8 }}>
            <select value={whatIfLoan?.id ?? ''} onChange={(event) => { setWhatIfLoanId(Number(event.target.value)); setWhatIf(null) }}>
              {active.map((loan) => <option key={loan.id} value={loan.id}>{loan.name}</option>)}
            </select>
          </div>
          <div className="inline-form" style={{ marginBottom: 8 }}>
            <label className="small">Lump sum (€) <input style={{ width: 80 }} value={lumpSum} onChange={(event) => setLumpSum(event.target.value)} /></label>
            <label className="small">New rate (%) <input style={{ width: 60 }} value={newRate} onChange={(event) => setNewRate(event.target.value)} /></label>
            <label className="small">Fees (€) <input style={{ width: 70 }} value={fees} onChange={(event) => setFees(event.target.value)} /></label>
            <button className="primary" onClick={runWhatIf}>Compute</button>
          </div>
          {whatIf && (
            <div className="small">
              <p className="muted">Today: {euros(whatIf.balance)} at {whatIf.annual_rate} %, {whatIf.baseline.months} instalments left, {euros(whatIf.baseline.cost)} of interest and insurance to come.</p>
              {whatIf.lump_sum && (
                <div style={{ marginBottom: 8 }}>
                  <strong>Prepay {euros(whatIf.lump_sum.amount)}</strong> (indemnity up to {euros(whatIf.lump_sum.indemnity_max)})
                  <ul>
                    <li>Keep the instalment: {whatIf.lump_sum.shorter_duration.months_saved} fewer months, <span className="positive">{euros(whatIf.lump_sum.shorter_duration.cost_saved)} saved</span> after the indemnity.</li>
                    <li>Or lower the instalment to {formatMoney(whatIf.lump_sum.lower_payment.payment)}: {euros(whatIf.lump_sum.lower_payment.monthly_saving)} less each month.</li>
                  </ul>
                  <span className="muted">{whatIf.lump_sum.note}</span>
                </div>
              )}
              {whatIf.renegotiation && (
                <div>
                  <strong>At {whatIf.renegotiation.new_rate} %</strong>
                  <ul>
                    <li>Instalment {formatMoney(whatIf.renegotiation.new_payment)}, {euros(whatIf.renegotiation.monthly_saving)} less each month.</li>
                    <li>Interest saved {euros(whatIf.renegotiation.interest_saved)}, <span className={whatIf.renegotiation.net_saving > 0 ? 'positive' : 'negative'}>{euros(whatIf.renegotiation.net_saving)} after {euros(whatIf.renegotiation.fees)} of fees</span>
                      {whatIf.renegotiation.break_even_months > 0 && <>, paid back in {whatIf.renegotiation.break_even_months} months</>}.</li>
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
