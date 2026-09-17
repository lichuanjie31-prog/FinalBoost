let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null
export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string) { super(message) }
}
export function setToken(token: string | null) { accessToken = token }
export async function refreshSession(): Promise<boolean> {
  if (!refreshPromise) refreshPromise = fetch('/api/v1/auth/refresh', {
    method: 'POST', credentials: 'include', headers: { 'X-Requested-With': 'FinalBoost' },
  }).then(async r => {
    if (!r.ok) { accessToken = null; return false }
    accessToken = (await r.json()).data.accessToken
    return true
  }).catch(() => false).finally(() => { refreshPromise = null })
  return refreshPromise
}
export async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('X-Requested-With', 'FinalBoost')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let response: Response
  try { response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'include' }) }
  catch (e) { if (e instanceof DOMException && e.name === 'AbortError') throw e; throw new ApiError(0, '暂时无法连接服务，请稍后重试。') }
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return request<T>(path, options, false)
    window.dispatchEvent(new Event('session-expired'))
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, payload?.message || '请求未完成，请稍后重试。', payload?.requestId)
  return payload.data as T
}
export function post<T>(path: string, body: unknown, key: string = crypto.randomUUID()): Promise<T> {
  return request<T>(path, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body) })
}
export async function download(path: string): Promise<Blob> {
  const headers = new Headers({ 'X-Requested-With': 'FinalBoost' })
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(`/api/v1${path}`, { headers, credentials: 'include' })
  if (!response.ok) throw new ApiError(response.status, '文件下载失败，请稍后重试。')
  return response.blob()
}
