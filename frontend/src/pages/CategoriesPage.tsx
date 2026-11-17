import { useState } from 'react'
import { api, type Category, type CategoryKind } from '../api'
import { useLoad } from '../hooks'

const KINDS: { value: CategoryKind; label: string; hint: string }[] = [
  { value: 'expense', label: 'Expenses', hint: 'Money going out' },
  { value: 'income', label: 'Income', hint: 'Money coming in' },
  { value: 'savings', label: 'Savings & investments', hint: 'Counted as saved, not spent' },
  { value: 'transfer', label: 'Internal transfers', hint: 'Between your own accounts; ignored in totals' },
]

export default function CategoriesPage() {
  const categories = useLoad(() => api.categories.list())
  const rules = useLoad(() => api.categories.rules())
  const [newCategory, setNewCategory] = useState<{ name: string; kind: CategoryKind }>({ name: '', kind: 'expense' })
  const [newRule, setNewRule] = useState<{ pattern: string; category_id: string; match_type: string }>({ pattern: '', category_id: '', match_type: 'contains' })
  const [message, setMessage] = useState<string | null>(null)

  const categoryById = new Map((categories.data ?? []).map((category) => [category.id, category]))

  async function createCategory() {
    if (!newCategory.name.trim()) return
    await api.categories.create({ name: newCategory.name.trim(), kind: newCategory.kind })
    setNewCategory({ name: '', kind: 'expense' })
    categories.reload()
  }

  async function createRule() {
    if (!newRule.pattern.trim() || !newRule.category_id) return
    const result = await api.categories.createRule({ category_id: Number(newRule.category_id), pattern: newRule.pattern.trim(), match_type: newRule.match_type })
    setMessage(`Rule saved and applied to ${result.applied_to} transaction(s).`)
    setNewRule({ pattern: '', category_id: '', match_type: 'contains' })
    rules.reload()
  }

  async function reapply() {
    const result = await api.categories.reapplyRules()
    setMessage(`Rules re-applied: ${result.changed} transaction(s) changed.`)
  }

  return (
    <div>
      <h1>Categories & rules</h1>
      {message && <div className="alert success">{message} <button className="link" onClick={() => setMessage(null)}>dismiss</button></div>}

      <div className="grid cols-2">
        <div className="card">
          <h2>Categories</h2>
          <div className="inline-form" style={{ marginBottom: 12 }}>
            <input placeholder="New category name" value={newCategory.name} onChange={(event) => setNewCategory({ ...newCategory, name: event.target.value })} />
            <select value={newCategory.kind} onChange={(event) => setNewCategory({ ...newCategory, kind: event.target.value as CategoryKind })}>
              {KINDS.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
            </select>
            <button className="primary" onClick={createCategory} disabled={!newCategory.name.trim()}>Add</button>
          </div>
          {KINDS.map((kind) => (
            <div key={kind.value} style={{ marginBottom: 12 }}>
              <div className="small muted" style={{ marginBottom: 4 }}>{kind.label} — {kind.hint}</div>
              {categories.data?.filter((category) => category.kind === kind.value).map((category) => (
                <div key={category.id} className="inline-form" style={{ padding: '3px 0' }}>
                  <span className="dot" style={{ background: category.color ?? 'var(--text-muted)' }} />
                  <span style={{ flex: 1 }}>{category.name}</span>
                  {category.kind === 'expense' && (
                    <select value={category.necessity ?? ''} title="Essential spending is hard to cut; flexible is discretionary" onChange={async (event) => { await api.categories.update(category.id, { necessity: (event.target.value || null) as Category['necessity'] }); categories.reload() }}>
                      <option value="">unclassified</option>
                      <option value="essential">essential</option>
                      <option value="flexible">flexible</option>
                    </select>
                  )}
                  <span className="small muted">{rules.data?.filter((rule) => rule.category_id === category.id).length ?? 0} rules</span>
                  <button className="danger small" onClick={async () => { await api.categories.remove(category.id); categories.reload(); rules.reload() }} title="Transactions in this category become uncategorized">×</button>
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="card">
          <h2>Rules</h2>
          <p className="small muted">A rule files every transaction whose label contains the pattern (case-insensitive) under a category. Rules you create from the Transactions page get priority over the defaults.</p>
          <div className="inline-form" style={{ marginBottom: 12 }}>
            <input placeholder="Pattern (e.g. carrefour)" value={newRule.pattern} onChange={(event) => setNewRule({ ...newRule, pattern: event.target.value })} />
            <select value={newRule.match_type} onChange={(event) => setNewRule({ ...newRule, match_type: event.target.value })}>
              <option value="contains">contains</option>
              <option value="regex">regex</option>
            </select>
            <select value={newRule.category_id} onChange={(event) => setNewRule({ ...newRule, category_id: event.target.value })}>
              <option value="">Category…</option>
              {categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
            <button className="primary" onClick={createRule} disabled={!newRule.pattern.trim() || !newRule.category_id}>Add rule</button>
            <button onClick={reapply}>Re-apply all rules</button>
          </div>
          <table>
            <thead><tr><th>Pattern</th><th>Type</th><th>Category</th><th>Priority</th><th></th></tr></thead>
            <tbody>
              {rules.data?.map((rule) => (
                <tr key={rule.id}>
                  <td><code>{rule.pattern}</code></td>
                  <td className="muted small">{rule.match_type}</td>
                  <td>{categoryById.get(rule.category_id)?.name ?? rule.category_id}</td>
                  <td className="muted">{rule.priority}</td>
                  <td><button className="danger" onClick={async () => { await api.categories.removeRule(rule.id); rules.reload() }}>×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
