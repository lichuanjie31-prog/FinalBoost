import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download, FileSpreadsheet } from 'lucide-react'
import { questionBank, type PrivatePaper } from '../../api/questionBank'
import { ErrorMessage } from '../../components/Shared'
import { displayTime } from './filters'
import { formatSize } from './components/PaperMeta'

export function PrivatePaperDetailPage() {
  const { id='' } = useParams()
  const [paper,setPaper] = useState<PrivatePaper|null>(null), [loading,setLoading] = useState(true)
  const [error,setError] = useState(''), [downloading,setDownloading] = useState(false), [version,setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    questionBank.privatePaper(id,controller.signal).then(setPaper).catch(error => { if (!controller.signal.aborted) setError(error.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id,version])
  async function download() {
    if (!paper) return
    setDownloading(true); setError('')
    try { await questionBank.downloadPrivate(paper.paperId,paper.fileName) }
    catch (error) { setError((error as Error).message) } finally { setDownloading(false) }
  }
  if (loading) return <div className="empty-state" role="status">正在读取试卷详情…</div>
  if (!paper) return <div className="panel"><ErrorMessage error={error} /><button className="text-button" onClick={() => setVersion(value=>value+1)}>重新加载</button></div>
  return <><Link className="text-link back-link" to="/app/question-bank"><ArrowLeft size={16} />私人题库</Link><div className="workspace-title"><div><span className="eyebrow">PRIVATE PAPER</span><h1>{paper.name}</h1><p>{paper.subject.name} · 创建于 {displayTime(paper.createdAt)}</p></div><button className="button" disabled={downloading} onClick={download}><Download size={17} />{downloading ? '正在下载…' : '下载 XLSX'}</button></div><ErrorMessage error={error} />
    <section className="panel qb-detail-panel"><div className="qb-detail-file"><FileSpreadsheet size={34} /><div><strong>{paper.fileName}</strong><span>受保护的私人 XLSX 文件</span></div></div><dl className="qb-detail-list"><div><dt>科目</dt><dd>{paper.subject.name}</dd></div><div><dt>学院</dt><dd>{paper.college}</dd></div><div><dt>年份</dt><dd>{paper.year}</dd></div><div><dt>学期</dt><dd>{paper.semester}</dd></div><div><dt>文件大小</dt><dd>{formatSize(paper.fileSize)}</dd></div><div><dt>来源</dt><dd>{paper.sourcePublicPaperId ? '从公共题库复制' : '由你上传'}</dd></div></dl></section>
  </>
}
