import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, BookOpen, CalendarDays, LogOut, Plus, ScanLine, Target, X } from 'lucide-react'
import { useAuth } from '../../app/auth'
import { Brand, ErrorMessage, EmptyState, MockNotice } from '../../components/Shared'
import { study, type Exam } from '../../api/study'

export function WorkspaceLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth(), navigate = useNavigate()
  const { id: examId } = useParams()
  const location = useLocation()
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function signOut() {
    setBusy(true); setError('')
    try { await logout(); navigate('/login', { replace:true }) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  // 最终模拟链接：如果当前在某个 exam 详情/mock 页面，链接到该 exam 的 mock；否则禁用
  const mockTo = examId ? `/app/exams/${examId}/mock` : '#'
  const mockDisabled = !examId
  // 当前路由高亮
  const path = location.pathname
  const isMyExams = path === '/app'
  const isMockRoute = /^\/app\/exams\/[^/]+\/mock$/.test(path)
  return <div className="workspace"><header className="workspace-header"><Brand /><div><span className="account-name">{user?.username}</span><button className="text-button" onClick={signOut} disabled={busy}><LogOut size={16} />退出登录</button></div></header><div className="workspace-body"><aside className="workspace-nav"><span className="tiny-label">学习空间</span><Link className={isMyExams ? 'nav-selected' : ''} to="/app"><BookOpen size={18} />我的备考</Link><span><Target size={18} />专项训练<small>规划中</small></span>{mockDisabled ? <span className="is-disabled"><ScanLine size={18} />最终模拟<small>请先进入考试</small></span> : <Link className={isMockRoute ? 'nav-selected' : ''} to={mockTo}><ScanLine size={18} />最终模拟</Link>}<div className="nav-note">从一份试卷开始，<br />找到复习的下一步。</div><Link className="text-link" to="/">返回首页<ArrowRight size={14} /></Link></aside><main id="main" tabIndex={-1} className="workspace-main"><ErrorMessage error={error} />{children}</main></div></div>
}

function shanghaiDate() {
  return new Intl.DateTimeFormat('en-CA', { timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit' }).format(new Date())
}

export function Workspace() {
  const [exams, setExams] = useState<Exam[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false), [busy, setBusy] = useState(false), [formError, setFormError] = useState('')
  const [course, setCourse] = useState(''), [date, setDate] = useState(''), [target, setTarget] = useState('85'), [maximum, setMaximum] = useState('100')
  const [reload, setReload] = useState(0)
  const intent = useRef({ body:'', key:crypto.randomUUID() }), dialog = useRef<HTMLDialogElement>(null)
  const navigate = useNavigate()
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    study.exams(controller.signal).then(setExams).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reload])
  useEffect(() => { if (showForm) dialog.current?.showModal(); else dialog.current?.close() }, [showForm])
  async function create(event: FormEvent) {
    event.preventDefault(); setFormError('')
    if (Number(target) > Number(maximum)) { setFormError('目标分数不能超过试卷满分'); return }
    const body = { course, examDate:date, targetScore:Number(target), maxScore:Number(maximum) }
    if (intent.current.body !== JSON.stringify(body)) intent.current = { body:JSON.stringify(body), key:crypto.randomUUID() }
    setBusy(true)
    try { const result = await study.create(body, intent.current.key); navigate(`/app/exams/${result.examId}`) }
    catch (e) { setFormError((e as Error).message) } finally { setBusy(false) }
  }
  return <><div className="workspace-title"><div><span className="eyebrow">YOUR STUDY SPACE</span><h1>我的备考</h1><p>把目标写下来，再一步步靠近它。</p></div><button className="button" onClick={() => setShowForm(true)}><Plus size={18} />新建备考计划</button></div><MockNotice />
    {loading ? <div className="empty-state" role="status">正在读取备考计划…</div> : error ? <div className="panel"><ErrorMessage error={error} /><button className="text-button" onClick={() => setReload(x => x + 1)}>重新加载</button></div> : exams.length === 0 ? <EmptyState><BookOpen size={36} /><h2>下一场考试，从这里开始</h2><p>填写课程、考试日期和目标分数，建立第一份备考计划。</p><button className="button button-quiet" onClick={() => setShowForm(true)}>创建第一份计划<ArrowRight size={17} /></button></EmptyState> : <div className="exam-grid">{exams.map(exam => <Link className="exam-card" key={exam.examId} to={`/app/exams/${exam.examId}`}><div className="card-top"><span className="tag">摸底诊断</span><span className="muted">还有 {exam.remainingDays} 天</span></div><h2>{exam.course}</h2><p><CalendarDays size={15} />{exam.examDate}</p><div className="exam-card-bottom"><span>目标 <strong>{exam.targetScore}</strong> / {exam.maxScore} 分</span><ArrowRight size={19} /></div></Link>)}</div>}
    <dialog ref={dialog} onCancel={() => setShowForm(false)} className="create-dialog"><div className="dialog-header"><h2>新建备考计划</h2><button className="icon-button" aria-label="关闭" onClick={() => setShowForm(false)} disabled={busy}><X size={20} /></button></div><p className="muted">先明确目标，后续可以随时回来继续。</p><form className="form-stack" onSubmit={create}><label>课程名称<input autoFocus required maxLength={100} value={course} onChange={e => setCourse(e.target.value)} placeholder="例如：数据结构" /></label><label>考试日期<input type="date" required min={shanghaiDate()} value={date} onChange={e => setDate(e.target.value)} /></label><div className="form-columns"><label>目标分数<input type="number" min="0.1" step="0.1" max={maximum} required value={target} onChange={e => setTarget(e.target.value)} /></label><label>试卷满分<input type="number" min="0.1" step="0.1" required value={maximum} onChange={e => setMaximum(e.target.value)} /></label></div><ErrorMessage error={formError} /><button className="button" disabled={busy}>{busy ? '正在保存…' : '保存并开始诊断'}<ArrowRight size={18} /></button></form></dialog>
  </>
}
