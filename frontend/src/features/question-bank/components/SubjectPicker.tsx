import { useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { questionBank, type Subject } from '../../../api/questionBank'
import { ErrorMessage } from '../../../components/Shared'

export function SubjectPicker({ subjects, value, admin, disabled, onChange, onCreated }: {
  subjects: Subject[]; value: string; admin: boolean; disabled?: boolean
  onChange: (id: string) => void; onCreated: (subject: Subject) => void
}) {
  const [name, setName] = useState(''), [creating, setCreating] = useState(false), [error, setError] = useState('')
  const intent = useRef({ name:'', key:crypto.randomUUID() })
  async function create() {
    const normalized = name.trim().replace(/\s+/g, ' ')
    if (!normalized) { setError('请输入科目名称'); return }
    if (intent.current.name !== normalized) intent.current = { name:normalized, key:crypto.randomUUID() }
    setCreating(true); setError('')
    try {
      const subject = admin
        ? await questionBank.createSystemSubject(normalized, intent.current.key)
        : await questionBank.createPrivateSubject(normalized, intent.current.key)
      onCreated(subject); onChange(subject.subjectId); setName('')
    } catch (error) { setError((error as Error).message) } finally { setCreating(false) }
  }
  return <div className="qb-subject-picker">
    <label>科目<select required value={value} disabled={disabled || creating} onChange={event => onChange(event.target.value)}><option value="">请选择科目</option>{subjects.map(subject => <option key={subject.subjectId} value={subject.subjectId}>{subject.name}{subject.scope === 'private' ? ' · 私人' : ''}</option>)}</select></label>
    <div className="qb-new-subject"><label>{admin ? '新建系统科目' : '没有合适的科目？'}<input value={name} disabled={disabled || creating} onChange={event => { setName(event.target.value); setError('') }} maxLength={100} placeholder={admin ? '输入系统标准科目名称' : '输入私人科目名称'} /></label><button type="button" className="button button-secondary button-small" disabled={disabled || creating || !name.trim()} onClick={create}><Plus size={15} />{creating ? '创建中…' : '创建并选择'}</button></div>
    <ErrorMessage error={error} />
  </div>
}
