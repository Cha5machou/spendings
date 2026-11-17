import HelpBox from '../components/HelpBox'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const monthLabel = (month: string) => new Date(month + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

function ManualPayslip({ onAdded }: { onAdded: () => void }) {
  const [form, setForm] = useState({ month: '', gross: '', net_before_tax: '', tax_rate: '', net_paid: '' })
  const [error, setError] = useState<string | null>(null)
  const number = (text: string) => Number(text.replace(',', '.'))
  async function add() {
    setError(null)
    try {
      await api.income.addManual({ month: form.month, gross: number(form.gross), net_before_tax: number(form.net_before_tax), tax_rate: number(form.tax_rate || '0'), net_paid: number(form.net_paid) })
      setForm({ month: '', gross: '', net_before_tax: '', tax_rate: '', net_paid: '' })
      onAdded()
    } catch (addError) {
      setError((addError as Error).message)
    }
  }
  const input = (key: keyof typeof form, label: string, placeholder: string, type = 'text') => (
    <label className="small">{label}<br /><input style={{ width: 120 }} type={type} placeholder={placeholder} value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} /></label>
  )
  return (
    <details className="help">
      <summary>Add a payslip by hand</summary>
      <div className="help-body">
        {error && <div className="alert error">{error}</div>}
        <div className="inline-form" style={{ alignItems: 'flex-end' }}>
          {input('month', 'Month', '2026-03', 'month')}{input('gross', 'Gross pay', '5000')}{input('net_before_tax', 'Net before tax', '3900')}{input('tax_rate', 'Tax rate %', '12')}{input('net_paid', 'Net paid', '3400')}
          <button className="primary" onClick={add} disabled={!form.month || !form.gross || !form.net_before_tax || !form.net_paid}>Add</button>
        </div>
      </div>
    </details>
  )
}

export default function IncomePage() {
  const income = useLoad(() => api.income.get())
  const [message, setMessage] = useState<string | null>(null)

  if (income.error) return <div className="alert error">{income.error}</div>
  const data = income.data
  if (!data) return <p className="muted">Loading…</p>

  async function upload(files: FileList | null) {
    if (!files?.length) return
    const result = await api.income.uploadPayslips(files)
    setMessage(`Imported ${result.imported.length} payslip(s).${result.failed.length ? ` ${result.failed.length} could not be read: ${result.failed.map((failure) => failure.filename).join(', ')}.` : ''}`)
    income.reload()
  }

  return (
    <div>
      <h1>Income</h1>
      <div className="toolbar">
        <label className="small">Add payslips (PDF): <input type="file" accept="application/pdf" multiple onChange={(event) => upload(event.target.files)} /></label>
        {message && <span className="small positive">{message}</span>}
      </div>
      <HelpBox title="How do I add my payslips?" open={data.empty}>
        <ul>
          <li>Download your payslips (PDF) from your employer's payroll space and add them above, several at once. The reader works on the common electronic layout.</li>
          <li>If a file cannot be read, <strong>add it by hand</strong> below: gross pay, net before tax, tax rate and the net paid to you.</li>
          <li>Payslips give the app your real income, the tax taken at source and your tax bracket. Self-employed or no salary? Skip this step.</li>
        </ul>
      </HelpBox>
      <ManualPayslip onAdded={income.reload} />
      {data.empty && <div className="card"><p>No payslip yet.</p></div>}
      {!data.empty && (
        <>
          <div className="grid cols-4">
            <div className="card stat"><div className="label">Gross per month</div><div className="value">{euros(data.average.gross)}</div>
              <div className="small muted">{euros(data.annual_gross)} a year at {data.employer}</div></div>
            <div className="card stat"><div className="label">Net before tax</div><div className="value">{euros(data.average.net_before_tax)}</div>
              <div className="small muted">{Math.round((data.average.net_before_tax / data.average.gross) * 100)} % of gross</div></div>
            <div className="card stat"><div className="label">Income tax withheld</div><div className="value negative">{euros(data.average.tax_withheld)}</div>
              <div className="small muted">{(data.withholding_share * 100).toFixed(1).replace('.', ',')} % of net before tax, rising</div></div>
            <div className="card stat"><div className="label">Paid to your account</div><div className="value positive">{euros(data.average.net_paid)}</div>
              <div className="small muted">{Math.round(data.net_share_of_gross * 100)} % of gross</div></div>
          </div>

          <div className="card">
            <h2>Gross, tax and net pay</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.payslips} maxBarSize={36}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="month" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={monthLabel} />
                <YAxis tick={axisTick} axisLine={false} tickLine={false} width={55} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} labelFormatter={(label) => monthLabel(String(label))} contentStyle={tooltipStyle} />
                <Legend />
                <Bar dataKey="net_paid" name="Paid to you" stackId="pay" fill="var(--positive)" />
                <Bar dataKey="tax_withheld" name="Income tax withheld" stackId="pay" fill="var(--expense)" />
              </BarChart>
            </ResponsiveContainer>
            <p className="small muted">The withholding rate went from {data.payslips[0].tax_rate} % to {data.payslips[data.payslips.length - 1].tax_rate} % over the year, so you keep less of each payslip than in November. June is higher, at {euros(data.payslips.find((slip) => slip.month.endsWith('-06'))?.gross ?? 0)} gross.</p>
          </div>

          <details className="help">
            <summary>All payslips ({data.payslips.length})</summary>
            <div className="help-body">
              <table>
                <thead><tr><th>Month</th><th>Gross</th><th>Net before tax</th><th>Tax</th><th>Paid</th><th /></tr></thead>
                <tbody>
                  {[...data.payslips].reverse().map((slip) => (
                    <tr key={slip.month}>
                      <td>{monthLabel(slip.month)}</td><td className="amount">{formatMoney(slip.gross)}</td><td className="amount">{formatMoney(slip.net_before_tax)}</td>
                      <td className="amount">{formatMoney(slip.tax_withheld)} <span className="muted small">({slip.tax_rate} %)</span></td><td className="amount">{formatMoney(slip.net_paid)}</td>
                      <td><button className="small danger" onClick={async () => { if (confirm(`Delete the ${monthLabel(slip.month)} payslip?`)) { await api.income.removePayslip(slip.month); income.reload() } }}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <div className="card">
            <h2>Tax bracket and retirement savings</h2>
            <p>Your taxable salary is about <strong>{euros(data.annual_taxable_estimate)}</strong> a year after the 10 % allowance. For a single person that puts you in the <strong>{Math.round(data.marginal_rate * 100)} % bracket</strong> (indicative scale, rent and the furnished-rental regime not included).</p>
            <ul>
              <li><strong>PER (retirement savings plan).</strong> Payments are deductible from taxable income up to about {euros(data.per.ceiling_estimate)} a year (roughly 10 % of your professional income; your tax notice gives the exact ceiling). At {Math.round(data.marginal_rate * 100)} %, each 1 000 € paid in lowers your tax by about {euros(data.per.tax_saved_per_1000)}, up to {euros(data.per.max_tax_saved)} a year. The money is blocked until retirement, except notably to buy your main home, such as buying your main home. Amounts you deducted are taxed when you take them out, so the gain is the difference between your bracket now and then.</li>
              <li><strong>PEE / PERCO.</strong> Your payslips show no company savings plan and no employer contribution. Ask your employer whether one exists: an employer top-up is free money and these plans have their own tax advantages.</li>
              <li><strong>Before saving more.</strong> The emergency cash on the Savings page is close to zero, and both current accounts are overdrawn. A PER is the wrong place for money you may need within a few years; build the buffer first.</li>
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
