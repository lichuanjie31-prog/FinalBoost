import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CalendarDays, ScanLine, Target } from 'lucide-react'
import { ErrorMessage, EmptyState, MockNotice } from '../../components/Shared'
import { study, type Exam, type MockExam } from '../../api/study'

type Row = { exam: Exam; mock: MockExam | null; lastScore: number | null }

const STATUS_LABEL: Record<MockExam['status'] | 'none', string> = {
  none: '未开始',
  ready: '可作答',
  submitted: '判卷中',
  graded: '已判卷',
}

const STATUS_HINT: Record<MockExam['status'] | 'none', string> = {
  none: '尚未生成模拟卷',
  ready: '卷子已生成，可作答',
  submitted: '作答已提交，正在判卷',
  graded: '上次已有成绩，可再来一套',
}

const CTA_LABEL: Record<MockExam['status'] | 'none', string> = {
  none: '开始第一套',
  ready: '继续作答',
  submitted: '查看进度',
  graded: '查看 / 再来一套',
}

export function MockHub() {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    ;(async () => {
      try {
        const exams = await study.exams(controller.signal)
        if (controller.signal.aborted) return
        // 复用 createMock（幂等）：对每份考试拿到最新 mock，没有则视为 null
        const results = await Promise.all(exams.map(async exam => {
          try {
            const mock = await study.createMock(exam.examId, crypto.randomUUID())
            // 已判卷的 mock 顺手把分数也拉回来，板块页卡片直接展示
            let lastScore: number | null = null
            if (mock.status === 'graded' && mock.gradingId) {
              const g = await study.grading(mock.gradingId).catch(() => null)
              lastScore = g?.result?.totalScore ?? null
            }
            return { exam, mock, lastScore }
          } catch {
            return { exam, mock: null, lastScore: null }
          }
        }))
        if (controller.signal.aborted) return
        setRows(results)
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [])

  return <>
    <div className="workspace-title">
      <div>
        <span className="eyebrow">03 / MOCK EXAM</span>
        <h1>最终模拟</h1>
        <p>每一份考试都能独立开一套模拟卷，作答后立即自动判卷，给出接近真实考试的总分。</p>
      </div>
    </div>
    <MockNotice />
    <ErrorMessage error={error} />
    {loading ? (
      <div className="empty-state" role="status">正在汇总各考试进度…</div>
    ) : rows.length === 0 ? (
      <EmptyState>
        <ScanLine size={36} />
        <h2>还没有考试</h2>
        <p>先去「我的备考」新建一份，再回到这里开始最终模拟。</p>
        <Link className="button" to="/app">去新建备考计划<ArrowRight size={17} /></Link>
      </EmptyState>
    ) : (
      <div className="mock-hub-grid">
        {rows.map(({ exam, mock, lastScore }) => {
          const statusKey = (mock ? mock.status : 'none') as keyof typeof STATUS_LABEL
          const scoreReachedTarget = lastScore !== null && lastScore >= exam.targetScore
          return <article className="mock-hub-card" key={exam.examId}>
            <div className="card-top">
              <span className="tag">{exam.remainingDays} 天后考试</span>
              <span className={`mock-hub-status is-${statusKey}`}>{STATUS_LABEL[statusKey]}</span>
            </div>
            <h2>{exam.course}</h2>
            <p className="muted"><CalendarDays size={15} />{exam.examDate}</p>
            <p className="mock-hub-hint">{STATUS_HINT[statusKey]}</p>
            {statusKey === 'graded' && lastScore !== null && (
              <div className={`mock-hub-score ${scoreReachedTarget ? 'is-target' : ''}`}>
                <span className="muted">上次成绩</span>
                <strong>{lastScore}<small> / {exam.maxScore}</small></strong>
                {scoreReachedTarget
                  ? <span className="mock-hub-score-flag">已达目标 {exam.targetScore}</span>
                  : <span className="mock-hub-score-flag is-gap">距目标还差 {exam.targetScore - lastScore} 分</span>}
              </div>
            )}
            <div className="mock-hub-bottom">
              <span className="muted">目标 <strong>{exam.targetScore}</strong> / {exam.maxScore}</span>
              <Link className="button button-quiet" to={`/app/exams/${exam.examId}/mock`}>{CTA_LABEL[statusKey]}<ArrowRight size={17} /></Link>
            </div>
          </article>
        })}
      </div>
    )}
  </>
}