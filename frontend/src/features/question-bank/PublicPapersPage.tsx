import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Check, Globe2, LibraryBig } from 'lucide-react'
import { questionBank } from '../../api/questionBank'
import { EmptyState, ErrorMessage } from '../../components/Shared'
import { LoadMoreButton } from './components/LoadMoreButton'
import { PaperFilters } from './components/PaperFilters'
import { PaperMeta } from './components/PaperMeta'
import { useCursorList } from './hooks/useCursorList'
import { useSubjects } from './hooks/useSubjects'
import { displayTime, readFilters, writeFilters } from './filters'

export function PublicPapersPage() {
  const [params,setParams] = useSearchParams(), serialized = params.toString()
  const filters = useMemo(() => readFilters(new URLSearchParams(serialized)), [serialized])
  const loader = useCallback((cursor:string|null,signal:AbortSignal) => questionBank.publicPapers(filters,cursor,signal), [filters])
  const list = useCursorList(loader), subjects = useSubjects()
  const [busy,setBusy] = useState<string|null>(null), [actionError,setActionError] = useState('')
  const keys = useRef(new Map<string,string>())
  async function copy(id:string) {
    if (!keys.current.has(id)) keys.current.set(id,crypto.randomUUID())
    setBusy(id); setActionError('')
    try {
      const privatePaper = await questionBank.copyPublic(id,keys.current.get(id)!)
      list.setItems(items => items.map(item => item.paperId === id ? {...item,copied:true,privatePaperId:privatePaper.paperId} : item))
    } catch (error) { setActionError((error as Error).message) } finally { setBusy(null) }
  }
  return <><div className="workspace-title"><div><span className="eyebrow">PUBLIC LIBRARY</span><h1>公共题库</h1><p>找到合适的试卷，加入私人题库后即可下载。</p></div></div>
    <PaperFilters values={filters} subjects={subjects.subjects.filter(subject=>subject.scope==='system')} includeCollege onApply={values => setParams(writeFilters(values))} />
    <ErrorMessage error={actionError || list.error || subjects.error} />
    {list.loading ? <div className="empty-state" role="status">正在搜索公共题库…</div> : list.items.length === 0 ? <EmptyState><Globe2 size={36} /><h2>没有找到公开试卷</h2><p>换一个关键词或筛选条件再试试。</p></EmptyState> : <div className="qb-paper-grid">{list.items.map(paper => <article className="qb-paper-card" key={paper.paperId}><div className="qb-card-head"><span className="tag">{paper.subject.name}</span><span className="qb-source">发布于 {displayTime(paper.publishedAt)}</span></div><h2>{paper.name}</h2><PaperMeta college={paper.college} year={paper.year} semester={paper.semester} /><div className="qb-card-foot">{paper.copied && paper.privatePaperId ? <Link className="text-link qb-copied" to={`/app/question-bank/papers/${paper.privatePaperId}`}><Check size={15} />已加入，查看副本<ArrowRight size={14} /></Link> : <button className="button button-secondary button-small" disabled={busy===paper.paperId} onClick={() => copy(paper.paperId)}><LibraryBig size={15} />{busy===paper.paperId ? '正在加入…' : '加入私人题库'}</button>}</div></article>)}</div>}
    <LoadMoreButton hasMore={Boolean(list.nextCursor)} loading={list.loadingMore} onClick={list.loadMore} />
  </>
}
