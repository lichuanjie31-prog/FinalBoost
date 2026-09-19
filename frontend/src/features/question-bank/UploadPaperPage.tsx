import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { ErrorMessage } from '../../components/Shared'
import { UploadPaperForm } from './components/UploadPaperForm'
import { useSubjects } from './hooks/useSubjects'

export function UploadPaperPage() {
  const navigate = useNavigate(), state = useSubjects()
  return <><Link className="text-link back-link" to="/app/question-bank"><ArrowLeft size={16} />私人题库</Link><div className="workspace-title"><div><span className="eyebrow">UPLOAD PRIVATE PAPER</span><h1>上传私人试卷</h1><p>只保存文件与检索信息，本阶段不会解析题目内容。</p></div></div>
    <ErrorMessage error={state.error} />
    {state.loading ? <div className="empty-state" role="status">正在读取科目…</div> : <UploadPaperForm subjects={state.subjects} admin={false} onSubjectCreated={subject => state.setSubjects(current => [...current.filter(item => item.subjectId !== subject.subjectId),subject].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')))} onSuccess={paper => navigate(`/app/question-bank/papers/${paper.paperId}`,{replace:true})} />}
  </>
}
