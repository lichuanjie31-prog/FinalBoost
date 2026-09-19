import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, FileClock, Plus, Send, Undo2 } from 'lucide-react'
import { questionBank, type Paper } from '../../api/questionBank'
import { EmptyState, ErrorMessage } from '../../components/Shared'
import { LoadMoreButton } from './components/LoadMoreButton'
import { PaperFilters } from './components/PaperFilters'
import { PaperMeta } from './components/PaperMeta'
import { PaperStatusBadge } from './components/PaperStatusBadge'
import { useCursorList } from './hooks/useCursorList'
import { useSubjects } from './hooks/useSubjects'
import { displayTime, readFilters, writeFilters } from './filters'

export function AdminPapersPage() {
  const [params,setParams] = useSearchParams(), serialized = params.toString()
  const filters = useMemo(() => readFilters(new URLSearchParams(serialized)), [serialized])
  const loader = useCallback((cursor:string|null,signal:AbortSignal) => questionBank.adminPapers(filters,cursor,signal), [filters])
  const list = useCursorList(loader), subjects = useSubjects()
  const [busy,setBusy] = useState<string|null>(null), [error,setError] = useState('')
  const keys = useRef(new Map<string,string>())
  async function transition(paper:Paper,action:'publish'|'unpublish') {
    const identity = `${paper.paperId}:${action}`
    if (!keys.current.has(identity)) keys.current.set(identity,crypto.randomUUID())
    setBusy(identity); setError('')
    try {
      const updated = action === 'publish'
        ? await questionBank.publish(paper.paperId,keys.current.get(identity)!)
        : await questionBank.unpublish(paper.paperId,keys.current.get(identity)!)
      list.setItems(items => items.map(item => item.paperId===paper.paperId ? updated : item))
    } catch (error) { setError((error as Error).message) } finally { setBusy(null) }
  }
  async function download(paper:Paper) {
    const identity = `${paper.paperId}:download`; setBusy(identity); setError('')
    try { await questionBank.downloadAdmin(paper.paperId,paper.fileName) }
    catch (error) { setError((error as Error).message) } finally { setBusy(null) }
  }
  return <><div className="workspace-title"><div><span className="eyebrow">ADMIN QUESTION BANK</span><h1>公共试卷管理</h1><p>上传草稿，确认信息后再发布到公共题库。</p></div><Link className="button" to="/app/admin/question-bank/upload"><Plus size={18} />上传公共试卷</Link></div>
    <PaperFilters values={filters} subjects={subjects.subjects} includeStatus onApply={values=>setParams(writeFilters(values))} />
    <ErrorMessage error={error || list.error || subjects.error} />
    {list.loading ? <div className="empty-state" role="status">正在读取公共试卷…</div> : list.items.length===0 ? <EmptyState><FileClock size={36} /><h2>还没有公共试卷</h2><p>上传第一份 XLSX 文件，它会先保存为草稿。</p></EmptyState> : <div className="qb-admin-list">{list.items.map(paper => <article className="panel qb-admin-paper" key={paper.paperId}><div className="qb-admin-paper-main"><div className="qb-card-head"><span className="tag">{paper.subject.name}</span><PaperStatusBadge status={paper.publicationStatus!} /></div><h2>{paper.name}</h2><PaperMeta college={paper.college} year={paper.year} semester={paper.semester} fileSize={paper.fileSize} /><small>创建于 {displayTime(paper.createdAt)}{paper.publishedAt ? ` · 最近发布 ${displayTime(paper.publishedAt)}` : ''}</small></div><div className="qb-admin-actions"><button className="text-button" disabled={busy!==null} onClick={()=>download(paper)}><Download size={15} />下载源文件</button>{paper.publicationStatus==='published' ? <button className="button button-secondary button-small" disabled={busy!==null} onClick={()=>transition(paper,'unpublish')}><Undo2 size={15} />{busy===`${paper.paperId}:unpublish`?'正在下架…':'下架'}</button> : <button className="button button-small" disabled={busy!==null} onClick={()=>transition(paper,'publish')}><Send size={15} />{busy===`${paper.paperId}:publish`?'正在发布…':paper.publicationStatus==='draft'?'发布':'重新发布'}</button>}</div></article>)}</div>}
    <LoadMoreButton hasMore={Boolean(list.nextCursor)} loading={list.loadingMore} onClick={list.loadMore} />
  </>
}
