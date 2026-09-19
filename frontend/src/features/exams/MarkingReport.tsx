import { PROVIDER_LABEL, type MarkingAnswer, type MarkingJob, type MarkingQuestion } from '../../api/marking'

const MISSING = '未提供'
const provided = (value?: string | null) => (value && value.trim() ? value : MISSING)

// An answer the grader did not judge is reported as 未判定, never as wrong.
function Verdict({ correct }: { correct: boolean | null }) {
  const state = correct === true ? 'is-right' : correct === false ? 'is-wrong' : 'is-unknown'
  const label = correct === true ? '正确' : correct === false ? '错误' : '未判定'
  return <span className={'mark-verdict ' + state} data-testid="mark-verdict">{label}</span>
}

function tally(questions: MarkingQuestion[]) {
  const counts = { right: 0, wrong: 0, unknown: 0 }
  const walk = (question: MarkingQuestion) => {
    question.answers.forEach(answer => {
      if (answer.correct === true) counts.right += 1
      else if (answer.correct === false) counts.wrong += 1
      else counts.unknown += 1
    })
    question.children.forEach(walk)
  }
  questions.forEach(walk)
  return counts
}

function AnswerRow({ answer }: { answer: MarkingAnswer }) {
  const confidence = typeof answer.confidence === 'number' ? Math.round(answer.confidence * 100) : null
  return <li className="mark-answer">
    <div className="mark-answer-head">
      <span className="mark-label">学生作答</span>
      <span className="mark-answer-tags">
        {confidence !== null && <span className="mark-confidence" data-testid="mark-confidence">模型置信度 {confidence}%</span>}
        <Verdict correct={answer.correct} />
      </span>
    </div>
    <p className="mark-handwriting" data-testid="mark-handwriting">{provided(answer.handwriting)}</p>
    {answer.correct === null && <p className="mark-uncertain" data-testid="mark-uncertain">
      说明：图片内容无法可靠识别，请人工确认。该题不计为错误。</p>}
    <dl className="mark-fields">
      <div><dt>正确答案</dt><dd data-testid="mark-right-answer">{provided(answer.rightAnswer)}</dd></div>
      {answer.correct === false && <div><dt>错误原因</dt><dd data-testid="mark-error-reason">{provided(answer.errorReason)}</dd></div>}
      <div><dt>解析</dt><dd data-testid="mark-analysis">{provided(answer.analysis)}</dd></div>
      <div><dt>知识点</dt><dd data-testid="mark-knowledge">{answer.knowledgePoints.length ? answer.knowledgePoints.join('、') : MISSING}</dd></div>
    </dl>
  </li>
}

function QuestionBlock({ question, depth }: { question: MarkingQuestion; depth: number }) {
  return <div className={'mark-question mark-depth-' + depth} data-testid="mark-question">
    <div className="mark-question-head">
      <span className="mark-index">{question.questionId}</span>
      <strong data-testid="mark-stem">{provided(question.text)}</strong>
      <span className="tag tag-muted">{[question.subject, question.questionType].filter(Boolean).join(' · ') || MISSING}</span>
    </div>
    {question.rightAnswer && <p className="mark-question-answer">本题正确答案：{question.rightAnswer}</p>}
    {question.answers.length > 0 && <ul className="mark-answers">{question.answers.map(answer => <AnswerRow key={answer.answerId} answer={answer} />)}</ul>}
    {question.children.map(child => <QuestionBlock key={child.questionId} question={child} depth={depth + 1} />)}
  </div>
}

export function MarkingReport({ job }: { job: MarkingJob }) {
  const result = job.result
  if (!result) return null
  const counts = tally(result.questions)
  return <div className="marking-report" data-testid="marking-report">
    <p className="mark-notice">{result.notice}</p>
    <div className="mark-summary" data-testid="mark-summary">
      <span className="mark-stat is-right">正确 {counts.right}</span>
      <span className="mark-stat is-wrong">错误 {counts.wrong}</span>
      <span className="mark-stat is-unknown">未判定 {counts.unknown}</span>
      <span className="mark-stat mark-stat-note">缺少评分细则，未计算百分制分数</span>
    </div>
    <p className="mark-provenance" data-testid="mark-provenance">
      识别 {result.questions.length} 题 · 由 {PROVIDER_LABEL[job.source] ?? job.source}
      {job.model ? `（${job.model}）` : ''} 批改
    </p>
    {result.questions.map(question => <QuestionBlock key={question.questionId} question={question} depth={0} />)}
  </div>
}
