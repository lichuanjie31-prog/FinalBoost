import type { components } from './generated'
import { request } from './client'

export type MarkingJob = components['schemas']['MarkingOutput']
export type MarkingReadiness = components['schemas']['MarkingReadiness']
export type MarkingPage = components['schemas']['MarkingPage']
export type MarkingResult = NonNullable<MarkingJob['result']>
export type MarkingQuestion = MarkingResult['questions'][number]
export type MarkingAnswer = MarkingQuestion['answers'][number]

export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

// `usage` is an open map on the wire (it mirrors whatever the provider reports),
// so it is narrowed here rather than pretending to a fixed shape.
export const tokenUsage = (job: MarkingJob): TokenUsage | null =>
  (job.usage as TokenUsage | null | undefined) ?? null

export const PROVIDER_LABEL: Record<string, string> = { qwen: '千问视觉', tencent: '腾讯云' }

export interface MarkingSubmit {
  examId: string
  fileId: string
  pageIndex: number
  requestKey: string
  referenceFileId?: string | null
}

export const marking = {
  readiness: (signal?: AbortSignal) => request<MarkingReadiness>('/marking/readiness', { signal }),
  jobs: (examId: string, signal?: AbortSignal) =>
    request<MarkingPage>(`/marking/jobs?examId=${encodeURIComponent(examId)}&limit=100`, { signal }),
  job: (id: string, signal?: AbortSignal) => request<MarkingJob>(`/marking/jobs/${id}`, { signal }),
  // The request key travels in the body: it is the provider-level idempotency
  // token that stops a retried page from being charged twice.
  submit: (body: MarkingSubmit) => request<MarkingJob>('/marking/jobs', { method: 'POST', body: JSON.stringify(body) }),
  imageUrl: (id: string) => `/api/v1/marking/jobs/${id}/image`,
}
