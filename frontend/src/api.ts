import { authToken } from './auth'

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
  const token = await authToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`/api${path}`, { ...init, headers })
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

export interface PropertyData {
  id: number
  name: string
  address: string | null
  furnished: boolean
  surface_m2: number | null
  purchase_price: number | null
  purchase_date: string | null
  furnishing_and_works: number
  market_value: number | null
  lease_start: string | null
  monthly_rent: number
  monthly_charges: number
  deposit: number | null
  agency: string | null
  management_fee_rate: number
  rent_insurance_rate: number
  syndic_quarterly: number
  property_tax_yearly: number
  notes: string | null
  checks: { severity: 'high' | 'medium' | 'low' | 'info'; title: string; detail: string }[]
  months: { month: string; rent: number; costs: number; mortgage: number; net: number; cumulative: number }[]
  totals: { rent: number; costs: number; mortgage: number; net: number }
  months_with_rent: number
  lines: { label: string; amount: number }[]
  monthly_result: number
  operating_result: number
  net_from_agency: number
  yields: { gross: number | null; net_of_costs: number | null; loan_rate: number | null }
  levers: { label: string; monthly: number }[]
  invested: number
  loan: { id: number; name: string; balance: number; rate: number; remaining_months: number } | null
}

export interface SaleScenario {
  price: number
  agent_fee: number
  loan_balance: number
  early_repayment_indemnity_max: number
  estimated_gain_tax: number
  net_proceeds: number
  monthly_result_if_kept: number
  months_of_losses_equivalent: number | null
  note: string
}

export interface WealthData {
  accounts: { account_id: number; name: string; kind: string; bank: string | null; balance: number; as_of: string | null; since_first: number | null; first_date: string | null; change_12m: number | null; holdings_total: number }[]
  history: ({ date: string; total: number } & Record<string, number | string>)[]
  net_worth: {
    checking: number; cash_savings: number; invested: number; consumer_debt: number; financial: number
    property_value: number; property_basis: string; mortgage: number; property_equity: number; total: number
  }
  allocation: { asset_class: string; label: string; value: number }[]
  checks: { severity: 'high' | 'medium' | 'low' | 'info'; title: string; detail: string }[]
  checking: { account_id: number; name: string; balance: number | null }[]
  holdings: { account_id: number; name: string; identifier: string | null; asset_class: string; value: number; gain_loss: number | null; as_of: string | null }[]
  liabilities: { name: string; balance: number; kind: string }[]
}

export interface IncomeData {
  empty: boolean
  payslips: { month: string; gross: number; net_before_tax: number; tax_rate: number; tax_withheld: number; net_paid: number; bonus: number | null }[]
  employer: string | null
  months: number
  average: { gross: number; net_before_tax: number; tax_withheld: number; net_paid: number }
  annual_gross: number
  annual_taxable_estimate: number
  withholding_share: number
  marginal_rate: number
  per: { ceiling_estimate: number; tax_saved_per_1000: number; max_tax_saved: number }
  net_share_of_gross: number
}

export interface PlanSettingsData {
  split_pea: number; split_cto: number; split_livrets: number; av_monthly: number; livrets_target: number; expected_return_pct: number
  new_credit_monthly: number; housing_delta: number; sale_date: string | null; sale_price: number | null; sale_agent_fee_pct: number
  purchase_date: string | null; purchase_price: number | null; purchase_savings_share_pct: number; loan_rate_pct: number; loan_years: number
  loan_insurance_pct: number; notary_fees_pct: number; rent_weight_pct: number; max_debt_ratio_pct: number
}

export interface PlanAffordability {
  sells_flat: boolean; bank_income: number; existing_debt_payments: number; max_total_payment: number; room_for_new_loan: number
  capital_max: number; down_payment: number; price_max: number
  grid: { price: number; capital: number; payment: number; ratio: number | null; feasible: boolean }[]
}

export interface PlanData {
  settings: PlanSettingsData
  context: { salary_net: number; rent_net: number; flat_costs: number; core_spending: number; housing_cost: number; checking: number; balances: Record<string, number>; essential_typical: number }
  property_name: string | null
  projection: { month: string; income: number; spending: number; debt_service: number; av: number; surplus: number; invested: number; cash: number
    pea: number; cto: number; av_balance: number; livrets: number; sale_pot: number; total: number; events: { type: string; amount: number }[] }[]
  milestones: { first_surplus_month: string | null; overdraft_cleared_month: string | null; steady_surplus: number | null
    savings_2027_12: number | null; savings_2028_12: number | null; savings_2029_06: number | null; savings_end: number | null }
  housing_scenarios: { delta: number; monthly_cost: number; surplus_next_month: number; surplus_2027_09: number | null; savings_end_2028: number | null }[]
  sale: { date: string; price: number; price_basis: string; agent_fee: number; loan_balance: number; indemnity: number; gain_tax: number; net_proceeds: number } | null
  purchase: { date: string; savings_pool: number; keep_flat: PlanAffordability; sell_flat: PlanAffordability }
  split_check: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export const api = {
  assistant: {
    ask: (messages: ChatMessage[]) =>
      request<{ answer: string; tools_used: string[]; usage: { input_tokens: number; output_tokens: number } }>('/assistant', json('POST', { messages })),
  },
  plan: {
    get: () => request<PlanData>('/plan'),
    update: (payload: Partial<PlanSettingsData> & { clear_sale_price?: boolean; clear_purchase_price?: boolean }) => request<unknown>('/plan/settings', json('PATCH', payload)),
  },
  wealth: {
    get: () => request<WealthData>('/wealth'),
    snapshot: (accountId: number, day: string, balance: number) =>
      request<{ ok: boolean }>('/wealth/snapshots', json('POST', { account_id: accountId, date: day, balance, source: 'manual' })),
  },
  income: {
    get: () => request<IncomeData>('/income'),
    uploadPayslips: (files: FileList) => {
      const form = new FormData()
      for (const file of Array.from(files)) form.append('files', file)
      return request<{ imported: string[]; failed: { filename: string; error: string }[] }>('/income/payslips', { method: 'POST', body: form })
    },
  },
  properties: {
    list: () => request<PropertyData[]>('/properties'),
    update: (id: number, payload: Partial<PropertyData>) => request<PropertyData>(`/properties/${id}`, json('PATCH', payload)),
    sale: (id: number, price: number, agentFeePercent: number) => request<SaleScenario>(`/properties/${id}/sale?price=${price}&agent_fee_percent=${agentFeePercent}`),
  },
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
