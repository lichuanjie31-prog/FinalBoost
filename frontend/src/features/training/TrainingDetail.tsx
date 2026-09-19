import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Circle, Lock, Target } from 'lucide-react'
import { ErrorMessage, MockNotice } from '../../components/Shared'
import { training as trainingApi, type Training, type StageDetail, type Quiz, type QuizAnswer } from '../../api/study'
import { StageView } from './StageView'
import { QuizView } from './QuizView'
import { ExportPanel } from './ExportPanel'

function statusIcon(status: string) {
  if (status === 'completed') return <CheckCircle2 size={16} />
  if (status === 'unlocked') return <Circle size={16} />
  return <Lock size={14} />
}

export function TrainingDetail() {
  const { id = '' } = useParams()
  const [data, setData] = useState<Training | null>(null)
  const [selected, setSelected] = useState('')
  const [stage, setStage] = useState<StageDetail | null>(null)
  const [loading, setLoading] = useState(true), [stageLoading, setStageLoading] = useState(false)
  const [error, setError] = useState(''), [stageError, setStageError] = useState('')
  const [reload, setReload] = useState(0)
  const [quiz, setQuiz] = useState<Quiz | null>(null), [quizResult, setQuizResult] = useState<QuizAnswer | null>(null)

  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    trainingApi.get(id, controller.signal).then(setData).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id, reload])

  useEffect(() => {
    if (!data) return
    setSelected(current => current || (data.stages.find(s => s.status === 'unlocked')?.type ?? data.stages[data.stages.length - 1].type))
  }, [data])

  useEffect(() => {
    if (!selected) return
    const controller = new AbortController(); setStageLoading(true); setStageError('')
    trainingApi.stage(id, selected, controller.signal).then(setStage).catch(e => { if (!controller.signal.aborted) { setStage(null); setStageError(e.message) } }).finally(() => { if (!controller.signal.aborted) setStageLoading(false) })
    return () => controller.abort()
  }, [id, selected, reload])

  function advance(next: string | null) {
    setReload(v => v + 1)
    if (next) { setStage(null); setSelected(next) }
  }

  if (loading) return <div className="empty-state" role="status">正在读取专项训练…</div>
  if (!data) return <div className="panel"><ErrorMessage error={error} /><Link to="/app" className="text-link">返回我的备考</Link></div>

  const mastery = data.currentMastery ?? 0
  return <>
    <Link className="text-link back-link" to="/app"><ArrowLeft size={16} />我的备考</Link>
    <div className="workspace-title"><div><span className="eyebrow">02 / TRAINING</span><h1>{data.title}</h1><p>目标掌握度 {data.targetMastery} · 五阶段专项突破</p></div>{data.estimatedScoreGain != null && <div className="days-left"><strong>+{data.estimatedScoreGain}</strong><span>预计提分</span></div>}</div>
    <MockNotice /><ErrorMessage error={error} />
    <section className="panel mastery-panel">
      <div className="panel-title"><h2>掌握度</h2><span className="tag">{data.currentMastery == null ? '尚未评估' : `${data.currentMastery}`}</span></div>
      <div className="mastery-track"><span className="mastery-fill" style={{ width: `${Math.min(100, mastery)}%` }} /><span className="mastery-target" style={{ left: `${Math.min(100, data.targetMastery)}%` }} /></div>
      <p className="fine-print">当前掌握度 {data.currentMastery == null ? '尚未评估' : data.currentMastery} · 目标 {data.targetMastery}。完成作答与检测后自动更新。</p>
    </section>
    <nav className="stage-stepper" aria-label="训练阶段">
      {data.stages.map(s => <button key={s.type} className={`stage-step ${s.status} ${selected === s.type ? 'current' : ''}`} disabled={s.status === 'locked'} onClick={() => { setStage(null); setSelected(s.type) }}>{statusIcon(s.status)}<span>{s.title}</span></button>)}
    </nav>
    {stageLoading && !stage ? <div className="empty-state" role="status">正在读取阶段内容…</div>
      : stageError ? <div className="panel"><ErrorMessage error={stageError} /></div>
      : stage ? (stage.type === 'quiz'
        ? <QuizView trainingId={id} stage={stage} quiz={quiz} onQuiz={setQuiz} result={quizResult} onResult={setQuizResult} onChanged={advance} />
        : <StageView trainingId={id} stage={stage} onChanged={advance} />)
      : null}
    <ExportPanel trainingId={id} title={data.title} />
  </>
}
