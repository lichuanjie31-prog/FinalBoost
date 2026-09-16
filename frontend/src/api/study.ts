import type { components } from './generated'
import { request, post } from './client'
export type Exam = components['schemas']['ExamOut']
export type ExamInput = components['schemas']['ExamIn']
export type Grading = components['schemas']['GradingOut']
export type Diagnosis = components['schemas']['DiagnosisOut']
export type UploadedFile = components['schemas']['FileOut']
export type AuthResult = components['schemas']['AuthOut']

async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = []
  let cursor: string | null = null
  do {
    const result: { items: T[]; nextCursor?: string | null } = await request(`${path}?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, { signal })
    items.push(...result.items); cursor = result.nextCursor || null
  } while (cursor)
  return items
}
export const study = {
  exams: (signal?: AbortSignal) => allPages<Exam>('/exams', signal),
  exam: (id: string, signal?: AbortSignal) => request<Exam>(`/exams/${id}`, { signal }),
  create: (body: ExamInput, key: string) => post<Exam>('/exams', body, key),
  gradings: (id: string, signal?: AbortSignal) => allPages<Grading>(`/exams/${id}/gradings`, signal),
  grading: (id: string, signal?: AbortSignal) => request<Grading>(`/grading/${id}`, { signal }),
  diagnoses: (id: string, signal?: AbortSignal) => allPages<Diagnosis>(`/exams/${id}/diagnoses`, signal),
  diagnose: (id: string, gradingId: string) => post<Diagnosis>(`/exams/${id}/diagnosis`, { gradingId }),
  grade: (examId: string, fileIds: string[], key: string) => post<components['schemas']['GradingAccepted']>('/grading', { examId, fileIds }, key),
  upload: (file: File, key: string) => {
    const body = new FormData(); body.append('file', file)
    return request<UploadedFile>('/files/images', { method:'POST', body, headers:{ 'Idempotency-Key':key } })
  },
}
