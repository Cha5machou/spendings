import { useRef, useState, type ReactNode } from 'react'
import { api, type ChatMessage } from '../api'
import { useLoad } from '../hooks'

const SUGGESTIONS = [
  'Where could I realistically cut 200 euros a month?',
  'Summarise my last month in five lines.',
  'What if my housing cost goes up by 200 euros a month?',
  'Which of my credits should I pay off first, and what would it save?',
  'Am I on track for my goals?',
]

const TOOL_LABEL: Record<string, string> = {
  get_spending_analysis: 'spending', search_transactions: 'transactions', get_accounts: 'accounts', get_loans: 'loans', get_rental_property: 'rental flat',
  get_wealth: 'savings', get_income: 'income', get_plan: 'plan', run_plan_scenario: 'what-if on the plan',
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  )
}

/** Tiny, safe renderer for the subset of markdown the assistant uses: paragraphs, bullet lists, bold. */
function Answer({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let bullets: string[] = []
  const flush = () => {
    if (bullets.length) {
      blocks.push(<ul key={`ul${blocks.length}`}>{bullets.map((item, index) => <li key={index}>{inline(item)}</li>)}</ul>)
      bullets = []
    }
  }
  for (const line of text.split('\n')) {
    const bullet = line.match(/^\s*[-*]\s+(.*)/)
    if (bullet) bullets.push(bullet[1])
    else {
      flush()
      if (line.trim()) blocks.push(<p key={`p${blocks.length}`} style={{ margin: '6px 0' }}>{inline(line)}</p>)
    }
  }
  flush()
  return <>{blocks}</>
}

export default function AskPage() {
  const health = useLoad(() => api.health())
  const [messages, setMessages] = useState<(ChatMessage & { tools?: string[] })[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  async function send(question: string) {
    const text = question.trim()
    if (!text || busy) return
    const next = [...messages, { role: 'user' as const, content: text }]
    setMessages(next)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const reply = await api.assistant.ask(next.map(({ role, content }) => ({ role, content })))
      setMessages([...next, { role: 'assistant', content: reply.answer, tools: reply.tools_used }])
    } catch (askError) {
      setError((askError as Error).message)
    } finally {
      setBusy(false)
      setTimeout(() => bottom.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    }
  }

  return (
    <div>
      <h1>Ask</h1>
      {health.data && !health.data.claude_available && (
        <div className="alert error">The assistant needs an Anthropic API key: add ANTHROPIC_API_KEY to backend/.env and restart.</div>
      )}
      <p className="small muted">Ask anything about your own numbers. The assistant reads your data to answer, and can test what-ifs on your plan without changing it. Your question and the figures it looks up are sent to the Claude API (see Anthropic's data policy for how they are handled). It is not a licensed adviser: check tax and loan decisions with a professional.</p>

      {messages.length === 0 && (
        <div className="chips" style={{ marginBottom: 16 }}>
          {SUGGESTIONS.map((suggestion) => <button key={suggestion} className="chip" onClick={() => send(suggestion)}>{suggestion}</button>)}
        </div>
      )}

      {messages.map((message, index) => (
        <div key={index} className="card" style={message.role === 'user' ? { background: 'var(--bg)' } : undefined}>
          <div className="small muted" style={{ marginBottom: 4 }}>{message.role === 'user' ? 'You' : 'Assistant'}</div>
          {message.role === 'user' ? <div>{message.content}</div> : <Answer text={message.content} />}
          {message.tools && message.tools.length > 0 && (
            <div className="small muted" style={{ marginTop: 8 }}>Looked at: {[...new Set(message.tools)].map((tool) => TOOL_LABEL[tool] ?? tool).join(', ')}</div>
          )}
        </div>
      ))}
      {busy && <p className="muted">Looking at your numbers…</p>}
      {error && <div className="alert error">{error}</div>}

      <div className="inline-form" style={{ position: 'sticky', bottom: 0, background: 'var(--bg)', padding: '8px 0' }}>
        <input style={{ flex: 1, minWidth: 240 }} placeholder="Ask about your money…" value={input} disabled={busy}
          onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') send(input) }} />
        <button className="primary" onClick={() => send(input)} disabled={busy || !input.trim()}>Ask</button>
        {messages.length > 0 && <button onClick={() => { setMessages([]); setError(null) }}>New conversation</button>}
      </div>
      <div ref={bottom} />
    </div>
  )
}
