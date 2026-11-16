import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatDate, formatMoney, type Account, type AccountKind } from '../api'
import { useLoad } from '../hooks'

const KINDS: { value: AccountKind; label: string }[] = [
  { value: 'checking', label: 'Current account' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'savings', label: 'Savings (Livret A, LDDS…)' },
  { value: 'investment', label: 'Investment (PEA, CTO, assurance-vie…)' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'loan', label: 'Loan / credit' },
  { value: 'other', label: 'Other' },
]

function NumberField({ value, onCommit, width = 110 }: { value: number | null; onCommit: (value: number | null) => void; width?: number }) {
  const [draft, setDraft] = useState(value === null ? '' : String(value))
  return (
    <input
      style={{ width, textAlign: 'right' }}
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        const parsed = draft.trim() === '' ? null : Number(draft.replace(',', '.'))
        if (parsed !== null && Number.isNaN(parsed)) return
        if (parsed !== value) onCommit(parsed)
      }}
    />
  )
}

export default function AccountsPage() {
  const accounts = useLoad(() => api.accounts.list())
  const [draft, setDraft] = useState<{ name: string; bank: string; kind: AccountKind }>({ name: '', bank: '', kind: 'checking' })
  const [error, setError] = useState<string | null>(null)

  async function create() {
    if (!draft.name.trim()) return
    setError(null)
    try {
      await api.accounts.create({ name: draft.name.trim(), bank: draft.bank.trim() || null, kind: draft.kind })
      setDraft({ name: '', bank: '', kind: 'checking' })
      accounts.reload()
    } catch (createError) {
      setError((createError as Error).message)
    }
  }

  async function update(account: Account, changes: Partial<Account>) {
    await api.accounts.update(account.id, changes)
    accounts.reload()
  }

  async function remove(account: Account) {
    setError(null)
    try {
      await api.accounts.remove(account.id)
      accounts.reload()
    } catch (removeError) {
      setError((removeError as Error).message)
    }
  }

  return (
    <div>
      <h1>Accounts</h1>

      <div className="grid cols-2">
        {accounts.data?.filter((account) => account.is_active).map((account) => {
          const balance = account.current_balance
          const available = account.available
          const inOverdraft = balance !== null && balance < 0
          const overdraftUsed = inOverdraft && account.overdraft_limit > 0 ? Math.min(100, (-balance / account.overdraft_limit) * 100) : 0
          return (
            <div className="card" key={account.id}>
              <div className="toolbar" style={{ marginBottom: 4 }}>
                <strong>{account.name}</strong>
                <span className="muted small">{account.bank}</span>
                <span className="spacer" />
                <span className="badge">{KINDS.find((kind) => kind.value === account.kind)?.label}</span>
              </div>
              <div className="stat">
                <div className="label">Current situation</div>
                <div className={`value ${balance === null ? 'muted' : balance < 0 ? 'negative' : 'positive'}`}>
                  {balance === null ? '—' : formatMoney(balance, account.currency)}
                </div>
                <div className="small muted">
                  {account.statement_balance_date
                    ? <>Statement balance {formatMoney(account.statement_balance ?? 0, account.currency)} on {formatDate(account.statement_balance_date)}, {account.movements_since_statement >= 0 ? '+' : ''}{formatMoney(account.movements_since_statement, account.currency)} since. <Link to={`/transactions?account_id=${account.id}`}>Add what happened since →</Link></>
                    : 'No statement balance yet: import a statement or type the balance below.'}
                </div>
              </div>
              {account.overdraft_limit > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div className="small muted">Découvert autorisé {formatMoney(account.overdraft_limit, account.currency)} · available {available === null ? '—' : formatMoney(available, account.currency)}</div>
                  <div className="bar-track" style={{ marginTop: 4 }}>
                    <div className="bar-fill" style={{ width: `${overdraftUsed}%`, background: overdraftUsed > 80 ? 'var(--negative)' : 'var(--expense)' }} />
                  </div>
                  {inOverdraft && <div className="small negative">{overdraftUsed.toFixed(0)}% of the overdraft used</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="card">
        <h2>Settings</h2>
        <table>
          <thead>
            <tr><th>Name</th><th>Bank</th><th>Type</th><th className="amount">Découvert autorisé</th><th className="amount">Statement balance</th><th>Balance date</th><th>Transactions</th><th>Active</th><th></th></tr>
          </thead>
          <tbody>
            {accounts.data?.map((account) => (
              <tr key={account.id} style={{ opacity: account.is_active ? 1 : 0.5 }}>
                <td><input key={account.name} defaultValue={account.name} onBlur={(event) => event.target.value !== account.name && update(account, { name: event.target.value })} /></td>
                <td>{account.bank ?? '—'}</td>
                <td>
                  <select value={account.kind} onChange={(event) => update(account, { kind: event.target.value as AccountKind })}>
                    {KINDS.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
                  </select>
                </td>
                <td className="amount"><NumberField key={`od-${account.overdraft_limit}`} value={account.overdraft_limit} onCommit={(value) => update(account, { overdraft_limit: value ?? 0 })} width={90} /></td>
                <td className="amount"><NumberField key={`sb-${account.statement_balance}`} value={account.statement_balance} onCommit={(value) => update(account, { statement_balance: value })} /></td>
                <td><input type="date" value={account.statement_balance_date ?? ''} onChange={(event) => update(account, { statement_balance_date: event.target.value || null })} /></td>
                <td>{account.transaction_count}</td>
                <td><input type="checkbox" checked={account.is_active} onChange={(event) => update(account, { is_active: event.target.checked })} /></td>
                <td>{account.transaction_count === 0 && <button className="danger" onClick={() => remove(account)}>Delete</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">The statement balance is filled automatically when you import a statement; set it by hand for accounts without statements. "Current situation" = statement balance + all transactions dated after it.</p>
      </div>

      <div className="card">
        <h2>Add an account</h2>
        <div className="inline-form">
          <input placeholder="Name (e.g. Compte courant)" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          <input placeholder="Bank (optional)" value={draft.bank} onChange={(event) => setDraft({ ...draft, bank: event.target.value })} />
          <select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as AccountKind })}>
            {KINDS.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
          </select>
          <button className="primary" onClick={create} disabled={!draft.name.trim()}>Add</button>
        </div>
        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
      </div>
    </div>
  )
}
