import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Sparkles, ArrowRight, X, Send, Loader2, Wrench, ChevronRight, User } from 'lucide-react'
import { agent, type ToolCall } from '../api/agent'

/* ── Props ─────────────────────────────────────────────────── */

interface AIPanelProps {
  /** Course name for context */
  course?: string
  /** Associated exam ID — injects grading context into AI */
  examId?: string
  /** Associated grading ID — lets AI analyze specific grading result */
  gradingId?: string
  /** Initial prompt to send automatically (e.g. after grading completes) */
  autoMessage?: string
  /** Compact mode: show as a small card that can expand */
  compact?: boolean
}

/* ── Tool labels ───────────────────────────────────────────── */

const TOOL_LABELS: Record<string, string> = {
  get_study_summary: '查询学习概览',
  query_weak_points: '查询薄弱知识点',
  query_wrong_questions: '查询错题',
  explain_question: '讲解题目',
  generate_practice: '生成练习题',
}

/* ── Simple markdown renderer ──────────────────────────────── */

function renderMd(text: string) {
  const html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>')
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

/* ── Tool call card ────────────────────────────────────────── */

function ToolCallCard({ tc }: { tc: ToolCall }) {
  const [open, setOpen] = useState(false)
  let parsedStr = ''
  if (tc.result) {
    try {
      const obj = JSON.parse(tc.result)
      parsedStr = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)
    } catch { parsedStr = tc.result }
  }
  return <div className="ai-tool-card">
    <button className="ai-tool-header" onClick={() => setOpen(!open)} type="button">
      <Wrench size={13} /><span>{TOOL_LABELS[tc.name] || tc.name}</span>
      <ChevronRight size={13} className={`ai-tool-chevron ${open ? 'open' : ''}`} />
    </button>
    {open && parsedStr && <pre className="ai-tool-body">{parsedStr}</pre>}
  </div>
}

/* ── Message type ──────────────────────────────────────────── */

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls: ToolCall[]
}

/* ── AIPanel component ─────────────────────────────────────── */

export function AIPanel({ course, examId, gradingId, autoMessage, compact }: AIPanelProps) {
  const [expanded, setExpanded] = useState(!!autoMessage)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [hasAutoSent, setHasAutoSent] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  // Auto-resize textarea
  useEffect(() => {
    const el = inputRef.current
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px' }
  }, [input])

  // Auto-send the initial message (e.g. after grading completes)
  useEffect(() => {
    if (autoMessage && !hasAutoSent && expanded) {
      setHasAutoSent(true)
      sendMessage(autoMessage)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, autoMessage, hasAutoSent])

  async function sendMessage(text: string) {
    if (!text.trim() || sending) return
    setError('')
    setSending(true)
    setInput('')
    setExpanded(true)

    const userMsg: Msg = { id: `u-${Date.now()}`, role: 'user', content: text.trim(), toolCalls: [] }
    setMessages(prev => [...prev, userMsg])

    try {
      const res = await agent.chat(text.trim(), sessionId, course || undefined)
      if (!sessionId) setSessionId(res.sessionId)

      const aiMsg: Msg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: res.message,
        toolCalls: res.toolCalls || [],
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (e) {
      setError((e as Error).message)
      setMessages(prev => prev.filter(m => m.id !== userMsg.id))
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    sendMessage(input)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  /* ── Compact card mode (not expanded yet) ── */
  if (compact && !expanded && messages.length === 0) {
    return <div className="ai-panel-card" onClick={() => { setExpanded(true); setTimeout(() => inputRef.current?.focus(), 100) }}>
      <div className="ai-panel-card-icon"><Sparkles size={18} /></div>
      <div className="ai-panel-card-text">
        <strong>问问 AI</strong>
        <span>针对这次判卷结果，让 AI 分析你的薄弱点</span>
      </div>
      <ArrowRight size={16} />
    </div>
  }

  /* ── Full panel mode ── */
  return <div className="ai-panel">
    {/* Header */}
    <div className="ai-panel-header">
      <div><Sparkles size={16} /><strong>AI 学伴</strong>{course && <span className="tag tag-muted">{course}</span>}</div>
      {compact && <button className="ai-panel-close" onClick={() => { setExpanded(false); setMessages([]); setSessionId(null) }} type="button" aria-label="关闭"><X size={16} /></button>}
    </div>

    {/* Messages */}
    <div className="ai-panel-messages">
      {messages.length === 0 && !sending && <div className="ai-panel-empty">
        <Sparkles size={24} />
        <p>我可以帮你分析判卷结果、讲解错题、生成练习题。</p>
      </div>}

      {messages.map(msg => <div key={msg.id} className={`ai-msg ${msg.role === 'user' ? 'ai-msg-user' : 'ai-msg-ai'}`}>
        <div className="ai-msg-avatar">{msg.role === 'user' ? <User size={14} /> : <Sparkles size={14} />}</div>
        <div className="ai-msg-body">
          {msg.toolCalls.length > 0 && <div className="ai-msg-tools">
            {msg.toolCalls.map((tc, i) => <ToolCallCard key={tc.id || i} tc={tc} />)}
          </div>}
          {msg.content && <div className="ai-msg-text">{renderMd(msg.content)}</div>}
        </div>
      </div>)}

      {sending && <div className="ai-msg ai-msg-ai">
        <div className="ai-msg-avatar"><Sparkles size={14} /></div>
        <div className="ai-msg-body"><div className="ai-thinking"><Loader2 size={14} className="spin" /><span>正在分析…</span></div></div>
      </div>}

      <div ref={bottomRef} />
    </div>

    {/* Error */}
    {error && <div className="ai-panel-error">{error}</div>}

    {/* Input — v0-style dark box */}
    <form className="ai-panel-input-wrap" onSubmit={handleSubmit}>
      <div className="ai-panel-input-box">
        <textarea
          ref={inputRef}
          className="ai-panel-input"
          placeholder="问 AI 任何关于备考的问题…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={sending}
          maxLength={4000}
        />
        <div className="ai-panel-input-actions">
          <button className="ai-send-btn" type="submit" disabled={!input.trim() || sending} aria-label="发送">
            {sending ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </form>
  </div>
}