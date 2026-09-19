import { useRef, useState, type FormEvent } from 'react'
import { ArrowRight, CheckCircle2, FileSpreadsheet, Upload, X } from 'lucide-react'
import { questionBank, type Paper, type Subject } from '../../../api/questionBank'
import { ErrorMessage } from '../../../components/Shared'
import { formatSize } from './PaperMeta'
import { SubjectPicker } from './SubjectPicker'

export function UploadPaperForm({ subjects, admin, onSubjectCreated, onSuccess }: {
  subjects: Subject[]; admin: boolean; onSubjectCreated: (subject: Subject) => void; onSuccess: (paper: Paper) => void
}) {
  const [subjectId, setSubjectId] = useState(''), [name, setName] = useState(''), [college, setCollege] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear())), [semester, setSemester] = useState('第一学期')
  const [file, setFile] = useState<File | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null), intent = useRef({ fingerprint:'', key:crypto.randomUUID() })
  function choose(selected: File | null) {
    setError('')
    if (!selected) { setFile(null); return }
    if (!selected.name.toLowerCase().endsWith('.xlsx')) { setError('请选择 .xlsx 文件'); if (input.current) input.current.value=''; return }
    if (selected.size > 20 * 1024 * 1024) { setError('XLSX 文件不能超过 20 MiB'); if (input.current) input.current.value=''; return }
    setFile(selected)
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (!file) { setError('请选择需要上传的 XLSX 文件'); return }
    const payload = { file, subjectId, name:name.trim(), college:college.trim(), year:Number(year), semester:semester.trim(), visibility:admin ? 'public' as const : 'private' as const }
    const fingerprint = JSON.stringify({ ...payload, file:{ name:file.name,size:file.size,lastModified:file.lastModified } })
    if (intent.current.fingerprint !== fingerprint) intent.current = { fingerprint, key:crypto.randomUUID() }
    setBusy(true)
    try { onSuccess(await questionBank.upload(payload, intent.current.key)) }
    catch (error) { setError((error as Error).message) } finally { setBusy(false) }
  }
  return <form className="panel qb-upload-form" onSubmit={submit}>
    <SubjectPicker subjects={subjects} value={subjectId} admin={admin} disabled={busy} onChange={setSubjectId} onCreated={onSubjectCreated} />
    <div className="form-columns"><label>试卷名称<input required maxLength={200} value={name} disabled={busy} onChange={event => setName(event.target.value)} placeholder="例如：2025 数据结构期末试卷" /></label><label>学院<input required maxLength={100} value={college} disabled={busy} onChange={event => setCollege(event.target.value)} placeholder="例如：计算机与人工智能学院" /></label></div>
    <div className="form-columns"><label>年份<input required type="number" min="1900" max="2100" value={year} disabled={busy} onChange={event => setYear(event.target.value)} /></label><label>学期<input required maxLength={30} value={semester} disabled={busy} onChange={event => setSemester(event.target.value)} placeholder="例如：第一学期" /></label></div>
    {!file ? <label className={`upload-zone ${busy ? 'is-disabled' : ''}`}><Upload size={28} /><strong>选择 XLSX 试卷文件</strong><span>仅支持 .xlsx · 最大 20 MiB</span><input ref={input} type="file" aria-label="选择 XLSX 试卷文件" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={event => choose(event.target.files?.[0] || null)} /></label> : <div className="qb-selected-file"><FileSpreadsheet size={22} /><div><strong>{file.name}</strong><span>{formatSize(file.size)}</span></div><CheckCircle2 size={18} className="qb-file-ok" /><button type="button" className="icon-button" aria-label={`移除 ${file.name}`} disabled={busy} onClick={() => { setFile(null); if (input.current) input.current.value = '' }}><X size={18} /></button></div>}
    <ErrorMessage error={error} />
    <div className="qb-upload-actions"><p>上传后不会解析题目内容。{admin ? '公共试卷将先保存为草稿。' : '文件仅对你的账号开放。'}</p><button className="button" disabled={busy || !file || !subjectId}>{busy ? '正在安全上传…' : admin ? '保存为公共草稿' : '上传到私人题库'}{!busy && <ArrowRight size={17} />}</button></div>
  </form>
}
