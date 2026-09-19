import type { components } from './generated'
import { request, post } from './client'
export type Exam = components['schemas']['ExamOut']
export type ExamInput = components['schemas']['ExamIn']
export type Grading = components['schemas']['GradingOut']
export type Diagnosis = components['schemas']['DiagnosisOut']
export type UploadedFile = components['schemas']['FileOut']
export type AuthResult = components['schemas']['AuthOut']
export type Training = components['schemas']['TrainingOut']
export type TrainingInput = components['schemas']['TrainingIn']
export type StageDetail = components['schemas']['StageOut']
export type TrainingQuestion = components['schemas']['QuestionOut']
export type Attempt = components['schemas']['AttemptOut']
export type AttemptAccepted = components['schemas']['AttemptAccepted']
export type Quiz = components['schemas']['QuizOut']
export type QuizAnswer = components['schemas']['QuizAnswerOut']
export type StageComplete = components['schemas']['StageCompleteOut']
export type ExportAccepted = components['schemas']['ExportAccepted']
export type ExportStatus = components['schemas']['ExportOut']
export type ExportInput = components['schemas']['ExportIn']

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
export const training = {
  list: (signal?: AbortSignal) => allPages<Training>('/trainings', signal),
  get: (id: string, signal?: AbortSignal) => request<Training>(`/trainings/${id}`, { signal }),
  create: (body: TrainingInput, key: string) => post<Training>('/trainings', body, key),
  stage: (id: string, type: string, signal?: AbortSignal) => request<StageDetail>(`/trainings/${id}/stages/${type}`, { signal }),
  completeStage: (id: string, type: string) => post<StageComplete>(`/trainings/${id}/stages/${type}/complete`, {}),
  attempt: (id: string, body: components['schemas']['AttemptIn'], key: string) => post<AttemptAccepted>(`/trainings/${id}/attempts`, body, key),
  getAttempt: (id: string, attemptId: string, signal?: AbortSignal) => request<Attempt>(`/trainings/${id}/attempts/${attemptId}`, { signal }),
  createQuiz: (id: string) => post<Quiz>(`/trainings/${id}/quiz`, {}),
  answerQuiz: (id: string, body: components['schemas']['QuizAnswerIn']) => post<QuizAnswer>(`/trainings/${id}/quiz/answer`, body),
  exportPdf: (id: string, body: ExportInput, key: string) => post<ExportAccepted>(`/trainings/${id}/pdf`, body, key),
  getExport: (id: string, exportId: string, signal?: AbortSignal) => request<ExportStatus>(`/trainings/${id}/pdf/${exportId}`, { signal }),
}
