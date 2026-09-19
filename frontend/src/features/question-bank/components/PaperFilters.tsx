import { useEffect, useState, type FormEvent } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import type { PaperFilters as Values, Subject } from '../../../api/questionBank'

export function PaperFilters({ values, subjects, includeCollege = false, includeStatus = false, onApply }: {
  values: Values; subjects: Subject[]; includeCollege?: boolean; includeStatus?: boolean; onApply: (values: Values) => void
}) {
  const [draft, setDraft] = useState({ subjectId:'', q:'', college:'', year:'', semester:'', status:'' })
  useEffect(() => setDraft({
    subjectId: values.subjectId || '', q: values.q || '', college: values.college || '',
    year: values.year ? String(values.year) : '', semester: values.semester || '', status: values.status || '',
  }), [values])
  function submit(event: FormEvent) {
    event.preventDefault()
    onApply({
      subjectId:draft.subjectId || undefined, q:draft.q.trim() || undefined,
      college:draft.college.trim() || undefined, year:draft.year ? Number(draft.year) : undefined,
      semester:draft.semester.trim() || undefined,
      status:(draft.status || undefined) as Values['status'],
    })
  }
  function clear() {
    const empty = { subjectId:'', q:'', college:'', year:'', semester:'', status:'' }
    setDraft(empty); onApply({})
  }
  return <form className="qb-filters panel" onSubmit={submit}>
    <label className="qb-search"><span>试卷名称</span><div><Search size={15} /><input value={draft.q} onChange={event => setDraft({...draft,q:event.target.value})} placeholder="输入关键词" maxLength={200} /></div></label>
    <label><span>科目</span><select value={draft.subjectId} onChange={event => setDraft({...draft,subjectId:event.target.value})}><option value="">全部科目</option>{subjects.map(subject => <option key={subject.subjectId} value={subject.subjectId}>{subject.name}</option>)}</select></label>
    {includeCollege && <label><span>学院</span><input value={draft.college} onChange={event => setDraft({...draft,college:event.target.value})} placeholder="全部学院" maxLength={100} /></label>}
    <label><span>年份</span><input type="number" min="1900" max="2100" value={draft.year} onChange={event => setDraft({...draft,year:event.target.value})} placeholder="全部年份" /></label>
    <label><span>学期</span><input value={draft.semester} onChange={event => setDraft({...draft,semester:event.target.value})} placeholder="全部学期" maxLength={30} /></label>
    {includeStatus && <label><span>状态</span><select value={draft.status} onChange={event => setDraft({...draft,status:event.target.value})}><option value="">全部状态</option><option value="draft">草稿</option><option value="published">已发布</option><option value="unpublished">已下架</option></select></label>}
    <div className="qb-filter-actions"><button type="button" className="text-button" onClick={clear}><RotateCcw size={14} />重置</button><button className="button button-small">筛选</button></div>
  </form>
}
