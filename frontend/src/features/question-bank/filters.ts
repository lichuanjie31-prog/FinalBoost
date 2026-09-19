import type { PaperFilters } from '../../api/questionBank'

export function readFilters(params: URLSearchParams): PaperFilters {
  const year = Number(params.get('year'))
  const status = params.get('status')
  return {
    subjectId:params.get('subjectId') || undefined,
    q:params.get('q') || undefined,
    college:params.get('college') || undefined,
    year:Number.isInteger(year) && year >= 1900 && year <= 2100 ? year : undefined,
    semester:params.get('semester') || undefined,
    status:status === 'draft' || status === 'published' || status === 'unpublished' ? status : undefined,
  }
}

export function writeFilters(values: PaperFilters) {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([name,value]) => { if (value !== undefined && value !== '') params.set(name,String(value)) })
  return params
}

export function displayTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit' }).format(new Date(value))
}
