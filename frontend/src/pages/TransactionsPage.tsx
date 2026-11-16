import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, formatDate, formatMoney, type Category, type Transaction } from '../api'
import { useLoad } from '../hooks'

const PAGE_SIZE = 200

/** Guess a reusable rule pattern from a label: drop dates, card prefixes and numbers. */
function suggestPattern(label: string): string {
  return label
    .replace(/\b\d{2}\/\d{2}(\/\d{2,4})?\b/g, '')
    .replace(/\b(carte|cb|psc|prlv|vir|inst|sepa|paiement|achat)\b/gi, '')
    .replace(/\d+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .split(' ')
    .slice(0, 2)
    .join(' ')
}

function monthBounds(year: number, month: number): { start: string; end: string } {
  const pad = (value: number) => String(value).padStart(2, '0')
  const lastDay = new Date(year, month, 0).getDate()
  return { start: `${year}-${pad(month)}-01`, end: `${year}-${pad(month)}-${pad(lastDay)}` }
}

function monthLabel(start: string): string {
  return new Date(start + 'T00:00:00').toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
}

function CategoryGroups({ categories }: { categories: Category[] }) {
  const kinds: Category['kind'][] = ['expense', 'income', 'savings', 'transfer']
  return (
    <>
      {kinds.map((kind) => (
        <optgroup key={kind} label={kind}>
          {categories.filter((category) => category.kind === kind).map((category) => (
            <option key={category.id} value={category.id}>{category.name}</option>
          ))}
        </optgroup>
      ))}
    </>
  )
}

export default function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const accountId = searchParams.get('account_id') ? Number(searchParams.get('account_id')) : undefined
  const categoryId = searchParams.get('category_id') ? Number(searchParams.get('category_id')) : undefined
  const uncategorized = searchParams.get('uncategorized') === '1'
  const search = searchParams.get('search') ?? ''
  const start = searchParams.get('start') ?? ''
  const end = searchParams.get('end') ?? ''
  const page = Number(searchParams.get('page') ?? '0')
  const isWholeMonth = /^\d{4}-\d{2}-01$/.test(start) && end === monthBounds(Number(start.slice(0, 4)), Number(start.slice(5, 7))).end

  const accounts = useLoad(() => api.accounts.list())
  const categories = useLoad(() => api.categories.list())
  const health = useLoad(() => api.health())
  const transactions = useLoad(
    () => api.transactions.list({ account_id: accountId, category_id: categoryId, uncategorized, search, start, end, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [accountId, categoryId, uncategorized, search, start, end, page],
  )
  const summary = useLoad(() => (start && end ? api.dashboard({ start, end, account_id: accountId }) : Promise.resolve(null)), [start, end, accountId, transactions.data])

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [ruleFor, setRuleFor] = useState<{ transaction: Transaction; pattern: string } | null>(null)
  const [editing, setEditing] = useState<{ id: number; date: string; label: string; amount: string; notes: string } | null>(null)
  const [adding, setAdding] = useState<{ account_id: string; date: string; label: string; amount: string; category_id: string } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function setParams(changes: Record<string, string | undefined>) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in changes)) next.delete('page')
    setSearchParams(next)
  }

  function shiftMonth(delta: number) {
    const base = isWholeMonth ? new Date(start + 'T00:00:00') : new Date()
    const target = new Date(base.getFullYear(), base.getMonth() + delta, 1)
    setParams(monthBounds(target.getFullYear(), target.getMonth() + 1))
  }

  const categoryById = new Map((categories.data ?? []).map((category) => [category.id, category]))
  const accountById = new Map((accounts.data ?? []).map((account) => [account.id, account]))

  function replaceItem(updated: Transaction) {
    transactions.setData((current) => current && { ...current, items: current.items.map((item) => (item.id === updated.id ? updated : item)) })
  }

  async function changeCategory(transaction: Transaction, categoryIdValue: string) {
    const newCategoryId = categoryIdValue ? Number(categoryIdValue) : null
    const updated = await api.transactions.update(transaction.id, { category_id: newCategoryId })
    replaceItem(updated)
    if (newCategoryId) setRuleFor({ transaction: updated, pattern: suggestPattern(transaction.label) })
  }

  async function saveRule() {
    if (!ruleFor || !ruleFor.transaction.category_id) return
    const result = await api.categories.createRule({ category_id: ruleFor.transaction.category_id, pattern: ruleFor.pattern, priority: 10 })
    setMessage(`Rule "${ruleFor.pattern}" saved and applied to ${result.applied_to} other transaction(s).`)
    setRuleFor(null)
    transactions.reload()
  }

  async function saveEdit() {
    if (!editing) return
    const amount = Number(editing.amount.replace(',', '.'))
    if (Number.isNaN(amount)) return
    const updated = await api.transactions.update(editing.id, { date: editing.date, label: editing.label, amount, notes: editing.notes || null })
    replaceItem(updated)
    setEditing(null)
    summary.reload()
  }

  async function saveNew() {
    if (!adding || !adding.account_id || !adding.date || !adding.label.trim()) return
    const amount = Number(adding.amount.replace(',', '.'))
    if (Number.isNaN(amount)) return
    await api.transactions.create({ account_id: Number(adding.account_id), date: adding.date, label: adding.label.trim(), amount, category_id: adding.category_id ? Number(adding.category_id) : null })
    setAdding(null)
    transactions.reload()
  }

  async function remove(transaction: Transaction) {
    await api.transactions.remove(transaction.id)
    transactions.reload()
  }

  async function bulkApply(categoryIdValue: string) {
    if (selected.size === 0) return
    await api.transactions.bulkCategorize([...selected], categoryIdValue ? Number(categoryIdValue) : null)
    setSelected(new Set())
    transactions.reload()
  }

  async function askClaude() {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.transactions.suggestCategories()
      setMessage(`Claude reviewed ${result.reviewed} uncategorized transaction(s) and categorized ${result.applied}. They are marked "ai" so you can correct them.`)
      transactions.reload()
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const items = transactions.data?.items ?? []
  const total = transactions.data?.total ?? 0
  const monthSummary = summary.data
  const summaryCategories = monthSummary?.by_category.filter((entry) => entry.kind !== 'transfer') ?? []

  return (
    <div>
      <h1>Transactions</h1>
      <div className="toolbar">
        <button onClick={() => shiftMonth(-1)}>‹</button>
        <strong style={{ minWidth: 130, textAlign: 'center' }}>{isWholeMonth ? monthLabel(start) : start || end ? `${start || '…'} → ${end || '…'}` : 'All dates'}</strong>
        <button onClick={() => shiftMonth(1)}>›</button>
        {(start || end) && <button onClick={() => setParams({ start: undefined, end: undefined })}>All dates</button>}
        <span className="spacer" />
        <select value={accountId ?? ''} onChange={(event) => setParams({ account_id: event.target.value })}>
          <option value="">All accounts</option>
          {accounts.data?.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
        </select>
        <select value={categoryId ?? ''} onChange={(event) => setParams({ category_id: event.target.value })}>
          <option value="">All categories</option>
          {categories.data && <CategoryGroups categories={categories.data} />}
        </select>
        <label><input type="checkbox" checked={uncategorized} onChange={(event) => setParams({ uncategorized: event.target.checked ? '1' : undefined })} /> Uncategorized only</label>
        <input placeholder="Search label… (Enter)" defaultValue={search} onKeyDown={(event) => { if (event.key === 'Enter') setParams({ search: (event.target as HTMLInputElement).value }) }} />
        {health.data?.claude_available && (
          <button onClick={askClaude} disabled={busy}>{busy ? 'Asking Claude…' : 'Categorize with Claude'}</button>
        )}
        <button className="primary" onClick={() => setAdding({ account_id: accountId ? String(accountId) : '', date: new Date().toISOString().slice(0, 10), label: '', amount: '', category_id: '' })}>+ Add</button>
      </div>

      {adding && (
        <div className="card inline-form">
          <span className="muted small">Not on a statement yet:</span>
          <select value={adding.account_id} onChange={(event) => setAdding({ ...adding, account_id: event.target.value })}>
            <option value="">Account…</option>
            {accounts.data?.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select>
          <input type="date" value={adding.date} onChange={(event) => setAdding({ ...adding, date: event.target.value })} />
          <input placeholder="Label" value={adding.label} onChange={(event) => setAdding({ ...adding, label: event.target.value })} />
          <input placeholder="Amount (−50 = out)" style={{ width: 130 }} value={adding.amount} onChange={(event) => setAdding({ ...adding, amount: event.target.value })} />
          <select value={adding.category_id} onChange={(event) => setAdding({ ...adding, category_id: event.target.value })}>
            <option value="">Category…</option>
            {categories.data && <CategoryGroups categories={categories.data} />}
          </select>
          <button className="primary" onClick={saveNew} disabled={!adding.account_id || !adding.label.trim() || !adding.amount}>Save</button>
          <button onClick={() => setAdding(null)}>Cancel</button>
        </div>
      )}

      {monthSummary && (
        <div className="card">
          <div className="toolbar" style={{ marginBottom: 8 }}>
            <span>Income <strong className="positive">{formatMoney(monthSummary.income)}</strong></span>
            <span>Expenses <strong className="negative">{formatMoney(monthSummary.expenses)}</strong></span>
            <span>Saved <strong>{formatMoney(monthSummary.savings)}</strong></span>
            <span>Net <strong className={monthSummary.net >= 0 ? 'positive' : 'negative'}>{formatMoney(monthSummary.net)}</strong></span>
            {monthSummary.uncategorized_count > 0 && <span className="badge">{monthSummary.uncategorized_count} uncategorized</span>}
          </div>
          <div className="chips">
            {summaryCategories.map((entry) => (
              <button
                key={entry.category_id ?? 'none'}
                className={`chip ${categoryId === entry.category_id || (uncategorized && entry.category_id === null) ? 'active' : ''}`}
                onClick={() => (entry.category_id === null ? setParams({ uncategorized: uncategorized ? undefined : '1', category_id: undefined }) : setParams({ category_id: categoryId === entry.category_id ? undefined : String(entry.category_id), uncategorized: undefined }))}
              >
                <span className="dot" style={{ background: entry.color ?? 'var(--text-muted)' }} />
                {entry.category_name} <span className={entry.total >= 0 ? 'positive' : ''}>{formatMoney(entry.total)}</span> <span className="muted">({entry.count})</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {message && <div className="alert success">{message} <button className="link" onClick={() => setMessage(null)}>dismiss</button></div>}
      {transactions.error && <div className="alert error">{transactions.error}</div>}

      {selected.size > 0 && (
        <div className="alert inline-form">
          <span>{selected.size} selected →</span>
          <select onChange={(event) => bulkApply(event.target.value)} defaultValue="">
            <option value="" disabled>Set category…</option>
            {categories.data && <CategoryGroups categories={categories.data} />}
          </select>
          <button onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      <div className="card">
        <div className="toolbar small muted">
          <span>{total} transaction(s), total {formatMoney(transactions.data?.total_amount ?? 0)}</span>
          <span className="spacer" />
          <button disabled={page === 0} onClick={() => setParams({ page: String(page - 1) })}>‹ Prev</button>
          <span>page {page + 1} / {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
          <button disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setParams({ page: String(page + 1) })}>Next ›</button>
        </div>
        <table>
          <thead>
            <tr>
              <th><input type="checkbox" checked={items.length > 0 && selected.size === items.length} onChange={(event) => setSelected(event.target.checked ? new Set(items.map((item) => item.id)) : new Set())} /></th>
              <th>Date</th>
              <th>Label</th>
              <th>Account</th>
              <th>Category</th>
              <th className="amount">Amount</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((transaction) => (
              editing?.id === transaction.id ? (
                <tr key={transaction.id} className="editing">
                  <td></td>
                  <td><input type="date" value={editing.date} onChange={(event) => setEditing({ ...editing, date: event.target.value })} /></td>
                  <td>
                    <input style={{ width: '100%' }} value={editing.label} onChange={(event) => setEditing({ ...editing, label: event.target.value })} />
                    <input style={{ width: '100%', marginTop: 4 }} placeholder="Notes" value={editing.notes} onChange={(event) => setEditing({ ...editing, notes: event.target.value })} />
                  </td>
                  <td className="muted small">{accountById.get(transaction.account_id)?.name}</td>
                  <td className="muted small">{categoryById.get(transaction.category_id ?? -1)?.name ?? '—'}</td>
                  <td className="amount"><input style={{ width: 110, textAlign: 'right' }} value={editing.amount} onChange={(event) => setEditing({ ...editing, amount: event.target.value })} /></td>
                  <td className="inline-form" style={{ whiteSpace: 'nowrap' }}>
                    <button className="primary" onClick={saveEdit}>Save</button>
                    <button onClick={() => setEditing(null)}>Cancel</button>
                    <button className="danger" onClick={() => remove(transaction)}>Delete</button>
                  </td>
                </tr>
              ) : (
                <tr key={transaction.id}>
                  <td><input type="checkbox" checked={selected.has(transaction.id)} onChange={(event) => {
                    const next = new Set(selected)
                    if (event.target.checked) next.add(transaction.id)
                    else next.delete(transaction.id)
                    setSelected(next)
                  }} /></td>
                  <td className="muted">{formatDate(transaction.date)}</td>
                  <td>
                    {transaction.label}
                    {transaction.notes && <div className="small muted">{transaction.notes}</div>}
                    {ruleFor?.transaction.id === transaction.id && (
                      <div className="inline-form rule-form small">
                        <span className="muted">Always file labels containing</span>
                        <input value={ruleFor.pattern} onChange={(event) => setRuleFor({ ...ruleFor, pattern: event.target.value })} />
                        <span className="muted">under {categoryById.get(ruleFor.transaction.category_id!)?.name}?</span>
                        <button className="primary" onClick={saveRule} disabled={!ruleFor.pattern}>Save rule</button>
                        <button onClick={() => setRuleFor(null)}>No</button>
                      </div>
                    )}
                  </td>
                  <td className="muted small">{accountById.get(transaction.account_id)?.name ?? transaction.account_id}</td>
                  <td>
                    <span className="dot" style={{ background: categoryById.get(transaction.category_id ?? -1)?.color ?? 'transparent' }} />
                    <select value={transaction.category_id ?? ''} onChange={(event) => changeCategory(transaction, event.target.value)}>
                      <option value="">— uncategorized —</option>
                      {categories.data && <CategoryGroups categories={categories.data} />}
                    </select>
                    {transaction.category_source !== 'none' && <span className="badge" style={{ marginLeft: 4 }}>{transaction.category_source}</span>}
                  </td>
                  <td className={`amount ${transaction.amount >= 0 ? 'positive' : ''}`}>{formatMoney(transaction.amount, transaction.currency)}</td>
                  <td><button className="link small" title="Edit date, label, amount or notes" onClick={() => setEditing({ id: transaction.id, date: transaction.date, label: transaction.label, amount: String(transaction.amount), notes: transaction.notes ?? '' })}>edit</button></td>
                </tr>
              )
            ))}
            {items.length === 0 && !transactions.loading && (
              <tr><td colSpan={7} className="muted">No transactions match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
