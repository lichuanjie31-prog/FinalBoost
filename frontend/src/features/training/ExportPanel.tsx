import { useState } from 'react'
import { Download, FileText } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { training as trainingApi, type ExportStatus } from '../../api/study'
import { download } from '../../api/client'

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export function ExportPanel({ trainingId, title }: { trainingId: string; title: string }) {
  const [includeAnswers, setIncludeAnswers] = useState(true), [includeAnalysis, setIncludeAnalysis] = useState(true)
  const [busy, setBusy] = useState(false), [saving, setSaving] = useState(false)
  const [error, setError] = useState(''), [exported, setExported] = useState<ExportStatus | null>(null)

  async function run() {
    setBusy(true); setError(''); setExported(null)
    try {
      const accepted = await trainingApi.exportPdf(trainingId, { includeAnswers, includeAnalysis: includeAnswers && includeAnalysis }, crypto.randomUUID())
      let current = await trainingApi.getExport(trainingId, accepted.exportId)
      for (let i = 0; i < 40 && (current.status === 'queued' || current.status === 'running'); i++) { await sleep(400); current = await trainingApi.getExport(trainingId, accepted.exportId) }
      setExported(current)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function save() {
    if (!exported?.result) return
    setSaving(true); setError('')
    try {
      const blob = await download(exported.result.downloadUrl.replace('/api/v1', ''))
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = exported.result.fileName
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  return <section className="panel export-panel">
    <div className="panel-title"><h2>导出训练卷</h2><span className="tag">PDF</span></div>
    <p className="stage-content">生成可下载、可打印的《{title}》训练卷，训练记录保留题目与来源。</p>
    <label className="checkbox"><input type="checkbox" checked={includeAnswers} disabled={busy} onChange={e => setIncludeAnswers(e.target.checked)} />包含答案</label>
    <label className="checkbox"><input type="checkbox" checked={includeAnalysis} disabled={busy || !includeAnswers} onChange={e => setIncludeAnalysis(e.target.checked)} />包含解析</label>
    <ErrorMessage error={error} />
    {!exported && <button className="button full-width" disabled={busy} onClick={run}>{busy ? '正在生成 PDF…' : '生成 PDF'}<FileText size={17} /></button>}
    {exported?.status === 'succeeded' && exported.result && <button className="button full-width" disabled={saving} onClick={save}><Download size={17} />{saving ? '正在下载…' : `下载 ${exported.result.fileName}`}</button>}
    {exported?.status === 'failed' && <div className="attempt-result wrong"><span>{exported.error?.message || '导出失败，请稍后重试'}</span></div>}
    <p className="fine-print">文件在服务端生成，带有 AI 生成标识，仅本人可通过鉴权下载。</p>
  </section>
}
