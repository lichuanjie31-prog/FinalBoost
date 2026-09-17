import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, Target } from 'lucide-react'
import { ErrorMessage, EmptyState, MockNotice } from '../../components/Shared'
import { training as trainingApi, type Training } from '../../api/study'

export function Trainings() {
  const [items, setItems] = useState<Training[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    trainingApi.list(controller.signal).then(setItems).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  return <>
    <div className="workspace-title"><div><span className="eyebrow">02 / TRAINING</span><h1>专项训练</h1><p>针对薄弱知识点的五阶段突破。</p></div></div>
    <MockNotice /><ErrorMessage error={error} />
    {loading ? <div className="empty-state" role="status">正在读取专项训练…</div>
      : items.length === 0 ? <EmptyState><Target size={36} /><h2>还没有专项训练</h2><p>先在「我的备考」中上传试卷并生成诊断，再从薄弱知识点开始专项突破。</p><Link className="button button-quiet" to="/app">前往我的备考<ArrowRight size={17} /></Link></EmptyState>
      : <div className="exam-grid">{items.map(item => {
        const completed = item.stages.filter(s => s.status === 'completed').length
        return <Link className="exam-card" key={item.trainingId} to={`/app/trainings/${item.trainingId}`}>
          <div className="card-top"><span className="tag">专项训练</span><span className="muted">{completed} / {item.stages.length} 阶段</span></div>
          <h2>{item.title}</h2>
          <p><BookOpen size={15} />目标掌握度 {item.targetMastery}</p>
          <div className="exam-card-bottom"><span>当前掌握度 <strong>{item.currentMastery ?? '—'}</strong></span><ArrowRight size={19} /></div>
        </Link>
      })}</div>}
  </>
}
