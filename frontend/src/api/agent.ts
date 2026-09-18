import { request, post } from './client'

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result: string | null
}

export interface ChatResponse {
  sessionId: string
  message: string
  toolCalls: ToolCall[]
}

export interface AgentSession {
  sessionId: string
  title: string
  course: string | null
  createdAt: number
  updatedAt: number
  lastMessage: string | null
}

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  toolCalls: ToolCall[]
  toolCallId: string | null
  name: string | null
  createdAt: number
}

export const agent = {
  chat: (message: string, sessionId?: string | null, course?: string) =>
    post<ChatResponse>('/agent/chat', { message, sessionId: sessionId || undefined, course }),

  sessions: (signal?: AbortSignal) =>
    request<AgentSession[]>('/agent/sessions', { signal }),

  messages: (sessionId: string, signal?: AbortSignal) =>
    request<AgentMessage[]>(`/agent/sessions/${sessionId}/messages`, { signal }),

  deleteSession: (sessionId: string) =>
    request<{ deleted: boolean }>(`/agent/sessions/${sessionId}`, { method: 'DELETE' }),
}