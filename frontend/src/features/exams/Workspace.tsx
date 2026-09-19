import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, BookOpen, CalendarDays, Database, FileImage, Globe2, LogOut, Plus, ScanLine, ShieldCheck, Sparkles, Target, X } from 'lucide-react'

import { useAuth } from '../../app/auth'
import { Brand, ErrorMessage, EmptyState } from '../../components/Shared'
import { study, type Exam } from '../../api/study'

export function WorkspaceLayout() {

  const { user, logout } = useAuth(), navigate = useNavigate(), location = useLocation()
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function signOut() {
    setBusy(true); setError('')
    try { await logout(); navigate('/login', { replace:true }) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const navClass = ({ isActive }: { isActive:boolean }) => isActive ? 'nav-selected' : undefined
  const privateSelected = location.pathname === '/app/question-bank' || location.pathname === '/app/question-bank/upload' || location.pathname.startsWith('/app/question-bank/papers/')
  return <div className="workspace"><header className="workspace-header"><Brand /><div><span className="account-name">{user?.username}{user?.role==='admin' ? ' · 管理员' : ''}</span><button className="text-button" onClick={signOut} disabled={busy}><LogOut size={16} />退出登录</button></div></header><div className="workspace-body"><aside className="workspace-nav"><span className="label-text">学习空间</span><NavLink end className={navClass} to="/app"><BookOpen size={18} />我的备考</NavLink><NavLink end className={privateSelected ? 'nav-selected' : undefined} to="/app/question-bank"><Database size={18} />私人题库</NavLink><NavLink className={navClass} to="/app/question-bank/public"><Globe2 size={18} />公共题库</NavLink>{user?.role==='admin' && <NavLink className={navClass} to="/app/admin/question-bank"><ShieldCheck size={18} />题库管理</NavLink>}<span className="nav-planned"><Target size={18} />专项训练<small>规划中</small></span><span className="nav-planned"><ScanLine size={18} />最终模拟<small>规划中</small></span><div className="nav-workflow"><span className="tiny-label">在一场考试中完成</span><p><FileImage size={16} />上传与批改</p><p><Sparkles size={16} />AI 对话与复习</p></div><div className="nav-note">从一份试卷开始，<br />找到复习的下一步。</div><Link className="text-link nav-home" to="/">返回首页<ArrowRight size={14} /></Link></aside><main id="main" tabIndex={-1} className="workspace-main"><ErrorMessage error={error} /><Outlet /></main></div></div>
}

function openDatePicker(input: HTMLInputElement) {
  try {
    input.showPicker?.()
  } catch {
    // Keep native editing available when an embedded browser blocks the picker API.
    input.focus()
  }

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
  return <><div className="workspace-title"><div><span className="eyebrow">MY STUDY DESK</span><h1>我的备考</h1><p>从试卷里的问题，找到下一步复习方向。</p></div><button className="button" onClick={() => setShowForm(true)}><Plus size={18} />新建备考计划</button></div><section className="study-intro"><div><span className="eyebrow">A LITTLE CLEARER, EVERY DAY</span><h2>每一份试卷，<br />都是复习的起点。</h2><p>选择一场考试，上传作答。在同一个工作台查看批改，和 AI 一起把错题弄明白。</p></div><ol><li><b>01</b><div><strong>上传试卷</strong><span>保留你的真实作答</span></div><FileImage size={20} /></li><li><b>02</b><div><strong>读懂失分</strong><span>逐题评分与知识点分析</span></div><BookOpen size={20} /></li><li><b>03</b><div><strong>继续追问</strong><span>围绕当前考试与 AI 对话</span></div><Sparkles size={20} /></li></ol></section><div className="study-list-heading"><h2>我的考试</h2><span>{loading ? "正在读取…" : exams.length + " 场备考"} · 选择课程进入工作台</span></div>
    {loading ? <div className="empty-state" role="status">正在读取备考计划…</div> : error ? <div className="panel"><ErrorMessage error={error} /><button className="text-button" onClick={() => setReload(x => x + 1)}>重新加载</button></div> : exams.length === 0 ? <EmptyState><BookOpen size={36} /><h2>下一场考试，从这里开始</h2><p>填写课程、考试日期和目标分数，建立第一份备考计划。</p><button className="button button-quiet" onClick={() => setShowForm(true)}>创建第一份计划<ArrowRight size={17} /></button></EmptyState> : <div className="exam-grid">{exams.map(exam => <Link className="exam-card" key={exam.examId} to={`/app/exams/${exam.examId}`}><div className="card-top"><span className="tag">备考工作台</span><span className="muted">还有 {exam.remainingDays} 天</span></div><h2>{exam.course}</h2><p><CalendarDays size={15} />{exam.examDate}</p><div className="exam-card-bottom"><span>目标 <strong>{exam.targetScore}</strong> / {exam.maxScore} 分</span><span className="exam-card-enter">上传试卷 / 继续复习<ArrowRight size={16} /></span></div></Link>)}</div>}
    <dialog ref={dialog} onCancel={() => setShowForm(false)} className="create-dialog"><div className="dialog-header"><h2>新建备考计划</h2><button className="icon-button" aria-label="关闭" onClick={() => setShowForm(false)} disabled={busy}><X size={20} /></button></div><p className="muted">先明确目标，后续可以随时回来继续。</p><form className="form-stack" onSubmit={create}><label>课程名称<input autoFocus required maxLength={100} value={course} onChange={e => setCourse(e.target.value)} placeholder="例如：数据结构" /></label><label>考试日期<input type="date" onClick={e => openDatePicker(e.currentTarget)} required min={shanghaiDate()} value={date} onChange={e => setDate(e.target.value)} /></label><div className="form-columns"><label>目标分数<input type="number" min="0.1" step="0.1" max={maximum} required value={target} onChange={e => setTarget(e.target.value)} /></label><label>试卷满分<input type="number" min="0.1" step="0.1" required value={maximum} onChange={e => setMaximum(e.target.value)} /></label></div><ErrorMessage error={formError} /><button className="button" disabled={busy}>{busy ? '正在保存…' : '保存并开始诊断'}<ArrowRight size={18} /></button></form></dialog>
  </>
}
