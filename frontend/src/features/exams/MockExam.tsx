import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, ClipboardList, Clock, ScanLine, Target } from 'lucide-react'
import { ErrorMessage, MockNotice } from '../../components/Shared'
import { study, type Exam, type Grading, type MockExam, type MockQuestion } from '../../api/study'
import { QuestionScores } from './QuestionScores'

// 5 状态进度条（UI 状态机）
//   ready 之前（创建中）→ ready（就绪）→ 作答中（前端本地） → submitted（判卷中） → graded（结果）
type Phase = 'creating' | 'ready' | 'answering' | 'grading' | 'result' | 'failed'
const PHASES: { key: Phase; label: string }[] = [
  { key: 'creating',  label: '列表创建' },
  { key: 'ready',     label: '就绪' },
  { key: 'answering', label: '作答中' },
  { key: 'grading',   label: '判卷中' },
  { key: 'result',    label: '结果' },
]

function currentPhaseIndex(mock: MockExam | null, working: boolean, failed: boolean, done: boolean): number {
  if (failed) return -1
  if (mock === null) return 0 // 还在创建
  if (done) return 4 // 判卷任务已 succeeded（即使 mock 状态还没刷新过来）
  if (mock.status === 'ready') return working ? 2 : 1
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
  // 试卷折叠状态：作答中默认全部收起；判卷完成后默认展开便于复盘
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const intent = useRef(crypto.randomUUID())
  const answersRef = useRef(answers); answersRef.current = answers

  // 初始加载：先拉考试 + 创建/复用 mock_exam
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    ;(async () => {
      try {
        const e = await study.exam(id, controller.signal); setExam(e)
        // 创建 mock（幂等）
        const m = await study.createMock(id, intent.current)
        if (!controller.signal.aborted) {
          setMock(m)
          // 如果已 graded，附带 gradingId 直接拉详情
          if (m.status === 'graded' && m.gradingId) {
            const g = await study.grading(m.gradingId, controller.signal)
            if (!controller.signal.aborted) setGrading(g)
            setPhase('result')
            // 复盘场景：默认展开所有题目
            setExpanded(new Set(m.questions.map(q => q.questionId)))
          } else if (m.status === 'submitted') {
            setPhase('grading')
          } else {
            setPhase('ready')
            // 作答场景：默认全部收起
            setExpanded(new Set())
          }
          // 回填学生已作答的答案
          const existing: Record<string, string> = {}
          for (const q of m.questions) if (q.studentAnswer !== undefined) existing[q.questionId] = q.studentAnswer
          setAnswers(existing)
        }
      } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    })()
    return () => controller.abort()
  }, [id])

  // 轮询 grading job
  useEffect(() => {
    if (!grading || (grading.status !== 'queued' && grading.status !== 'running')) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    timer = setTimeout(async function poll() {
      try {
        const g = await study.grading(grading.gradingId, controller.signal)
        if (!controller.signal.aborted) {
          setGrading(g)
          if (g.status === 'succeeded') {
            // 注意：这里不能传 controller.signal——setGrading 会让本 effect 重跑，
            // cleanup 会 abort 这个 controller，把紧接着的这次拉取自己取消掉（竞态）
            const m = mock ? await study.getMock(id, mock.mockExamId).catch(() => null) : null
            if (m) setMock(m)
            setPhase('result')
            return
          }
          if (g.status === 'failed') { setPhase('failed'); setError(g.error?.message || '判卷失败'); return }
        }
      } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
      if (!controller.signal.aborted) timer = setTimeout(poll, 1500)
    }, 1500)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [grading, id, mock])

  function selectAnswer(questionId: string, value: string) {
    if (mock?.status !== 'ready') return
    setPhase('answering')
    setAnswers(old => ({ ...old, [questionId]: value }))
  }

  function jumpToQuestion(questionId: string) {
    const el = document.getElementById(`mock-q-${questionId}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // 把焦点放到第一道题的选项/文本框（让键盘 / 移动端可以直接作答）
    const focusTarget = el.querySelector('textarea, input[type="radio"]') as HTMLElement | null
    focusTarget?.focus({ preventScroll: true })
  }

  function toggleExpanded(questionId: string) {
    setExpanded(old => {
      const next = new Set(old)
      if (next.has(questionId)) next.delete(questionId)
      else next.add(questionId)
      return next
    })
  }

  async function submitAnswers(event: FormEvent) {
    event.preventDefault()
    if (!mock) return
    setBusy(true); setError('')
    try {
      const payload = mock.questions.map(q => ({ questionId: q.questionId, answer: answers[q.questionId] || '' }))
      const unanswered = payload.filter(a => !a.answer.trim()).length
      if (unanswered > 0) {
        setError(`还有 ${unanswered} 道题未作答，请补齐后提交`)
        setBusy(false); return
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

  if (loading) return <div className="empty-state" role="status">正在准备最终模拟…</div>
  if (!exam) return <div className="panel"><ErrorMessage error={error} /><Link className="text-link" to="/app">返回我的备考</Link></div>

  const phaseIdx = currentPhaseIndex(mock, phase === 'answering', phase === 'failed', grading?.status === 'succeeded')
  const allAnswered = !!mock && mock.questions.every(q => (answers[q.questionId] || '').trim())
  const gradedDone = !!mock && (mock.status === 'graded' || grading?.status === 'succeeded')

  return <>
    <Link className="text-link back-link" to="/app"><ArrowLeft size={16} />我的备考</Link>
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
            <div className="panel-title-actions">
              <span className="tag">{mock.questions.length} 题 / {mock.maxScore} 分</span>
              <button type="button" className="text-button" onClick={() => setExpanded(new Set(mock.questions.map(q => q.questionId)))}>全部展开</button>
              <button type="button" className="text-button" onClick={() => setExpanded(new Set())}>全部收起</button>
            </div>
          </div>
          {mock.status === 'ready' ? (
            <form onSubmit={submitAnswers} className="form-stack">
              {mock.questions.map((q, idx) => {
                const isOpen = expanded.has(q.questionId)
                const answered = !!(answers[q.questionId] || '').trim()
                return <fieldset key={q.questionId} id={`mock-q-${q.questionId}`} className={`mock-question ${isOpen ? 'is-open' : 'is-collapsed'} ${answered ? 'is-answered' : ''}`}>
                    <button
                      type="button"
                      className="mock-question-toggle"
                      aria-expanded={isOpen}
                      aria-controls={`mock-q-body-${q.questionId}`}
                      onClick={() => toggleExpanded(q.questionId)}
                    >
                      <ChevronDown size={16} className={`mock-question-chevron ${isOpen ? 'is-rotated' : ''}`} />
                      <strong>第 {idx + 1} 题</strong>
                      <span className="muted">{q.knowledgePoints.join('、')} · {q.maxScore} 分</span>
                      {answered && <span className="mock-question-flag">已作答</span>}
                    </button>
                    {isOpen && <div id={`mock-q-body-${q.questionId}`} className="mock-question-body">
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
                    </div>}
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
                const isOpen = expanded.has(q.questionId)
                const answered = !!(answers[q.questionId] || '').trim()
                return <li key={q.questionId} id={`mock-q-${q.questionId}`} className={`mock-readonly-item ${isOpen ? 'is-open' : 'is-collapsed'} ${answered ? 'is-answered' : ''}`}>
                    <button type="button" className="mock-question-toggle" aria-expanded={isOpen} aria-controls={`mock-q-body-${q.questionId}`} onClick={() => toggleExpanded(q.questionId)}>
                      <ChevronDown size={16} className={`mock-question-chevron ${isOpen ? 'is-rotated' : ''}`} />
                      <strong>第 {idx + 1} 题 · {q.maxScore} 分</strong>
                      <span className="muted">{q.knowledgePoints.join('、')}</span>
                      {answered && <span className="mock-question-flag">已作答</span>}
                    </button>
                    {isOpen && <div id={`mock-q-body-${q.questionId}`} className="mock-question-body">
                      <p className="mock-prompt">{q.prompt}</p>
                      {q.options?.length && <ul className="mock-options readonly">{q.options.map(o => <li key={o.label} className={answers[q.questionId] === o.label ? 'is-checked' : ''}>{o.label}. {o.text}</li>)}</ul>}
                      {!q.options?.length && <p className="mock-text-answer">作答：{answers[q.questionId] || <em className="muted">（空白）</em>}</p>}
                    </div>}
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
            <div className="status-block" id="mock-result-block">
              <CheckCircle2 size={26} /><p>判卷完成，下面是逐题得分。</p>
              <div className="job-score">{grading.result.totalScore ?? '待评估'}<small> / {grading.result.maxScore} 分</small></div>
              <QuestionScores result={grading.result} />
              <button className="button" onClick={startNewMock} disabled={busy}>{busy ? '正在开新卷…' : '再来一套'}<ArrowRight size={17} /></button>
            </div>
          )}
          {gradedDone && !grading?.result && (
            <div className="status-block"><Clock size={26} /><p>已判卷，但结果未加载。</p></div>
          )}
          <div className="side-meta"><Target size={15} />目标 {exam.targetScore} / {exam.maxScore}</div>
        </section>
      </div>
    )}

    {/* 悬浮"查看成绩"药丸：判卷完成后从屏幕底部浮起，
        答完最后一道题滚到底部时不用再爬回去看结果。 */}
    {gradedDone && grading?.result && (
      <button
        type="button"
        className="mock-result-pill"
        onClick={() => {
          const target = document.getElementById('mock-result-block')
          target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          // 再给结果块一个轻微脉冲，强调"到了"
          target?.classList.add('is-flashing')
          setTimeout(() => target?.classList.remove('is-flashing'), 1200)
        }}
        aria-label="查看本次成绩"
      >
        <CheckCircle2 size={18} />
        <span className="mock-result-pill-label">本次成绩</span>
        <strong className="mock-result-pill-score">
          {grading.result.totalScore ?? '—'}<small> / {grading.result.maxScore}</small>
        </strong>
      </button>
    )}
  </>
}