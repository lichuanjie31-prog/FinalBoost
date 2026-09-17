import { useState } from 'react'
import { ArrowRight, CheckCircle2, XCircle } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { training as trainingApi, type StageDetail, type Attempt, type TrainingQuestion } from '../../api/study'

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
const STAGE_LABEL: Record<string, string> = { method: '题型速记', guided: 'AI 带做', easy: '简单真题', medium: '中等真题', quiz: '掌握度检测' }

export function StageView({ trainingId, stage, onChanged }: { trainingId: string; stage: StageDetail; onChanged: (next: string | null) => void }) {
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, Attempt>>({})
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [completing, setCompleting] = useState(false)

  async function submit(question: TrainingQuestion) {
    const answer = choices[question.questionId]
    if (!answer) { setError('请先选择答案'); return }
    setBusy(question.questionId); setError('')
    try {
      const accepted = await trainingApi.attempt(trainingId, { questionId: question.questionId, answer, durationSeconds: 0 }, crypto.randomUUID())
      let attempt = await trainingApi.getAttempt(trainingId, accepted.attemptId)
      for (let i = 0; i < 40 && (attempt.status === 'queued' || attempt.status === 'running'); i++) { await sleep(400); attempt = await trainingApi.getAttempt(trainingId, accepted.attemptId) }
      setResults(current => ({ ...current, [question.questionId]: attempt }))
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function complete() {
    setCompleting(true); setError('')
    try { const result = await trainingApi.completeStage(trainingId, stage.type); onChanged(result.nextStageType ?? null) }
    catch (e) { setError((e as Error).message) } finally { setCompleting(false) }
  }

  return <section className="panel stage-panel">
    <div className="panel-title"><h2>{STAGE_LABEL[stage.type] ?? stage.type}</h2><span className="tag tag-muted">{stage.questions.length} 题</span></div>
    {stage.content && <p className="stage-content">{stage.content}</p>}
    {stage.questions.length > 0 && <ol className="question-list">{stage.questions.map((question, index) => {
      const result = results[question.questionId]
      const chosen = choices[question.questionId]
      return <li className="question-item" key={question.questionId}>
        <div className="question-head"><span className="question-index">第 {index + 1} 题</span><span className="tag tag-muted">难度 {question.difficulty} · {question.score} 分</span></div>
        <p className="question-stem">{question.content}</p>
        <div className="option-list">{(question.options ?? []).map(option => <label key={option.key} className={`option ${chosen === option.key ? 'selected' : ''}`}><input type="radio" name={question.questionId} value={option.key} checked={chosen === option.key} disabled={!!result} onChange={() => setChoices(current => ({ ...current, [question.questionId]: option.key }))} /><span>{option.key}. {option.text}</span></label>)}</div>
        {!result && <button className="button button-quiet" disabled={busy === question.questionId} onClick={() => submit(question)}>{busy === question.questionId ? '正在判分…' : '提交答案'}<ArrowRight size={16} /></button>}
        {result?.status === 'succeeded' && result.result && <div className={`attempt-result ${result.result.correct ? 'correct' : 'wrong'}`}>{result.result.correct ? <CheckCircle2 size={16} /> : <XCircle size={16} />}<span>{result.result.correct ? '回答正确' : '回答有误'} · 得分 {result.result.score}/{result.result.maxScore}</span><p>{result.result.analysis}</p>{result.result.masteryAfter != null && <small>掌握度 {result.result.masteryBefore ?? '—'} → {result.result.masteryAfter}</small>}</div>}
        {result?.status === 'failed' && <div className="attempt-result wrong"><XCircle size={16} /><span>{result.error?.message || '判分失败'}</span></div>}
      </li>
    })}</ol>}
    <ErrorMessage error={error} />
    <button className="button full-width" disabled={completing} onClick={complete}>{completing ? '正在提交…' : '完成本阶段，进入下一阶段'}<ArrowRight size={17} /></button>
    <p className="fine-print">完成本阶段需要全部题目都已有成功判分的作答。</p>
  </section>
}
