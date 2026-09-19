import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { UploadPaperForm } from './components/UploadPaperForm'
import { useSubjects } from './hooks/useSubjects'

export function AdminUploadPage() {
  const navigate = useNavigate(), state = useSubjects()
  return <><Link className="text-link back-link" to="/app/admin/question-bank"><ArrowLeft size={16} />公共试卷管理</Link><div className="workspace-title"><div><span className="eyebrow">UPLOAD PUBLIC PAPER</span><h1>上传公共试卷</h1><p>上传完成后先进入草稿状态，不会立即向学生公开。</p></div></div>
    <ErrorMessage error={state.error} />
    {state.loading ? <div className="empty-state" role="status">正在读取系统科目…</div> : <UploadPaperForm subjects={state.subjects} admin onSubjectCreated={subject => state.setSubjects(current => [...current.filter(item=>item.subjectId!==subject.subjectId),subject].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')))} onSuccess={() => navigate('/app/admin/question-bank',{replace:true})} />}
  </>
}
