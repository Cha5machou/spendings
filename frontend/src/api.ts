export type AccountKind = 'checking' | 'credit_card' | 'savings' | 'investment' | 'loan' | 'crypto' | 'other'
export type CategoryKind = 'expense' | 'income' | 'transfer' | 'savings'
export type CategorySource = 'none' | 'rule' | 'ai' | 'manual'

export interface Account {
  id: number
  name: string
  bank: string | null
  kind: AccountKind
  currency: string
  is_active: boolean
  notes: string | null
  overdraft_limit: number
  statement_balance: number | null
  statement_balance_date: string | null
  transaction_count: number
  current_balance: number | null
  movements_since_statement: number
  available: number | null
}

export interface Category {
  id: number
  name: string
  kind: CategoryKind
  parent_id: number | null
  color: string | null
  is_default: boolean
}

export interface CategoryRule {
  id: number
  category_id: number
  pattern: string
  match_type: string
  priority: number
}

export interface Transaction {
  id: number
  account_id: number
  document_id: number | null
  date: string
  label: string
  amount: number
  currency: string
  category_id: number | null
  category_source: CategorySource
  notes: string | null
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  total_amount: number
}

export interface Document {
  id: number
  account_id: number | null
  filename: string
  mime_type: string
  size_bytes: number
  status: 'uploaded' | 'imported' | 'failed'
  extraction_method: string | null
  transactions_imported: number
  duplicates_skipped: number
  closing_balance: number | null
  period_end: string | null
  error: string | null
  uploaded_at: string
}

export interface ImportSummary {
  document_id: number
  status: string
  extraction_method: string | null
  transactions_imported: number
  duplicates_skipped: number
  auto_categorized: number
  warnings: string[]
  error: string | null
}

export interface CategoryTotal {
  category_id: number | null
  category_name: string
  kind: CategoryKind | null
  color: string | null
  total: number
  count: number
}

export interface MonthTotals {
  month: string
  income: number
  expenses: number
  savings: number
  net: number
}

export interface Dashboard {
  start: string
  end: string
  income: number
  expenses: number
  savings: number
  net: number
  by_category: CategoryTotal[]
  by_month: MonthTotals[]
  uncategorized_count: number
  top_merchants: CategoryTotal[]
}

export interface Health {
  status: string
  claude_available: boolean
  storage: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      // keep statusText
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export const api = {
  health: () => request<Health>('/health'),

  accounts: {
    list: () => request<Account[]>('/accounts'),
    create: (payload: Partial<Account>) => request<Account>('/accounts', json('POST', payload)),
    update: (id: number, payload: Partial<Account>) => request<Account>(`/accounts/${id}`, json('PATCH', payload)),
    remove: (id: number) => request<void>(`/accounts/${id}`, { method: 'DELETE' }),
  },

  categories: {
    list: () => request<Category[]>('/categories'),
    create: (payload: Partial<Category>) => request<Category>('/categories', json('POST', payload)),
    update: (id: number, payload: Partial<Category>) => request<Category>(`/categories/${id}`, json('PATCH', payload)),
    remove: (id: number) => request<void>(`/categories/${id}`, { method: 'DELETE' }),
    rules: () => request<CategoryRule[]>('/categories/rules'),
    createRule: (payload: { category_id: number; pattern: string; match_type?: string; priority?: number }) =>
      request<CategoryRule & { applied_to: number }>('/categories/rules', json('POST', payload)),
    removeRule: (id: number) => request<void>(`/categories/rules/${id}`, { method: 'DELETE' }),
    reapplyRules: () => request<{ changed: number }>('/categories/rules/apply', { method: 'POST' }),
  },

  documents: {
    list: () => request<Document[]>('/documents'),
    upload: (accountId: number, file: File) => {
      const form = new FormData()
      form.set('account_id', String(accountId))
      form.set('file', file)
      return request<ImportSummary>('/documents/upload', { method: 'POST', body: form })
    },
    reextract: (id: number) => request<{ updated_labels: number; added: number; removed: number }>(`/documents/${id}/reextract`, { method: 'POST' }),
    remove: (id: number, deleteTransactions: boolean) =>
      request<void>(`/documents/${id}${query({ delete_transactions: deleteTransactions })}`, { method: 'DELETE' }),
  },

  transactions: {
    list: (params: {
      account_id?: number
      category_id?: number
      uncategorized?: boolean
      start?: string
      end?: string
      search?: string
      limit?: number
      offset?: number
    }) => request<TransactionPage>(`/transactions${query(params)}`),
    create: (payload: { account_id: number; date: string; label: string; amount: number; category_id?: number | null; notes?: string | null }) =>
      request<Transaction>('/transactions', json('POST', payload)),
    update: (id: number, payload: Partial<Transaction> & { create_rule_pattern?: string }) =>
      request<Transaction>(`/transactions/${id}`, json('PATCH', payload)),
    bulkCategorize: (transaction_ids: number[], category_id: number | null) =>
      request<{ updated: number }>('/transactions/bulk-categorize', json('POST', { transaction_ids, category_id })),
    remove: (id: number) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),
    suggestCategories: () => request<{ applied: number; reviewed: number }>('/transactions/suggest-categories', { method: 'POST' }),
  },

  dashboard: (params: { start?: string; end?: string; account_id?: number }) => request<Dashboard>(`/dashboard${query(params)}`),
}

export function formatMoney(amount: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount)
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR')
}
