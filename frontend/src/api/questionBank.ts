import type { components } from './generated'
import { download, post, request } from './client'

export type Subject = components['schemas']['SubjectOut']
export type Paper = components['schemas']['PaperOut']
export type PrivatePaper = components['schemas']['PrivatePaperOut']
export type PrivatePaperSummary = components['schemas']['PrivatePaperSummaryOut']
export type PublicPaper = components['schemas']['PublicPaperOut']
export type PublicationStatus = 'draft' | 'published' | 'unpublished'
export type Page<T> = { items: T[]; nextCursor?: string | null }
export type PaperFilters = {
  subjectId?: string; q?: string; college?: string; year?: number
  semester?: string; status?: PublicationStatus
}
export type PaperUpload = {
  file: File; subjectId: string; name: string; college: string
  year: number; semester: string; visibility: 'private' | 'public'
}

function pathWithQuery(path: string, values: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams()
  Object.entries(values).forEach(([name, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(name, String(value))
  })
  const serialized = query.toString()
  return serialized ? `${path}?${serialized}` : path
}

export const questionBank = {
  subjects: (q = '', cursor?: string | null, signal?: AbortSignal) =>
    request<Page<Subject>>(pathWithQuery('/subjects', { q, cursor, limit: 100 }), { signal }),
  createPrivateSubject: (name: string, key: string) => post<Subject>('/subjects/private', { name }, key),
  createSystemSubject: (name: string, key: string) => post<Subject>('/subjects/system', { name }, key),
  upload: (input: PaperUpload, key: string) => {
    const form = new FormData()
    form.append('file', input.file)
    form.append('subjectId', input.subjectId)
    form.append('name', input.name)
    form.append('college', input.college)
    form.append('year', String(input.year))
    form.append('semester', input.semester)
    form.append('visibility', input.visibility)
    return request<Paper>('/papers', { method: 'POST', body: form, headers: { 'Idempotency-Key': key } })
  },
  privatePapers: (filters: PaperFilters, cursor?: string | null, signal?: AbortSignal) =>
    request<Page<PrivatePaperSummary>>(pathWithQuery('/papers/private', { ...filters, status: undefined, college: undefined, cursor, limit: 20 }), { signal }),
  privatePaper: (id: string, signal?: AbortSignal) => request<PrivatePaper>(`/papers/private/${encodeURIComponent(id)}`, { signal }),
  downloadPrivate: (id: string, fileName: string) => download(`/papers/private/${encodeURIComponent(id)}/file`, fileName),
  publicPapers: (filters: PaperFilters, cursor?: string | null, signal?: AbortSignal) =>
    request<Page<PublicPaper>>(pathWithQuery('/public/papers', { ...filters, status: undefined, cursor, limit: 20 }), { signal }),
  copyPublic: (id: string, key: string) => post<PrivatePaper>(`/public/papers/${encodeURIComponent(id)}/copy`, {}, key),
  adminPapers: (filters: PaperFilters, cursor?: string | null, signal?: AbortSignal) =>
    request<Page<Paper>>(pathWithQuery('/admin/papers', { ...filters, college: undefined, cursor, limit: 20 }), { signal }),
  adminPaper: (id: string, signal?: AbortSignal) => request<Paper>(`/admin/papers/${encodeURIComponent(id)}`, { signal }),
  downloadAdmin: (id: string, fileName: string) => download(`/admin/papers/${encodeURIComponent(id)}/file`, fileName),
  publish: (id: string, key: string) => post<Paper>(`/admin/papers/${encodeURIComponent(id)}/publish`, {}, key),
  unpublish: (id: string, key: string) => post<Paper>(`/admin/papers/${encodeURIComponent(id)}/unpublish`, {}, key),
}
