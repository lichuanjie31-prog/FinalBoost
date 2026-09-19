import { request } from './client'

export type MarkingMode = 'disabled' | 'fixture' | 'tencent'

export interface Capabilities {
  gradingMode: 'mock' | 'llm'
  chatMode: 'mock' | 'llm'
  markingMode?: MarkingMode
  markingConfigured?: boolean
  markingMessage?: string
}

export const capabilities = (signal?: AbortSignal) => request<Capabilities>('/health', { signal })
