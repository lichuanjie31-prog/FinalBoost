import { useState } from 'react'
import { ArrowRight, CheckCircle2, XCircle } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { training as trainingApi, type StageDetail, type Quiz, type QuizAnswer } from '../../api/study'

export function QuizView({ trainingId, stage, quiz, onQuiz, result, onResult, onChanged }: {
  trainingId: string
  stage: StageDetail
  quiz: Quiz | null
  onQuiz: (quiz: Quiz) => void
  result: QuizAnswer | null
  onResult: (result: QuizAnswer) => void
  onChanged: (next: string | null) => void
}) {
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')

  async function generate() {
    setBusy(true); setError('')
    try { onQuiz(await trainingApi.createQuiz(trainingId)) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function submit() {
    if (!quiz || !answer.trim()) { setError('请先作答'); return }
    setBusy(true); setError('')
    try { const scored = await trainingApi.answerQuiz(trainingId, { quizId: quiz.quizId, answer }); onResult(scored); onChanged(null) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <section className="panel stage-panel">
    <div className="panel-title"><h2>掌握度检测</h2><span className="tag">AI 检测</span></div>
    {result && <div className={`attempt-result ${result.passed ? 'correct' : 'wrong'}`}>
      {result.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      <span>检测得分 {result.score} · {result.conceptCorrect ? '概念正确' : '概念需要加强'}</span>
      {result.missingPoints.length > 0 && <p>待补充：{result.missingPoints.join('；')}</p>}
      <small>当前掌握度 {result.masteryAfter ?? '—'} · {result.passed ? '已达标' : '未达标，可继续练习后再检测'}</small>
    </div>}
    {!result && stage.status === 'completed' && <p className="stage-content">本训练的检测已完成。可查看上方掌握度确认是否达到目标。</p>}
    {!result && !quiz && stage.status !== 'completed' && <>
      <p className="stage-content">用自己的话作答，系统会评估概念理解程度，并据此更新掌握度。</p>
      <button className="button full-width" disabled={busy} onClick={generate}>{busy ? '正在生成检测题…' : '生成检测题'}<ArrowRight size={17} /></button>
    </>}
    {!result && quiz && <>
      <p className="question-stem">{quiz.question}</p>
      <textarea className="quiz-input" rows={5} maxLength={10000} value={answer} disabled={busy} placeholder="写下你的理解…" onChange={e => setAnswer(e.target.value)} />
      <button className="button full-width" disabled={busy} onClick={submit}>{busy ? '正在评估…' : '提交检测答案'}<ArrowRight size={17} /></button>
    </>}
    <ErrorMessage error={error} />
  </section>
}
