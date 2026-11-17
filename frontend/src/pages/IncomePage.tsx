import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatMoney } from '../api'
import { useLoad } from '../hooks'

const axisTick = { fill: 'var(--text-secondary)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }
const euros = (value: number) => formatMoney(Math.round(value)).replace(/,00$/, '')
const monthLabel = (month: string) => new Date(month + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

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
      {data.empty && <div className="card"><p>No payslip yet. Add your PDF payslips above.</p></div>}
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

          <div className="card">
            <h2>Tax bracket and retirement savings</h2>
            <p>Your taxable salary is about <strong>{euros(data.annual_taxable_estimate)}</strong> a year after the 10 % allowance. For a single person that puts you in the <strong>{Math.round(data.marginal_rate * 100)} % bracket</strong> (indicative scale, rent and the furnished-rental regime not included).</p>
            <ul>
              <li><strong>PER (retirement savings plan).</strong> Payments are deductible from taxable income up to about {euros(data.per.ceiling_estimate)} a year (roughly 10 % of your professional income; your tax notice gives the exact ceiling). At {Math.round(data.marginal_rate * 100)} %, each 1 000 € paid in lowers your tax by about {euros(data.per.tax_saved_per_1000)}, up to {euros(data.per.max_tax_saved)} a year. The money is blocked until retirement, except notably to buy your main home, which fits your plan in Aix. Amounts you deducted are taxed when you take them out, so the gain is the difference between your bracket now and then.</li>
              <li><strong>PEE / PERCO.</strong> Your payslips show no company savings plan and no employer contribution. Ask your employer whether one exists: an employer top-up is free money and these plans have their own tax advantages.</li>
              <li><strong>Before saving more.</strong> The emergency cash on the Savings page is close to zero, and both current accounts are overdrawn. A PER is the wrong place for money you may need within a few years; build the buffer first.</li>
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
