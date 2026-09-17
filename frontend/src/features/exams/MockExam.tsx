import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowRight, BookX, CheckCircle2, ClipboardList, Clock, History, ScanLine, Target, X } from 'lucide-react'
import { ErrorMessage, MockNotice } from '../../components/Shared'
import { study, type Exam, type Grading, type MockExam, type MockHistoryItem, type MockMistakeItem, type MockQuestion, type MockStudentAnswer } from '../../api/study'

// 5 状态进度条（UI 状态机）
//   ready 之前（创建中）→ ready（就绪）→ 作答中（前端本地） → submitted（判卷中） → graded（结果）
type Phase = 'creating' | 'ready' | 'answering' | 'grading' | 'result' | 'graded' | 'failed'
const PHASES: { key: Phase; label: string }[] = [
  { key: 'creating',  label: '列表创建' },
  { key: 'ready',     label: '就绪' },
  { key: 'answering', label: '作答中' },
  { key: 'grading',   label: '判卷中' },
  { key: 'graded',    label: '已完成' },
]
function currentPhaseIndex(
  mock: MockExam | null, isAnswering: boolean, isFailed: boolean, gradingSucceeded: boolean,
): number {
  if (isFailed) return 3
  if (!mock) return 0
  if (mock.status === 'ready') return isAnswering ? 2 : 1
  if (mock.status === 'submitted') return 3
  return 4 // graded
}

export function MockExam() {
  const { id = '' } = useParams()
  const [exam, setExam] = useState<Exam | null>(null)
  const [mock, setMock] = useState<MockExam | null>(null)
  const [grading, setGrading] = useState<Grading | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [phase, setPhase] = useState<Phase>('creating')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  // 判卷历史弹层
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<MockHistoryItem[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  // 错题集弹层
  const [mistakesOpen, setMistakesOpen] = useState(false)
  const [mistakes, setMistakes] = useState<MockMistakeItem[] | null>(null)
  const [mistakesLoading, setMistakesLoading] = useState(false)
  const intent = useRef(crypto.randomUUID())

  useEffect(() => {
    const controller = new AbortController()
    ;(async () => {
      try {
        const e = await study.exam(id, controller.signal)
        if (controller.signal.aborted) return
        setExam(e)

        const m = await study.createMock(id, intent.current, false)
        if (!controller.signal.aborted) {
          setMock(m)
          // 如果已 graded，附带 gradingId 直接拉详情
          if (m.status === 'graded' && m.gradingId) {
            const g = await study.grading(m.gradingId, controller.signal)
            if (!controller.signal.aborted) setGrading(g)
            setPhase('result')
          } else if (m.status === 'submitted') {
            setPhase('grading')
          } else {
            setPhase('ready')
          }
          // 加载作答（如果有）
          const allAnswers: Record<string, string> = {}
          for (const q of m.questions) if (q.studentAnswer) allAnswers[q.questionId] = q.studentAnswer
          setAnswers(allAnswers)
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [id])

  function selectAnswer(questionId: string, answer: string) {
    setAnswers(prev => ({ ...prev, [questionId]: answer }))
    setPhase('answering')
  }

  function jumpToQuestion(questionId: string) {
    const el = document.getElementById(`mock-q-${questionId}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // 把焦点放到第一道题的选项/文本框（让键盘 / 移动端可以直接作答）
    const focusTarget = el.querySelector('textarea, input[type="radio"]') as HTMLElement | null
    focusTarget?.focus({ preventScroll: true })
  }

  async function submitAnswers(event: FormEvent) {
    event.preventDefault()
    if (!mock) return
    setBusy(true); setError('')
    try {
      const payload: MockStudentAnswer[] = Object.entries(answers)
        .filter(([, v]) => (v || '').trim())
        .map(([questionId, answer]) => ({ questionId, answer }))
      if (payload.length !== mock.questions.length) {
        setError('还有题目未作答'); setBusy(false); return
      }
      const result = await study.submitMock(id, mock.mockExamId, payload, crypto.randomUUID())
      setMock(result); setPhase('grading')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  async function startGrading() {
    if (!mock) return
    setBusy(true); setError('')
    try {
      // 每次点击都生成新幂等键：判卷失败后点"重新判卷"能真正重试
      // （幂等键复用会命中缓存，拿到同一个失败的旧任务）
      const accepted = await study.gradeMock(id, mock.mockExamId, crypto.randomUUID())
      const g = await study.grading(accepted.gradingId)
      setGrading(g)
      if (g.status === 'succeeded') {
        const m = await study.getMock(id, mock.mockExamId).catch(() => mock)
        setMock(m)
        setPhase('result')
      } else if (g.status === 'failed') {
        setPhase('failed'); setError(g.error?.message || '判卷失败')
      }
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  async function startNewMock() {
    setBusy(true); setError('')
    try {
      // force=true：无视已判卷的旧卷，开一套新卷
      const m = await study.createMock(id, crypto.randomUUID(), true)
      setMock(m); setGrading(null); setAnswers({}); setPhase('ready')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  async function openHistory() {
    setHistoryOpen(true); setHistoryLoading(true)
    try {
      // 不传 abort signal：弹层开关由 state 控制，拉取结果直接落地
      const items = await study.mockHistory(id)
      setHistory(items)
    } catch { setHistory([]) }
    finally { setHistoryLoading(false) }
  }

  async function openMistakes() {
    setMistakesOpen(true); setMistakesLoading(true)
    try {
      const items = await study.mockMistakes()
      setMistakes(items)
    } catch { setMistakes([]) }
    finally { setMistakesLoading(false) }
  }

  function fmtTime(ts?: number | null) {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  if (loading) return <div className="empty-state" role="status">正在准备最终模拟…</div>
  if (!exam) return <div className="panel"><ErrorMessage error={error} /></div>

  const phaseIdx = currentPhaseIndex(mock, phase === 'answering', phase === 'failed', grading?.status === 'succeeded')
  const allAnswered = !!mock && mock.questions.every(q => (answers[q.questionId] || '').trim())
  const gradedDone = !!mock && (mock.status === 'graded' || grading?.status === 'succeeded')

  // 错题按考试分组
  const mistakesByExam = (mistakes || []).reduce<Record<string, { course: string; items: MockMistakeItem[] }>>((acc, m) => {
    if (!acc[m.examId]) acc[m.examId] = { course: m.course, items: [] }
    acc[m.examId].items.push(m)
    return acc
  }, {})
  const mistakeExamIds = Object.keys(mistakesByExam)

  return <>
    <div className="workspace-title">
      <div>
        <span className="eyebrow">03 / MOCK EXAM</span>
        <h1>最终模拟 · {exam.course}</h1>
        <p>从内置题库抽题，限时作答后立即判卷，得出接近真实考试的估分。</p>
      </div>
      <div className="days-left"><strong>{exam.remainingDays}</strong><span>天后考试</span></div>
    </div>
    <MockNotice />
    <ErrorMessage error={error} />

    {/* 5 状态进度条 */}
    <ol className="phase-track" aria-label="最终模拟状态进度">
      {PHASES.map((p, i) => {
        const reached = phaseIdx >= i
        const current = phaseIdx === i
        return <li key={p.key} className={`phase ${reached ? 'is-reached' : ''} ${current ? 'is-current' : ''}`}><span className="phase-dot" />{p.label}</li>
      })}
    </ol>

    {phase === 'failed' ? (
      <div className="panel"><h2>判卷未完成</h2><p>请重新点击下方按钮重试。</p><button className="button" onClick={startGrading} disabled={busy}>重新判卷<ArrowRight size={17} /></button></div>
    ) : !mock ? (
      <div className="empty-state" role="status"><ScanLine size={32} /><p>正在准备最终模拟卷…</p></div>
    ) : (
      <div className="detail-grid">
        {/* 左：题目列表 */}
        <section className="panel mock-questions-panel">
          <div className="panel-title">
            <h2>试卷</h2>
            <span className="tag">{mock.questions.length} 题 / {mock.maxScore} 分</span>
          </div>
          {mock.status === 'ready' ? (
            <form onSubmit={submitAnswers} className="form-stack">
              {mock.questions.map((q, idx) => {
                const answered = !!(answers[q.questionId] || '').trim()
                return <fieldset key={q.questionId} id={`mock-q-${q.questionId}`} className={`mock-question ${answered ? 'is-answered' : ''}`}>
                    <legend className="mock-question-legend">
                      <strong>第 {idx + 1} 题</strong>
                      <span className="muted">{q.knowledgePoints.join('、')} · {q.maxScore} 分</span>
                      {answered && <span className="mock-question-flag">已作答</span>}
                    </legend>
                    <div className="mock-question-body">
                      <p className="mock-prompt">{q.prompt}</p>
                      {q.options?.length ? (
                        <div className="mock-options">
                          {q.options.map(opt => {
                            const checked = answers[q.questionId] === opt.label
                            return <label key={opt.label} className={`mock-option ${checked ? 'is-checked' : ''}`}>
                              <input type="radio" name={q.questionId} value={opt.label} checked={checked} onChange={() => selectAnswer(q.questionId, opt.label)} />
                              <span className="opt-label">{opt.label}</span><span>{opt.text}</span>
                            </label>
                          })}
                        </div>
                      ) : (
                        <textarea rows={3} value={answers[q.questionId] || ''} onChange={e => selectAnswer(q.questionId, e.target.value)} placeholder="在此作答" />
                      )}
                    </div>
                  </fieldset>
              })}
              <div className="form-row">
                <span className="muted">{allAnswered ? '已作答全部题目' : `还有 ${mock.questions.filter(q => !(answers[q.questionId] || '').trim()).length} 题未作答`}</span>
                <button type="submit" className="button" disabled={busy || !allAnswered}>{busy ? '正在提交…' : '提交作答'}<ArrowRight size={17} /></button>
              </div>
            </form>
          ) : (
            <ol className="mock-readonly-list">
              {mock.questions.map((q, idx) => {
                const answered = !!(answers[q.questionId] || '').trim()
                return <li key={q.questionId} id={`mock-q-${q.questionId}`} className={`mock-readonly-item ${answered ? 'is-answered' : ''}`}>
                    <div className="mock-question-legend">
                      <strong>第 {idx + 1} 题 · {q.maxScore} 分</strong>
                      <span className="muted">{q.knowledgePoints.join('、')}</span>
                      {answered && <span className="mock-question-flag">已作答</span>}
                    </div>
                    <div className="mock-question-body">
                      <p className="mock-prompt">{q.prompt}</p>
                      {q.options?.length && <ul className="mock-options readonly">{q.options.map(o => <li key={o.label} className={answers[q.questionId] === o.label ? 'is-checked' : ''}>{o.label}. {o.text}</li>)}</ul>}
                      {!q.options?.length && <p className="mock-text-answer">作答：{answers[q.questionId] || <em className="muted">（空白）</em>}</p>}
                    </div>
                  </li>
              })}
            </ol>
          )}
        </section>

        {/* 右：进度 / 操作 */}
        <section className="panel mock-side-panel">
          <div className="panel-title"><h2>当前进度</h2></div>
          {mock.status === 'ready' && (
            <div className="status-block">
              <Clock size={26} /><p>试卷已生成，请尽快作答并提交。</p>
              <small className="fine-print">系统从内置示例题库抽题，与正式题库解耦；后续接入真题库时无需改动本页面。</small>
            </div>
          )}
          {mock.status === 'ready' && (
            <div className="answer-card">
              <div className="answer-card-head">
                <h3>答题卡</h3>
                <span className="muted">
                  {mock.questions.filter(q => (answers[q.questionId] || '').trim()).length} / {mock.questions.length} 已作答
                </span>
              </div>
              <div className="answer-card-grid" role="list">
                {mock.questions.map((q, idx) => {
                  const isAnswered = !!(answers[q.questionId] || '').trim()
                  return <button
                    key={q.questionId}
                    type="button"
                    role="listitem"
                    className={`answer-cell ${isAnswered ? 'is-answered' : 'is-empty'}`}
                    onClick={() => jumpToQuestion(q.questionId)}
                    aria-label={`第 ${idx + 1} 题，${isAnswered ? '已作答' : '未作答'}，点击跳转`}
                  >{idx + 1}</button>
                })}
              </div>
              <small className="fine-print">点击题号可跳转到对应题目。</small>
            </div>
          )}
          {mock.status === 'submitted' && !gradedDone && (
            <div className="status-block">
              <ClipboardList size={26} /><p>作答已提交，正在等待判卷。</p>
              {grading && grading.status !== 'failed'
                ? <p className="job-status-badge">判卷任务状态：{grading.status === 'running' ? '判卷中' : grading.status === 'succeeded' ? '已完成' : '排队中'}</p>
                : <button className="button" onClick={startGrading} disabled={busy}>{busy ? '正在触发…' : grading?.status === 'failed' ? '重新判卷' : '开始判卷'}<ArrowRight size={17} /></button>}
              {/* 已有判卷任务在跑时不再显示按钮，避免重复判卷被 409 拒绝 */}
              {grading && (grading.status === 'queued' || grading.status === 'running') && <small className="fine-print">判卷进行中，通常 1~2 秒完成，请稍候…</small>}
            </div>
          )}
          {gradedDone && grading?.result && (
            <div className="status-block">
              <CheckCircle2 size={26} /><p>判卷完成，下面是逐题得分。</p>
              <div className="job-score">{grading.result.totalScore ?? '待评估'}<small> / {grading.result.maxScore} 分</small></div>
              <button className="button" onClick={startNewMock} disabled={busy}>{busy ? '正在开新卷…' : '再来一套'}<ArrowRight size={17} /></button>
            </div>
          )}
          {gradedDone && !grading?.result && (
            <div className="status-block"><Clock size={26} /><p>已判卷，但结果未加载。</p></div>
          )}
          <button type="button" className="text-button mock-side-link" onClick={openHistory}>
            <History size={15} />判卷历史
          </button>
          <button type="button" className="text-button mock-side-link" onClick={openMistakes}>
            <BookX size={15} />错题集
          </button>
          <div className="side-meta"><Target size={15} />目标 {exam.targetScore} / {exam.maxScore}</div>
        </section>
      </div>
    )}

    {/* 判卷历史弹层：本场考试全部最终模拟记录 */}
    {historyOpen && (
      <div className="mock-history-overlay" role="dialog" aria-modal="true" aria-label="判卷历史" onClick={() => setHistoryOpen(false)}>
        <div className="mock-history-modal" onClick={e => e.stopPropagation()}>
          <div className="mock-history-head">
            <h2><History size={18} />判卷历史</h2>
            <button type="button" className="icon-button" aria-label="关闭" onClick={() => setHistoryOpen(false)}><X size={18} /></button>
          </div>
          {historyLoading ? (
            <div className="empty-state" role="status">正在加载判卷历史…</div>
          ) : !history || history.length === 0 ? (
            <div className="empty-state"><ClipboardList size={28} /><p>还没有模拟记录，做完一套就会出现这里。</p></div>
          ) : (
            <ol className="mock-history-list">
              {history.map((item, idx) => {
                const n = history.length - idx // 从旧到新编号 → 第 N 次
                const passed = item.totalScore !== null && exam && item.totalScore >= exam.targetScore
                return <li key={item.mockExamId} className={`mock-history-item ${item.status === 'graded' ? 'is-graded' : ''}`}>
                  <span className="mock-history-no">第 {n} 次</span>
                  {item.status === 'graded' ? (
                    <strong className="mock-history-score">{item.totalScore ?? '—'}<small> / {item.maxScore}</small></strong>
                  ) : (
                    <span className="mock-history-unfinished">{item.status === 'submitted' ? '判卷中' : '未完成'}</span>
                  )}
                  {item.status === 'graded' && exam && (
                    <span className={`mock-history-flag ${passed ? 'is-pass' : 'is-gap'}`}>
                      {passed ? `达标（目标 ${exam.targetScore}）` : `距目标 ${Math.max(0, exam.targetScore - (item.totalScore ?? 0))} 分`}
                    </span>
                  )}
                  <span className="mock-history-time">{fmtTime(item.gradedAt || item.submittedAt || item.createdAt)}</span>
                </li>
              })}
            </ol>
          )}
        </div>
      </div>
    )}

    {/* 错题集弹层：用户全部已判卷错题，按考试分组 */}
    {mistakesOpen && (
      <div className="mock-mistakes-overlay" role="dialog" aria-modal="true" aria-label="错题集" onClick={() => setMistakesOpen(false)}>
        <div className="mock-mistakes-modal" onClick={e => e.stopPropagation()}>
          <div className="mock-mistakes-head">
            <h2><BookX size={18} />错题集</h2>
            <button type="button" className="icon-button" aria-label="关闭" onClick={() => setMistakesOpen(false)}><X size={18} /></button>
          </div>
          {mistakesLoading ? (
            <div className="empty-state" role="status">正在加载错题…</div>
          ) : !mistakes || mistakes.length === 0 ? (
            <div className="empty-state"><CheckCircle2 size={28} /><p>还没有错题，做完一套模拟卷之后再来看看吧。</p></div>
          ) : (
            <div className="mock-mistakes-groups">
              <div className="mock-mistakes-summary">
                共 <strong>{mistakes.length}</strong> 道错题，覆盖 <strong>{mistakeExamIds.length}</strong> 场考试。
              </div>
              {mistakeExamIds.map(eid => {
                const g = mistakesByExam[eid]
                return <section key={eid} className="mock-mistakes-group">
                  <header className="mock-mistakes-group-head">
                    <h3>{g.course}</h3>
                    <span className="tag">{g.items.length} 道</span>
                  </header>
                  <ol className="mock-mistakes-list">
                    {g.items.map((m, i) => (
                      <li key={`${m.mockExamId}-${m.questionId}-${i}`} className="mock-mistake-item">
                        <div className="mock-mistake-head">
                          <span className="mock-mistake-score">{m.score}<small> / {m.maxScore}</small></span>
                          {m.knowledgePoints.length > 0 && (
                            <span className="mock-mistake-kp">{m.knowledgePoints.join(' · ')}</span>
                          )}
                          <span className="mock-mistake-time">{fmtTime(m.gradedAt)}</span>
                        </div>
                        <p className="mock-mistake-prompt">{m.prompt}</p>
                        <div className="mock-mistake-answers">
                          <div className="mock-mistake-answer is-wrong">
                            <span className="mock-mistake-label">你的作答</span>
                            <span className="mock-mistake-text">{m.userAnswer || <em className="muted">（空白）</em>}</span>
                          </div>
                          <div className="mock-mistake-answer is-correct">
                            <span className="mock-mistake-label">正确答案</span>
                            <span className="mock-mistake-text">{m.correctAnswer || <em className="muted">（无）</em>}</span>
                          </div>
                        </div>
                        {m.errorReason && <p className="mock-mistake-reason">提示：{m.errorReason}</p>}
                      </li>
                    ))}
                  </ol>
                </section>
              })}
            </div>
          )}
        </div>
      </div>
    )}
  </>
}