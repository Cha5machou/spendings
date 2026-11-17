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
  necessity: 'essential' | 'flexible' | null
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

export interface InsightCategory {
  category_id: number | null
  name: string
  kind: CategoryKind
  color: string | null
  necessity: 'essential' | 'flexible' | null
  series: number[]
  total: number
  average: number
  median: number
  recent_average: number
  earlier_average: number
  last_month: number
  current_month: number
  one_off_total: number
  transactions: number
  months_present: number
  pattern: 'fixed' | 'recurring' | 'occasional'
  share: number | null
  top_merchants: { name: string; total: number; count: number; last: string | null }[]
}

export interface Recommendation {
  key: string
  severity: 'high' | 'medium' | 'low' | 'info'
  title: string
  detail: string
  monthly_impact: number | null
  category_id: number | null
  saving: boolean
}

export interface InsightsData {
  empty: boolean
  overview: {
    window_start: string | null
    window_end: string | null
    months: number
    typical_income: number
    typical_spending: number
    average_spending_with_one_offs: number
    typical_saved_or_invested: number
    typical_surplus: number
    savings_rate: number | null
    essential_spending: number
    flexible_spending: number
    unclassified_spending: number
    one_off_total: number
    income_one_off_total: number
    uncategorized_transactions: number
  }
  potential_monthly_savings: number
  months: { month: string; income: number; spending: number; saved: number; one_offs: number; income_one_offs: number; partial: boolean }[]
  categories: InsightCategory[]
  recurring: {
    name: string; category_id: number | null; category_name: string; monthly_amount: number; yearly_cost: number
    fixed_amount: boolean; months_seen: number; first_month: string; last_month: string; active: boolean; example_label: string
  }[]
  overdraft: {
    account_id: number; account_name: string; overdraft_limit: number; days_tracked: number; days_negative: number
    days_beyond_limit: number; lowest_balance: number | null; lowest_balance_date: string | null
    by_month: { month: string; days_negative: number; lowest_balance: number | null }[]
  }[]
  recommendations: Recommendation[]
  one_offs: { id: number; date: string; label: string; amount: number; category_name: string }[]
}

export type LoanKind = 'mortgage' | 'personal' | 'revolving' | 'installment' | 'other'

export interface Loan {
  id: number
  name: string
  lender: string | null
  kind: LoanKind
  account_id: number | null
  is_active: boolean
  original_amount: number | null
  start_date: string | null
  remaining_balance: number
  balance_date: string | null
  annual_rate: number
  taeg: number | null
  monthly_payment: number
  insurance_monthly: number
  next_payment_date: string | null
  payments_remaining: number | null
  end_date: string | null
  payment_pattern: string | null
  notes: string | null
  has_schedule: boolean
  current_balance: number
  months_left: number
  projected_end: string | null
  next_payment: { date: string; total: number } | null
  remaining_interest: number
  remaining_insurance: number
  remaining_total: number
  progress: number | null
  last_seen_payment: { date: string; amount: number } | null
}

export interface LoansData {
  loans: Loan[]
  totals: {
    total_debt: number; monthly_payments: number; average_rate: number; remaining_interest_and_insurance: number
    typical_income: number | null; debt_to_income: number | null; last_payment_date: string | null
  }
  timeline: ({ month: string; total: number } & Record<string, number | string>)[]
  timeline_loans: { id: number; name: string; kind: LoanKind }[]
}

export interface PayoffPlan {
  strategy: string
  extra: number
  baseline: { months: number; interest: number; debt_free: string }
  plan: { months: number; interest: number; debt_free: string }
  interest_saved: number
  months_saved: number
  order: { name: string; month: number; date: string; baseline_date: string }[]
  monthly_budget: number
}

export interface WhatIf {
  balance: number
  annual_rate: number
  payment_without_insurance: number
  baseline: { months: number; interest: number; insurance: number; cost: number }
  lump_sum?: {
    amount: number; indemnity_max: number; note: string
    shorter_duration: { months: number; months_saved: number; cost_saved: number }
    lower_payment: { payment: number; monthly_saving: number }
  }
  renegotiation?: { new_rate: number; new_payment: number; monthly_saving: number; interest_saved: number; fees: number; net_saving: number; break_even_months: number }
}

export const api = {
  loans: {
    list: () => request<LoansData>('/loans'),
    create: (payload: Partial<Loan>) => request<Loan>('/loans', json('POST', payload)),
    update: (id: number, payload: Partial<Loan>) => request<Loan>(`/loans/${id}`, json('PATCH', payload)),
    remove: (id: number) => request<void>(`/loans/${id}`, { method: 'DELETE' }),
    importSchedule: (id: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<{ rows: number; first: string; last: string }>(`/loans/${id}/schedule`, { method: 'POST', body: form })
    },
    payoff: (extra: number, strategy: string, includeMortgage: boolean) =>
      request<PayoffPlan>(`/loans/payoff?extra=${extra}&strategy=${strategy}&include_mortgage=${includeMortgage}`),
    whatIf: (id: number, params: { lump_sum?: number; new_rate?: number; fees?: number }) => {
      const query = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) if (value !== undefined && !Number.isNaN(value)) query.set(key, String(value))
      return request<WhatIf>(`/loans/${id}/what-if?${query}`)
    },
  },
  insights: (months = 12) => request<InsightsData>(`/insights?months=${months}`),

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
