import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Upload, FileImage, RefreshCw, CheckCircle2, X } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { AIPanel } from '../../components/AIPanel'
import { study, type Exam, type Grading, type Diagnosis } from '../../api/study'
import { capabilities, type Capabilities, type MarkingMode } from '../../api/capabilities'
import { QuestionScores } from './QuestionScores'
import { MarkingStudy } from './MarkingStudy'

type LocalFile = { file:File; key:string; uploadedId?:string }
export function ExamDetail() {
  const { id = '' } = useParams()
  const [mode, setMode] = useState<MarkingMode | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    // The backend decides which pathway is live: real Tencent marking, or the
    // clearly-labelled local demo. The demo never pretends to be a real result.
    capabilities(controller.signal)
      .then(state => { if (!controller.signal.aborted) setMode(state.markingMode || 'disabled') })
      .catch(() => { if (!controller.signal.aborted) setMode('disabled') })
    return () => controller.abort()
  }, [id])
  if (mode === null) return <div className="empty-state" role="status">正在读取批改服务状态…</div>
  return mode === 'disabled' ? <ExamStudy key={id} id={id} /> : <MarkingStudy key={id} id={id} />
}
function Preview({ file }: { file: File }) {
  const [url, setUrl] = useState('')
  useEffect(() => { const value = URL.createObjectURL(file); setUrl(value); return () => URL.revokeObjectURL(value) }, [file])
  return url ? <img src={url} alt={file.name} /> : null
}
function ExamStudy({ id }: { id: string }) {
  const [exam, setExam] = useState<Exam | null>(null), [jobs, setJobs] = useState<Grading[]>([]), [diagnoses, setDiagnoses] = useState<Diagnosis[]>([])
  const [files, setFiles] = useState<LocalFile[]>([]), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const [error, setError] = useState(''), [uploadError, setUploadError] = useState(''), [diagnosisError, setDiagnosisError] = useState(''), [workingDiagnosis, setWorkingDiagnosis] = useState<string | null>(null)
  const [service, setService] = useState<Capabilities | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const submitLock = useRef(false)
  const [reload, setReload] = useState(0), [progress, setProgress] = useState('')
  const uploadIntent = useRef(crypto.randomUUID()), fileInput = useRef<HTMLInputElement>(null)
  const jobsRef = useRef(jobs); jobsRef.current = jobs
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    Promise.all([study.exam(id,controller.signal), study.gradings(id,controller.signal), study.diagnoses(id,controller.signal), capabilities(controller.signal)]).then(([e,j,d,s]) => { if (!controller.signal.aborted) { setExam(e); setJobs(j); setDiagnoses(d); setService(s) } }).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id,reload])
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>
    async function poll() {
      const pending = jobsRef.current.filter(j => j.status === 'queued' || j.status === 'running')
      if (pending.length) {
        try {
          const updated = await Promise.all(pending.map(j => study.grading(j.gradingId,controller.signal)))
          if (!controller.signal.aborted) { setJobs(old => old.map(j => updated.find(u => u.gradingId === j.gradingId) || j)); setError('') }
        } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
      }
      if (!controller.signal.aborted) timer = setTimeout(poll,2000)
    }
    timer = setTimeout(poll,2000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [id])
  function choose(selected: FileList | null) {
    if (!selected || busy) return
    const candidates = Array.from(selected)
    if (candidates.length + files.length > 10) { setUploadError('一次最多上传 10 张答题图片'); return }
    if (candidates.some(f => !['image/jpeg','image/png','image/webp'].includes(f.type) || f.size > 10*1024*1024)) { setUploadError('请选择 JPEG、PNG 或 WebP 图片，每张不超过 10 MiB'); return }
    setFiles(old => [...old,...candidates.map(file => ({ file,key:crypto.randomUUID() }))]); setUploadError(''); uploadIntent.current = crypto.randomUUID()
    if (fileInput.current) fileInput.current.value = ''
  }
  async function submit() {
    if (submitLock.current || !files.length || !service) return
    submitLock.current = true
    setBusy(true); setUploadError('')
    try {
      const current = [...files]
      for (let i=0;i<current.length;i++) {
        setProgress(`正在上传第 ${i+1} / ${current.length} 张图片`)
        if (!current[i].uploadedId) { const uploaded = await study.upload(current[i].file,current[i].key); current[i] = { ...current[i], uploadedId:uploaded.fileId }; setFiles([...current]) }
      }
      setProgress('正在创建批改任务')
      const accepted = await study.grade(id,current.map(f => f.uploadedId!),uploadIntent.current)
      setSelectedId(accepted.gradingId)
      const job = await study.grading(accepted.gradingId)
      setJobs(old => [...old.filter(j => j.gradingId !== job.gradingId),job]); setFiles([]); uploadIntent.current = crypto.randomUUID()
    } catch (e) { setUploadError((e as Error).message) } finally { submitLock.current = false; setBusy(false); setProgress('') }
  }
  async function diagnose(gid: string) {
    setWorkingDiagnosis(gid); setDiagnosisError('')
    try { const result = await study.diagnose(id,gid); setDiagnoses(old => [result,...old.filter(d => d.diagnosisId !== result.diagnosisId)]) }
    catch (e) { setDiagnosisError((e as Error).message) } finally { setWorkingDiagnosis(null) }
  }
  if (loading) return <div className="empty-state" role="status">正在读取考试记录…</div>
  if (!exam) return <div className="panel"><ErrorMessage error={error} /><button className="button button-quiet" onClick={() => setReload(v=>v+1)}>重新加载</button><Link to="/app" className="text-link">返回我的备考</Link></div>
  const active = jobs.find(j => j.gradingId === selectedId) || jobs[jobs.length - 1]
  const mock = service?.gradingMode === 'mock'
  const resultMock = active?.source === 'mock'
  const completed = active?.status === 'succeeded'
  return <div className="exam-study">
    <Link className="text-link back-link" to="/app"><ArrowLeft size={16} />我的备考</Link>
    <div className="workspace-title"><div><span className="eyebrow">EXAM WORKSPACE</span><h1>{exam.course}</h1><p>{exam.examDate} 考试 · 目标 {exam.targetScore} / {exam.maxScore} 分</p></div><div className="days-left"><strong>{exam.remainingDays}</strong><span>天后考试</span></div></div>
    <div className="study-steps" aria-label="备考流程"><span className="current"><b>01</b>上传试卷</span><span className={active ? 'current' : ''}><b>02</b>查看批改</span><span className={completed ? 'current' : ''}><b>03</b>和 AI 一起复习</span></div>
    <ErrorMessage error={error} />
    {!service && error && <button className="text-button" onClick={() => setReload(v => v + 1)}>重新连接服务</button>}
    <div className="study-columns"><div className="study-materials">
      <section className="panel upload-panel"><div className="panel-title"><div><span className="eyebrow">YOUR PAPER</span><h2>上传试卷，开始查漏补缺</h2></div><FileImage size={22} /></div>
        <p className="muted">上传包含题目与作答的清晰照片，按页码顺序排列。</p>
        {mock && <p className="study-mode">模拟数据，仅用于流程联调</p>}
        <label className={'upload-zone ' + (dragging ? 'is-dragging ' : '') + (busy ? 'is-disabled' : '')} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); choose(e.dataTransfer.files) }}>
          <span className="upload-symbol"><Upload size={26} /></span><strong>拖入试卷照片，或点击选择</strong><span>JPEG、PNG、WebP · 每张最多 10 MiB</span><small>最多 10 张 · 已选 {files.length} 张</small><input ref={fileInput} type="file" aria-label="选择答题图片" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={e => choose(e.target.files)} />
        </label>
        {!!files.length && <ol className="paper-previews">{files.map((entry,index) => <li key={entry.key}><Preview file={entry.file} /><div><strong>第 {index + 1} 页</strong><span>{entry.file.name}</span></div>{entry.uploadedId && <CheckCircle2 size={16} />}<button className="icon-button" disabled={busy} aria-label={'移除 ' + entry.file.name} onClick={() => { setFiles(old => old.filter(f => f.key !== entry.key)); uploadIntent.current = crypto.randomUUID() }}><X size={16} /></button></li>)}</ol>}
        <ErrorMessage error={uploadError} />{progress && <p role="status" className="progress-message">{progress}</p>}
        <button className="button full-width" disabled={busy || !files.length || !service} onClick={submit}>{busy ? '正在提交…' : mock ? '上传并开始模拟判卷' : '上传并开始批改'}<ArrowRight size={17} /></button>
        <p className="fine-print">{mock ? '当前使用固定示例评分，不识别图片内容。连接图像模型后可启用真实批改。' : '模型将读取试卷图片并生成逐题评分。请核对识别内容和评分依据。'}</p>
      </section>
      <section className="panel jobs-panel"><div className="panel-title"><div><span className="eyebrow">FEEDBACK</span><h2>批改结果</h2></div><span className="tag tag-muted">{jobs.length} 次提交</span></div>
        {!active ? <div className="results-empty"><FileImage size={32} /><h3>你的第一份分析，从这里开始</h3><p>提交试卷后，在这里查看分数、失分原因和薄弱知识点。</p></div> : <>
          <label className="record-select">判卷记录<select value={active.gradingId} onChange={e => setSelectedId(e.target.value)}>{[...jobs].reverse().map((job,index) => <option key={job.gradingId} value={job.gradingId}>第 {jobs.length-index} 次提交 · {job.status === 'succeeded' ? '已完成' : job.status === 'failed' ? '失败' : '处理中'}</option>)}</select></label>
          <article className="job-item"><div className="job-title"><strong>{resultMock ? '示例批改' : 'AI 批改'}</strong><span className={'job-status ' + active.status}>{completed ? '判卷完成' : active.status === 'failed' ? '判卷失败' : active.status === 'running' ? '正在判卷' : '排队中'}</span></div>
            {(active.status === 'queued' || active.status === 'running') && <p role="status"><RefreshCw size={16} className="spin" />{active.status === 'queued' ? '任务已排队' : '正在判卷'}，可安全刷新页面</p>}
            {active.status === 'failed' && <><ErrorMessage error={active.error?.message || '批改失败'} /><p className="fine-print">请检查图片清晰度和服务配置，然后重新上传。</p></>}
            {active.result && <><div className="score-overview"><div className="job-score">{active.result.totalScore ?? '待评估'}<small> / {active.result.maxScore} 分</small></div><span>{active.result.questions.length} 道题已分析</span></div><QuestionScores result={active.result} /><button className="text-button" disabled={workingDiagnosis !== null} onClick={() => diagnose(active.gradingId)}>{workingDiagnosis ? '正在生成…' : resultMock ? '查看示例诊断' : '查看诊断报告'}<ArrowRight size={16} /></button><p className="fine-print">右侧助手已关联这次批改，可继续追问失分原因。</p></>}
          </article>
        </>}<ErrorMessage error={diagnosisError} />
      </section>
      {diagnoses.map(diagnosis => <section className="panel diagnosis-panel" key={diagnosis.diagnosisId}><div className="panel-title"><h2>{diagnosis.source === 'mock' ? '示例诊断报告' : '诊断报告'}</h2><span className="tag">{diagnosis.source === 'mock' ? '模拟数据' : 'AI 分析'}</span></div><div className="diagnosis-summary"><div><span className="muted">按考试满分换算的估分</span><div className="report-score"><strong data-testid="estimated-score">{diagnosis.estimatedScore}</strong><span> / {exam.maxScore}</span></div></div><div><strong>优先复习</strong><p>{diagnosis.weakPoints.map(p => p.name).join('、') || '暂无薄弱点记录'}</p></div></div><div className="outline-list">{diagnosis.outline.map(point => <div className="outline-item" key={point.knowledgePointId}><div><strong>{point.knowledgePoint}</strong><span>掌握度尚未评估</span></div><div className="outline-progress"><div className="progress-track"><span style={{width: point.scoreRate + '%'}} /></div><span>得分率 {point.scoreRate}%</span></div></div>)}</div></section>)}
    </div><aside className="study-assistant"><AIPanel key={exam.examId} course={exam.course} examId={exam.examId} gradingId={completed ? active.gradingId : undefined} chatMode={service?.chatMode} /></aside></div>
  </div>
}
