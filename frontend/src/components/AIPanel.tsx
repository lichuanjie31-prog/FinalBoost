import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Sparkles, Send, Loader2, Wrench, RotateCcw } from 'lucide-react'
import { agent, type ToolCall } from '../api/agent'

interface Props { course?: string; examId?: string; gradingId?: string; markingJobIds?: string[]; chatMode?: 'mock' | 'llm' }
type Message = { id: string; role: 'user' | 'assistant'; content: string; tools: ToolCall[] }
const labels: Record<string, string> = {
  get_study_summary: '学习概览', query_weak_points: '薄弱知识点',
  query_wrong_questions: '错题记录', explain_question: '题目讲解', generate_practice: '针对性练习',
  query_marking_questions: '批改题目详情',
}
export function AIPanel({ course, examId, gradingId, markingJobIds, chatMode }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  const log = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (log.current && (messages.length || sending)) log.current.scrollTop = log.current.scrollHeight }, [messages, sending])
  async function send(text: string) {
    const content = text.trim()
    if (!content || lock.current || !chatMode) return
    lock.current = true; setSending(true); setError(''); setInput('')
    const message: Message = { id: crypto.randomUUID(), role: 'user', content, tools: [] }
    setMessages(old => [...old, message])
    try {
      const result = await agent.chat(content, sessionId, course, { examId, gradingId, markingJobIds })
      if (!result.message?.trim()) throw new Error('暂未生成完整回答，请重试或缩小问题范围。')
      setSessionId(result.sessionId)
      setMessages(old => [...old, { id: crypto.randomUUID(), role: 'assistant', content: result.message, tools: result.toolCalls || [] }])
    } catch (e) {
      setError((e as Error).message); setMessages(old => old.filter(m => m.id !== message.id)); setInput(content)
    } finally {
      lock.current = false; setSending(false)
      requestAnimationFrame(() => textarea.current?.focus())
    }
  }
  function submit(event: FormEvent) { event.preventDefault(); void send(input) }
  return <section className="study-chat" aria-label="AI 备考助手">
    <header className="study-chat-header"><div className="study-chat-icon"><Sparkles size={20} /></div><div><h2>AI 备考助手</h2><p>{chatMode === 'llm' ? '已连接模型' : chatMode === 'mock' ? '示例对话 · 尚未连接模型' : '正在确认服务状态'}</p></div>
      <button className="icon-button" type="button" aria-label="新建对话" disabled={sending || !messages.length} onClick={() => { setMessages([]); setSessionId(null); setError(''); setInput('') }}><RotateCcw size={17} /></button>
    </header>
    <div className="chat-context"><span className="context-dot" />{course || '当前考试'}<span>{gradingId || markingJobIds?.length ? `已关联所选批改结果${markingJobIds?.length ? `（${markingJobIds.length} 页）` : ''}` : '等待上传试卷'}</span></div>
    <div ref={log} className="study-chat-log" role="log" aria-label="备考对话记录" aria-live="polite" aria-relevant="additions text">
      {!messages.length && <div className="chat-welcome"><span className="chat-welcome-mark"><Sparkles size={28} /></span><h3>把不会的，弄明白。</h3><p>上传试卷后，和我一起梳理失分原因。也可以直接问一道题。</p><div className="chat-suggestions">{['分析这次判卷结果', '帮我讲解错题', '我应该先复习什么？'].map(text => <button type="button" key={text} disabled={sending || !chatMode} onClick={() => void send(text)}>{text}<span aria-hidden="true">↗</span></button>)}</div></div>}
      {messages.map(message => <article key={message.id} className={'study-message ' + message.role}><span className="message-author">{message.role === 'user' ? '你' : '备考助手'}</span><div className="message-content">{message.content}</div>{message.tools.map((tool, i) => <details className="study-tool" key={tool.id + i}><summary><Wrench size={14} />{labels[tool.name.replace(/_context$/, '')] || '学习资料'}</summary><pre>{tool.result || '已完成查询'}</pre></details>)}</article>)}
      {sending && <p className="chat-thinking" role="status"><Loader2 size={16} className="spin" />正在结合当前考试分析…</p>}
    </div>
    {error && <div className="chat-error" role="alert">{error} 原问题已保留，可重新发送。</div>}
    <form className="study-chat-form" onSubmit={submit}><label htmlFor="study-question">继续追问</label><textarea id="study-question" ref={textarea} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(input) } }} placeholder="例如：这道题为什么要这样解？" maxLength={4000} rows={3} disabled={sending} /><div><small>Enter 发送 · Shift + Enter 换行</small><button type="submit" aria-label="发送" disabled={!input.trim() || sending || !chatMode}>{sending ? <Loader2 size={17} className="spin" /> : <Send size={17} />}</button></div></form>
    <p className="chat-footnote">{chatMode === 'mock' ? '当前回复为示例内容，不代表模型分析。' : 'AI 分析仅供复习参考，请核对题目与答案。'}</p>
  </section>
}
