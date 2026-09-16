import type { Grading } from '../../api/study'

export function QuestionScores({ result }: { result: NonNullable<Grading['result']> }) {
  return <table className="question-scores" aria-label="逐题评分"><thead><tr><th>知识点</th><th>得分 / 满分</th><th>评语</th></tr></thead><tbody>{result.questions.map(q => <tr key={q.questionId}><td>{q.knowledgePoints.join('、')}</td><td>{q.score ?? '待评估'} / {q.maxScore}</td><td>{q.errorReason ?? (q.correct ? '本题正确' : '暂无评语')}</td></tr>)}</tbody></table>
}
