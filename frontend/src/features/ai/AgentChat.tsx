import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Sparkles, Send, Plus, MessageSquare, Trash2, BookOpen,
  AlertCircle, Wrench, ChevronRight, User, Loader2, ArrowRight,
} from 'lucide-react'
import { agent, type AgentMessage, type AgentSession, type ToolCall } from '../../api/agent'
import { ErrorMessage } from '../../components/Shared'

/* ── Tool name → Chinese label ─────────────────────────────── */

const TOOL_LABELS: Record<string, string> = {
  get_study_summary: '查询学习概览',
  query_weak_points: '查询薄弱知识点',
  query_wrong_questions: '查询错题',
  explain_question: '讲解题目',
  generate_practice: '生成练习题',
}

function toolLabel(name: string) {
  return TOOL_LABELS[name] || name
}

/* ── Simple Markdown-ish renderer ──────────────────────────── */

function renderContent(text: string) {
  // Very basic: bold, line breaks, lists. Enough for MVP.
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

  return <div className="tool-call-card">
    <button className="tool-call-header" onClick={() => setOpen(!open)} type="button">
      <Wrench size={14} />
      <span className="tool-call-name">{toolLabel(tc.name)}</span>
      <ChevronRight size={14} className={`tool-call-chevron ${open ? 'open' : ''}`} />
    </button>
    {open && <div className="tool-call-body">
      {tc.arguments && Object.keys(tc.arguments).length > 0 && <div className="tool-call-args">
        <span className="tiny-label">参数</span>
        <pre>{JSON.stringify(tc.arguments, null, 2)}</pre>
      </div>}
      {parsedStr && <div className="tool-call-result">
        <span className="tiny-label">结果</span>
        <pre>{parsedStr}</pre>
      </div>}
    </div>}
  </div>
}

/* ── Single message bubble ─────────────────────────────────── */

function MessageBubble({ msg }: { msg: AgentMessage }) {
  if (msg.role === 'tool') return null  // tool results shown via tool call cards
  const isUser = msg.role === 'user'

  return <div className={`chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-ai'}`}>
    <div className="chat-avatar">{isUser ? <User size={16} /> : <Sparkles size={16} />}</div>
    <div className="chat-bubble">
      {msg.toolCalls.length > 0 && <div className="chat-tools">
        {msg.toolCalls.map((tc, i) => <ToolCallCard key={tc.id || i} tc={tc} />)}
      </div>}
      {msg.content && <div className="chat-text">{renderContent(msg.content)}</div>}
    </div>
  </div>
}

/* ── Quick actions ─────────────────────────────────────────── */

const QUICK_ACTIONS = [
  { label: '分析学习情况', icon: BookOpen, msg: '帮我分析一下目前的学习情况' },
  { label: '薄弱知识点', icon: AlertCircle, msg: '我有哪些薄弱知识点？' },
  { label: '讲解错题', icon: Sparkles, msg: '帮我讲解一下最近的错题' },
]

/* ── Main Agent Chat component ─────────────────────────────── */

export function AgentChat() {
  const [searchParams] = useSearchParams()
  const courseParam = searchParams.get('course')

  // Sessions
  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loadingSessions, setLoadingSessions] = useState(true)

  // Messages
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)

  // Input
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  // Refs
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const justSentRef = useRef(false)  // guard: skip useEffect reload during sendMessage

  // Load sessions
  useEffect(() => {
    const ctrl = new AbortController()
    setLoadingSessions(true)
    agent.sessions(ctrl.signal).then(setSessions).catch(() => {}).finally(() => {
      if (!ctrl.signal.aborted) setLoadingSessions(false)
    })
    return () => ctrl.abort()
  }, [])

  // Load messages when session changes
  useEffect(() => {
    if (!sessionId) { setMessages([]); return }
    // Skip reload if sendMessage just added these messages locally
    if (justSentRef.current) { justSentRef.current = false; return }
    const ctrl = new AbortController()
    setLoadingMessages(true)
    agent.messages(sessionId, ctrl.signal).then(setMessages).catch(() => {}).finally(() => {
      if (!ctrl.signal.aborted) setLoadingMessages(false)
    })
    return () => ctrl.abort()
  }, [sessionId])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  // Auto-resize textarea
  useEffect(() => {
    const el = inputRef.current
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px' }
  }, [input])

  async function sendMessage(text: string) {
    if (!text.trim() || sending) return
    setError('')
    setSending(true)
    setInput('')

    // Optimistic: add user message locally
    const userMsg: AgentMessage = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      toolCalls: [],
      toolCallId: null,
      name: null,
      createdAt: Date.now() / 1000,
    }
    setMessages(prev => [...prev, userMsg])

    try {
      // Mark guard BEFORE awaiting — prevents useEffect from reloading
      // messages that sendMessage is about to add locally
      if (!sessionId) justSentRef.current = true

      const res = await agent.chat(text.trim(), sessionId, courseParam || undefined)

      // Update session id if new
      if (!sessionId) setSessionId(res.sessionId)

      // Build assistant message from response
      const assistantMsg: AgentMessage = {
        id: `resp-${Date.now()}`,
        role: 'assistant',
        content: res.message,
        toolCalls: res.toolCalls || [],
        toolCallId: null,
        name: null,
        createdAt: Date.now() / 1000,
      }
      setMessages(prev => [...prev, assistantMsg])

      // Refresh sessions list
      agent.sessions().then(setSessions).catch(() => {})
    } catch (e) {
      justSentRef.current = false  // allow useEffect to reload on next session change
      setError((e as Error).message)
      // Remove optimistic user message on error
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

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  function newChat() {
    setSessionId(null)
    setMessages([])
    setError('')
    inputRef.current?.focus()
  }

  async function deleteSession(id: string) {
    try {
      await agent.deleteSession(id)
      setSessions(prev => prev.filter(s => s.sessionId !== id))
      if (sessionId === id) newChat()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return <div className="agent-layout">
    {/* ── Session sidebar ── */}
    <aside className="agent-sidebar">
      <button className="agent-new-btn" onClick={newChat} type="button">
        <Plus size={16} />新对话
      </button>
      <div className="agent-session-list">
        {loadingSessions ? <div className="agent-sidebar-empty">加载中…</div>
          : sessions.length === 0 ? <div className="agent-sidebar-empty">暂无对话记录</div>
          : sessions.map(s => <button
              key={s.sessionId}
              className={`agent-session-item ${sessionId === s.sessionId ? 'active' : ''}`}
              onClick={() => setSessionId(s.sessionId)}
              type="button"
            >
              <MessageSquare size={14} />
              <span className="agent-session-title">{s.title}</span>
              <span className="agent-session-delete" onClick={e => { e.stopPropagation(); deleteSession(s.sessionId) }} role="button" tabIndex={-1} aria-label="删除">
                <Trash2 size={12} />
              </span>
            </button>)}
      </div>
    </aside>

    {/* ── Chat main area ── */}
    <div className="agent-chat-main">
      <div className="agent-chat-header">
        <div>
          <Sparkles size={18} />
          <strong>FinalBoost AI</strong>
          {courseParam && <span className="tag tag-muted">{courseParam}</span>}
        </div>
        <span className="agent-header-sub">你的 AI 学习伙伴</span>
      </div>

      {/* Messages */}
      <div className="agent-messages">
        {messages.length === 0 && !sending && <div className="agent-welcome">
          <Sparkles size={36} />
          <h2>FinalBoost AI 学习伙伴</h2>
          <p>我可以帮你分析学习情况、讲解错题、生成练习题。<br />试着问我一个问题吧。</p>
          <div className="agent-quick-actions">
            {QUICK_ACTIONS.map(a => <button
              key={a.label}
              className="agent-quick-btn"
              onClick={() => sendMessage(a.msg)}
              type="button"
              disabled={sending}
            >
              <a.icon size={16} />
              {a.label}
              <ArrowRight size={14} />
            </button>)}
          </div>
        </div>}

        {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}

        {sending && <div className="chat-msg chat-msg-ai">
          <div className="chat-avatar"><Sparkles size={16} /></div>
          <div className="chat-bubble">
            <div className="chat-thinking"><Loader2 size={16} className="spin" /><span>正在思考…</span></div>
          </div>
        </div>}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && <div className="agent-error"><ErrorMessage error={error} /></div>}

      {/* Input */}
      <form className="agent-input-area" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="agent-input"
          placeholder="问我任何关于备考的问题…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={sending}
          maxLength={4000}
        />
        <button className="agent-send-btn" type="submit" disabled={!input.trim() || sending} aria-label="发送">
          {sending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  </div>
}