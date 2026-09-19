import { useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, BookOpen, Plus } from 'lucide-react'
import { questionBank } from '../../api/questionBank'
import { EmptyState, ErrorMessage } from '../../components/Shared'
import { LoadMoreButton } from './components/LoadMoreButton'
import { PaperFilters } from './components/PaperFilters'
import { PaperMeta } from './components/PaperMeta'
import { useCursorList } from './hooks/useCursorList'
import { useSubjects } from './hooks/useSubjects'
import { displayTime, readFilters, writeFilters } from './filters'

export function PrivatePapersPage() {
  const [params,setParams] = useSearchParams(), serialized = params.toString()
  const filters = useMemo(() => readFilters(new URLSearchParams(serialized)), [serialized])
  const loader = useCallback((cursor:string|null,signal:AbortSignal) => questionBank.privatePapers(filters,cursor,signal), [filters])
  const list = useCursorList(loader), subjectState = useSubjects()
  return <><div className="workspace-title"><div><span className="eyebrow">MY QUESTION BANK</span><h1>私人题库</h1><p>按科目保存试卷，随时下载自己的原始文件。</p></div><Link className="button" to="/app/question-bank/upload"><Plus size={18} />上传试卷</Link></div>
    <PaperFilters values={filters} subjects={subjectState.subjects} onApply={values => setParams(writeFilters(values))} />
    {(list.error || subjectState.error) && <div className="qb-page-error"><ErrorMessage error={list.error || subjectState.error} /><button className="text-button" onClick={() => { list.reload(); subjectState.reload() }}>重新加载</button></div>}
    {list.loading ? <div className="empty-state" role="status">正在读取私人题库…</div> : list.items.length === 0 ? <EmptyState><BookOpen size={36} /><h2>私人题库还是空的</h2><p>上传第一份 XLSX 试卷，建立自己的复习资料库。</p><Link className="button button-quiet" to="/app/question-bank/upload">上传第一份试卷<ArrowRight size={17} /></Link></EmptyState> : <div className="qb-paper-grid">{list.items.map(paper => <Link className="qb-paper-card" key={paper.paperId} to={`/app/question-bank/papers/${paper.paperId}`}><div className="qb-card-head"><span className="tag">{paper.subject.name}</span>{paper.sourcePublicPaperId && <span className="qb-source">来自公共题库</span>}</div><h2>{paper.name}</h2><PaperMeta college={paper.college} year={paper.year} semester={paper.semester} fileSize={paper.fileSize} /><div className="qb-card-foot"><span>{displayTime(paper.createdAt)}</span><span>查看详情<ArrowRight size={15} /></span></div></Link>)}</div>}
    <LoadMoreButton hasMore={Boolean(list.nextCursor)} loading={list.loadingMore} onClick={list.loadMore} />
  </>
}
