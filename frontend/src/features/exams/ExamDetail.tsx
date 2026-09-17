import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Upload, FileImage, RefreshCw, CheckCircle2, Clock, X, Target } from 'lucide-react'
import { ErrorMessage, MockNotice } from '../../components/Shared'
import { study, training as trainingApi, type Exam, type Grading, type Diagnosis } from '../../api/study'
import { QuestionScores } from './QuestionScores'

type LocalFile = { file:File; key:string; uploadedId?:string }
export function ExamDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [exam, setExam] = useState<Exam | null>(null), [jobs, setJobs] = useState<Grading[]>([]), [diagnoses, setDiagnoses] = useState<Diagnosis[]>([])
  const [files, setFiles] = useState<LocalFile[]>([]), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const [error, setError] = useState(''), [uploadError, setUploadError] = useState(''), [diagnosisError, setDiagnosisError] = useState(''), [workingDiagnosis, setWorkingDiagnosis] = useState<string | null>(null)
  const [startingTraining, setStartingTraining] = useState(''), [trainingError, setTrainingError] = useState('')
  const [reload, setReload] = useState(0), [progress, setProgress] = useState('')
  const uploadIntent = useRef(crypto.randomUUID()), fileInput = useRef<HTMLInputElement>(null)
  const jobsRef = useRef(jobs); jobsRef.current = jobs
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    Promise.all([study.exam(id,controller.signal), study.gradings(id,controller.signal), study.diagnoses(id,controller.signal)]).then(([e,j,d]) => { setExam(e); setJobs(j); setDiagnoses(d) }).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
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
    if (!selected) return
    const candidates = Array.from(selected)
    if (candidates.length + files.length > 10) { setUploadError('一次最多上传 10 张答题图片'); return }
    if (candidates.some(f => !['image/jpeg','image/png','image/webp'].includes(f.type) || f.size > 10*1024*1024)) { setUploadError('请选择 JPEG、PNG 或 WebP 图片，每张不超过 10 MiB'); return }
    setFiles(old => [...old,...candidates.map(file => ({ file,key:crypto.randomUUID() }))]); setUploadError(''); uploadIntent.current = crypto.randomUUID()
    if (fileInput.current) fileInput.current.value = ''
  }
  async function submit() {
    setBusy(true); setUploadError('')
    try {
      const current = [...files]
      for (let i=0;i<current.length;i++) {
        setProgress(`正在上传第 ${i+1} / ${current.length} 张图片`)
        if (!current[i].uploadedId) { const uploaded = await study.upload(current[i].file,current[i].key); current[i] = { ...current[i], uploadedId:uploaded.fileId }; setFiles([...current]) }
      }
      setProgress('正在创建模拟判卷任务')
      const accepted = await study.grade(id,current.map(f => f.uploadedId!),uploadIntent.current)
      const job = await study.grading(accepted.gradingId)
      setJobs(old => [...old.filter(j => j.gradingId !== job.gradingId),job]); setFiles([]); uploadIntent.current = crypto.randomUUID()
    } catch (e) { setUploadError((e as Error).message) } finally { setBusy(false); setProgress('') }
  }
  async function diagnose(gid: string) {
    setWorkingDiagnosis(gid); setDiagnosisError('')
    try { const result = await study.diagnose(id,gid); setDiagnoses(old => [result,...old.filter(d => d.diagnosisId !== result.diagnosisId)]) }
    catch (e) { setDiagnosisError((e as Error).message) } finally { setWorkingDiagnosis(null) }
  }
  async function startTraining(knowledgePointId: string) {
    setStartingTraining(knowledgePointId); setTrainingError('')
    try { const result = await trainingApi.create({ examId:id, knowledgePointId, targetMastery:80 }, crypto.randomUUID()); navigate(`/app/trainings/${result.trainingId}`) }
    catch (e) { setTrainingError((e as Error).message) } finally { setStartingTraining('') }
  }
  if (loading) return <div className="empty-state" role="status">正在读取考试记录…</div>
  if (!exam) return <div className="panel"><ErrorMessage error={error} /><button className="button button-quiet" onClick={() => setReload(v=>v+1)}>重新加载</button><Link to="/app" className="text-link">返回我的备考</Link></div>
  return <><Link className="text-link back-link" to="/app"><ArrowLeft size={16} />我的备考</Link><div className="workspace-title"><div><span className="eyebrow">01 / DIAGNOSE</span><h1>{exam.course}</h1><p>考试日期 {exam.examDate} · 目标 {exam.targetScore} / {exam.maxScore} 分</p></div><div className="days-left"><strong>{exam.remainingDays}</strong><span>天后考试</span></div></div><MockNotice /><ErrorMessage error={error} />
    <div className="detail-grid"><section className="panel upload-panel"><div className="panel-title"><h2>上传答题照片</h2><span className="tag">摸底诊断</span></div><p className="muted">按页码顺序选择图片，保存这次诊断的材料。</p><label className={`upload-zone ${busy ? 'is-disabled' : ''}`}><Upload size={28} /><strong>选择答题图片</strong><span>JPEG、PNG、WebP · 每张最多 10 MiB</span><small>最多 10 张，当前已选 {files.length} 张</small><input ref={fileInput} type="file" aria-label="选择答题图片" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={e => choose(e.target.files)} /></label>
      {files.length > 0 && <ol className="file-list">{files.map((entry,index) => <li key={entry.key}><FileImage size={16} /><span>{index+1}. {entry.file.name}</span>{entry.uploadedId && <CheckCircle2 size={15} />}<button className="icon-button" disabled={busy} aria-label={`移除 ${entry.file.name}`} onClick={() => { setFiles(old=>old.filter(f=>f.key!==entry.key)); uploadIntent.current=crypto.randomUUID() }}><X size={16} /></button></li>)}</ol>}
      <ErrorMessage error={uploadError} />{progress && <p role="status" className="progress-message">{progress}</p>}<button className="button full-width" disabled={busy || !files.length} onClick={submit}>{busy ? '正在提交…' : '上传并开始模拟判卷'}<ArrowRight size={17} /></button><p className="fine-print">当前返回固定示例评分，不识别图片中的答案。请使用测试图片体验流程。</p>
    </section><section className="panel jobs-panel"><div className="panel-title"><h2>判卷记录</h2><span className="tag tag-muted">{jobs.length} 次</span></div>{jobs.length === 0 ? <div className="empty-state"><Clock size={26} /><p>上传图片后，判卷进度会显示在这里。</p></div> : <div className="job-list">{[...jobs].reverse().map((job,index) => <article className="job-item" key={job.gradingId}><div className="job-title"><strong>试卷记录 {jobs.length-index}</strong><span className={`job-status ${job.status}`}>{job.status==='succeeded' ? '判卷完成' : job.status==='failed' ? '判卷失败' : job.status==='running' ? '正在判卷' : '排队中'}</span></div>{(job.status==='queued' || job.status==='running') && <p role="status"><RefreshCw size={14} />{job.status==='queued' ? '任务已排队，正在等待模拟判卷' : '正在进行模拟判卷，可安全刷新页面'}</p>}{job.status==='failed' && <div><ErrorMessage error={job.error?.message || '判卷未完成'} /><p className="fine-print">重新选择图片并提交，可创建新的判卷任务。</p></div>}{job.result && <><div className="job-score">{job.result.totalScore ?? '待评估'}<small> / {job.result.maxScore} 分</small></div><QuestionScores result={job.result} /><button className="text-button" disabled={workingDiagnosis!==null} onClick={()=>diagnose(job.gradingId)}>{workingDiagnosis===job.gradingId ? '正在生成…' : '查看示例诊断'}<ArrowRight size={15} /></button></>}</article>)}</div>}<ErrorMessage error={diagnosisError} /></section></div>
    {diagnoses.map((diagnosis,index) => <section className="panel diagnosis-panel" key={diagnosis.diagnosisId}><div className="panel-title"><div><span className="eyebrow">REPORT / {String(index+1).padStart(2,'0')}</span><h2>示例诊断报告</h2></div><span className="tag">模拟数据</span></div><div className="diagnosis-summary"><div><span className="muted">按本次考试满分换算的估分</span><div className="report-score"><strong data-testid="estimated-score">{diagnosis.estimatedScore}</strong><span> / {exam.maxScore}</span></div></div><div><strong>建议回看的知识点</strong>{diagnosis.weakPoints.length === 0 ? <p>暂无薄弱点记录</p> : <ul className="weak-point-list">{diagnosis.weakPoints.map(p => <li key={p.knowledgePointId}><span>{p.name}</span><button className="text-button" disabled={startingTraining !== ''} onClick={() => startTraining(p.knowledgePointId)}>{startingTraining === p.knowledgePointId ? '正在创建…' : '开始专项训练'}<Target size={14} /></button></li>)}</ul>}<small>仅基于固定示例评分生成</small></div></div><div className="outline-list">{diagnosis.outline.map(point=><div className="outline-item" key={point.knowledgePointId}><div><strong>{point.knowledgePoint}</strong><span>掌握度尚未评估</span></div><div className="outline-progress"><div className="progress-track"><span className="fill-blue" style={{width:`${point.scoreRate}%`}} /></div><span>得分率 {point.scoreRate}%</span></div></div>)}</div><p className="fine-print">当前尚未建立真实知识画像；示例得分率与知识点掌握度分别展示。</p><ErrorMessage error={trainingError} /></section>)}
  </>
}
