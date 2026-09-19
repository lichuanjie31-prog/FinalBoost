import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, FileImage, RefreshCw, Upload, X } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { AIPanel } from '../../components/AIPanel'
import { study, type Exam } from '../../api/study'
import { marking, tokenUsage, PROVIDER_LABEL, type MarkingJob, type MarkingReadiness } from '../../api/marking'
import { capabilities, type Capabilities } from '../../api/capabilities'
import { ApiError } from '../../api/client'
import { MarkingReport } from './MarkingReport'

type LocalFile = { file: File; key: string; uploadedId?: string }

const TERMINAL = new Set(['succeeded', 'failed', 'submission_unknown'])
const STATUS_LABEL: Record<string, string> = {
  submitting: '提交中', submission_unknown: '提交结果未知', queued: '排队中',
  running: '处理中', succeeded: '批改完成', failed: '批改失败',
}
const MAX_PAGES = 10

const wait = (seconds: number) => new Promise(resolve => setTimeout(resolve, seconds * 1000))

// Which provider and model produced this page, plus what it cost, so a result
// can always be traced back to the call that made it.
function Provenance({ job }: { job: MarkingJob }) {
  const usage = tokenUsage(job)
  return <p className="fine-print" data-testid="page-provenance">
    {PROVIDER_LABEL[job.source] ?? job.source}
    {job.model ? ` · ${job.model}` : ''}
    {job.providerJobId ? ` · 任务 ${job.providerJobId}` : ''}
    {job.latencyMs ? ` · 耗时 ${(job.latencyMs / 1000).toFixed(1)}s` : ''}
    {usage?.total_tokens ? ` · Token ${usage.prompt_tokens ?? '—'}/${usage.completion_tokens ?? '—'}/${usage.total_tokens}` : ''}
  </p>
}

function Preview({ file }: { file: File }) {
  const [url, setUrl] = useState('')
  useEffect(() => { const value = URL.createObjectURL(file); setUrl(value); return () => URL.revokeObjectURL(value) }, [file])
  return url ? <img src={url} alt={file.name} /> : null
}

export function MarkingStudy({ id }: { id: string }) {
  const [exam, setExam] = useState<Exam | null>(null)
  const [jobs, setJobs] = useState<MarkingJob[]>([])
  const [readiness, setReadiness] = useState<MarkingReadiness | null>(null)
  const [service, setService] = useState<Capabilities | null>(null)
  const [files, setFiles] = useState<LocalFile[]>([])
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const [error, setError] = useState(''), [uploadError, setUploadError] = useState('')
  const [progress, setProgress] = useState(''), [dragging, setDragging] = useState(false)
  const [reload, setReload] = useState(0)
  const submitLock = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const intent = useRef(crypto.randomUUID())
  const jobsRef = useRef(jobs); jobsRef.current = jobs
  // 已受理的页（按文件 key）。重试时跳过它们，避免重复提交已受理的页。
  const accepted = useRef<Set<string>>(new Set())

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    Promise.all([study.exam(id, controller.signal), marking.jobs(id, controller.signal),
      marking.readiness(controller.signal), capabilities(controller.signal)])
      .then(([e, page, state, s]) => {
        if (controller.signal.aborted) return
        setExam(e)
        setJobs([...page.items].sort((a, b) => a.pageIndex - b.pageIndex))
        setReadiness(state); setService(s)
      })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id, reload])

  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>
    async function poll() {
      const pending = jobsRef.current.filter(j => !TERMINAL.has(j.status))
      if (pending.length) {
        try {
          const updated = await Promise.all(pending.map(j => marking.job(j.jobId, controller.signal)))
          if (!controller.signal.aborted) {
            setJobs(old => old.map(j => updated.find(u => u.jobId === j.jobId) || j))
            setError('')
          }
        } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2000)
    }
    timer = setTimeout(poll, 2000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [id])

  function choose(selected: FileList | null) {
    if (!selected || busy) return
    const candidates = Array.from(selected)
    if (candidates.length + files.length > MAX_PAGES) { setUploadError(`一次最多上传 ${MAX_PAGES} 张答题图片`); return }
    if (candidates.some(f => !['image/jpeg', 'image/png', 'image/webp'].includes(f.type) || f.size > 10 * 1024 * 1024)) {
      setUploadError('请选择 JPEG、PNG 或 WebP 图片，每张不超过 10 MiB'); return
    }
    setFiles(old => [...old, ...candidates.map(file => ({ file, key: crypto.randomUUID() }))])
    setUploadError(''); intent.current = crypto.randomUUID()
    if (fileInput.current) fileInput.current.value = ''
  }

  // A page that hit the vendor rate limit is retried with the SAME request key, so
  // the backend deduplicates it and the vendor is never charged twice.
  async function submitPage(fileId: string, pageIndex: number) {
    const requestKey = `${intent.current}:${pageIndex}`
    const gap = readiness?.submitIntervalSeconds || 6
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await marking.submit({ examId: id, fileId, pageIndex, requestKey })
      } catch (e) {
        const failure = e as ApiError
        if (failure.status === 429 && attempt < 5) { setProgress(`第 ${pageIndex + 1} 页等待提交限额（每分钟 10 张）`); await wait(gap); continue }
        throw e
      }
    }
  }

  async function submit() {
    if (submitLock.current || !files.length) return
    submitLock.current = true
    setBusy(true); setUploadError('')
    try {
      const current = [...files]
      for (let i = 0; i < current.length; i++) {
        setProgress(`正在上传第 ${i + 1} / ${current.length} 张图片`)
        if (!current[i].uploadedId) {
          const uploaded = await study.upload(current[i].file, current[i].key)
          current[i] = { ...current[i], uploadedId: uploaded.fileId }
          setFiles([...current])
        }
      }
      // 每受理一页就并入结果列表：该页立刻显示并进入轮询，
      // 不必等所有页都成功——否则后一页失败会让已受理的页一起消失。
      // 已受理的页在重试时直接跳过：页码与 requestKey 都不变，
      // 既不会把已受理的页重复提交给供应商，也不会重复计费。
      for (let i = 0; i < current.length; i++) {
        const entry = current[i]
        if (accepted.current.has(entry.key)) continue
        setProgress(`正在提交第 ${i + 1} / ${current.length} 页批改任务`)
        const job = await submitPage(entry.uploadedId!, i)
        accepted.current.add(entry.key)
        setJobs(old => {
          const merged = [...old]
          const at = merged.findIndex(j => j.jobId === job.jobId)
          if (at >= 0) merged[at] = job; else merged.push(job)
          return merged.sort((a, b) => a.pageIndex - b.pageIndex)
        })
      }
      setFiles([]); accepted.current = new Set(); intent.current = crypto.randomUUID()
    } catch (e) { setUploadError((e as Error).message) }
    finally { submitLock.current = false; setBusy(false); setProgress('') }
  }

  if (loading) return <div className="empty-state" role="status">正在读取考试记录…</div>
  if (!exam) return <div className="panel"><ErrorMessage error={error} /><button className="button button-quiet" onClick={() => setReload(v => v + 1)}>重新加载</button><Link to="/app" className="text-link">返回我的备考</Link></div>

  const ready = readiness?.ready === true
  const pending = jobs.filter(j => !TERMINAL.has(j.status))
  const done = jobs.filter(j => j.status === 'succeeded')
  const failed = jobs.filter(j => j.status === 'failed')
  const unresolved = jobs.filter(j => j.status === 'submission_unknown')

  return <div className="exam-study">
    <Link className="text-link back-link" to="/app"><ArrowLeft size={16} />我的备考</Link>
    <div className="workspace-title"><div><span className="eyebrow">EXAM WORKSPACE</span><h1>{exam.course}</h1><p>{exam.examDate} 考试 · 目标 {exam.targetScore} / {exam.maxScore} 分</p></div><div className="days-left"><strong>{exam.remainingDays}</strong><span>天后考试</span></div></div>
    <div className="study-steps" aria-label="备考流程"><span className="current"><b>01</b>上传试卷</span><span className={jobs.length ? 'current' : ''}><b>02</b>查看批改</span><span className={done.length ? 'current' : ''}><b>03</b>和 AI 一起复习</span></div>
    <ErrorMessage error={error} />
    <div className="study-columns"><div className="study-materials">
      <section className="panel upload-panel">
        <div className="panel-title"><div><span className="eyebrow">YOUR PAPER</span><h2>上传试卷，开始查漏补缺</h2></div><FileImage size={22} /></div>
        <p className="muted">上传包含题目与作答的清晰照片，按页码顺序排列，每一页会单独创建批改任务。</p>
        {readiness && !ready && <p className="study-warning" role="alert" data-testid="marking-not-configured">
          <AlertTriangle size={16} />{readiness.message} 批改功能暂不可用，不会生成示例分数。</p>}
        {readiness && <p className="fine-print" data-testid="marking-provider">
          当前批改服务：{PROVIDER_LABEL[readiness.provider] ?? readiness.provider}
          {readiness.model ? ` · ${readiness.model}` : ''}{readiness.ready ? '' : '（未配置）'}</p>}
        {readiness?.mode === 'fixture' && <p className="study-mode" data-testid="marking-fixture">离线验收模式：腾讯云边界由本地桩替代，未发生真实调用</p>}
        <label className={'upload-zone ' + (dragging ? 'is-dragging ' : '') + (busy ? 'is-disabled' : '')} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); choose(e.dataTransfer.files) }}>
          <span className="upload-symbol"><Upload size={26} /></span><strong>拖入试卷照片，或点击选择</strong><span>JPEG、PNG、WebP · 每张最多 10 MiB</span><small>最多 {MAX_PAGES} 张 · 已选 {files.length} 张</small>
          <input ref={fileInput} type="file" aria-label="选择答题图片" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={e => choose(e.target.files)} />
        </label>
        {!!files.length && <ol className="paper-previews">{files.map((entry, index) => <li key={entry.key}><Preview file={entry.file} /><div><strong>第 {index + 1} 页</strong><span>{entry.file.name}</span></div>{entry.uploadedId && <CheckCircle2 size={16} />}<button className="icon-button" disabled={busy} aria-label={'移除 ' + entry.file.name} onClick={() => { setFiles(old => old.filter(f => f.key !== entry.key)); intent.current = crypto.randomUUID() }}><X size={16} /></button></li>)}</ol>}
        <ErrorMessage error={uploadError} />{progress && <p role="status" className="progress-message">{progress}</p>}
        <button className="button full-width" disabled={busy || !files.length || !ready} onClick={submit}>{busy ? '正在提交…' : '上传并开始批改'}<ArrowRight size={17} /></button>
        <p className="fine-print">由{PROVIDER_LABEL[readiness?.provider ?? ''] ?? 'AI'}识别题目、作答、正误与解析，结果以文字形式展示，原卷坐标批注仍在测试中。多页试卷按页顺序分别提交，每页独立批改。AI 批改结果仅供参考，请自行核对。</p>
      </section>

      <section className="panel jobs-panel">
        <div className="panel-title"><div><span className="eyebrow">FEEDBACK</span><h2>批改结果</h2></div><span className="tag tag-muted">{jobs.length} 页任务</span></div>
        {!jobs.length ? <div className="results-empty"><FileImage size={32} /><h3>你的第一份分析，从这里开始</h3><p>提交试卷后，在这里按页查看题目、作答、正误和解析。</p></div> : <>
          {pending.length > 0 && <p role="status" className="progress-message" data-testid="marking-pending"><RefreshCw size={16} className="spin" />AI 正在识别并批改试卷…共 {pending.length} 页，可安全刷新页面</p>}
          {unresolved.length > 0 && <p className="study-warning" role="alert" data-testid="marking-unresolved"><AlertTriangle size={16} />有 {unresolved.length} 页提交结果未知，请勿重复提交以免重复计费，可联系管理员核对。</p>}
          <ol className="marking-pages">
            {jobs.map(job => <li key={job.jobId} className={'marking-page is-' + job.status} data-testid="marking-page">
              <div className="marking-page-head">
                <strong>第 {job.pageIndex + 1} 页</strong>
                <span className={'job-status ' + job.status} data-testid="page-status">{STATUS_LABEL[job.status] || job.status}</span>
              </div>
              <Provenance job={job} />
              {job.error && <><ErrorMessage error={job.error.message} />{job.error.code && <p className="fine-print" data-testid="page-error-code">错误码 {job.error.code}</p>}</>}
              {job.status === 'failed' && <p className="fine-print">未生成任何分数。请检查图片清晰度后重新上传该页。</p>}
              {job.result && <MarkingReport job={job} />}
            </li>)}
          </ol>
          {!!failed.length && <p className="fine-print" data-testid="marking-failed-note">{failed.length} 页批改失败，其余页面结果不受影响。</p>}
        </>}
      </section>
    </div><aside className="study-assistant"><AIPanel key={exam.examId} course={exam.course} examId={exam.examId} markingJobIds={done.map(job => job.jobId)} chatMode={service?.chatMode} /></aside></div>
  </div>
}
