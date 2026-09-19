import { request } from './client'

// 'live' means a real provider is active; 'fixture' swaps only the external
// boundary for a local stub during acceptance runs.
export type MarkingMode = 'disabled' | 'fixture' | 'live'
export type MarkingProvider = 'qwen' | 'tencent'

export interface Capabilities {
  gradingMode: 'mock' | 'llm'
  chatMode: 'mock' | 'llm'
  markingMode?: MarkingMode
  markingProvider?: MarkingProvider
  markingModel?: string | null
  markingConfigured?: boolean
  markingMessage?: string
}

export const capabilities = (signal?: AbortSignal) => request<Capabilities>('/health', { signal })
