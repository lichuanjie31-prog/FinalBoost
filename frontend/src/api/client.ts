let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null
export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string, public code?: number) { super(message) }
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
async function authorizedFetch(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(options.headers)
  headers.set('X-Requested-With', 'FinalBoost')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let response: Response
  try { response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'include' }) }
  catch (e) { if (e instanceof DOMException && e.name === 'AbortError') throw e; throw new ApiError(0, '暂时无法连接服务，请稍后重试。') }
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return authorizedFetch(path, options, false)
    window.dispatchEvent(new Event('session-expired'))
  }
  return response
}
export async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const response = await authorizedFetch(path, options, retry)
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, payload?.message || '请求未完成，请稍后重试。', payload?.requestId, payload?.code)
  return payload.data as T
}
export function post<T>(path: string, body: unknown, key: string = crypto.randomUUID()): Promise<T> {
  return request<T>(path, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body) })
}

export async function download(path: string, fallbackName: string): Promise<void> {
  const response = await authorizedFetch(path)
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.message || '文件下载失败，请稍后重试。', payload?.requestId, payload?.code)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  let fileName = fallbackName
  try { fileName = encoded ? decodeURIComponent(encoded) : plain || fallbackName } catch { fileName = fallbackName }
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = fileName; anchor.style.display = 'none'
  document.body.appendChild(anchor); anchor.click(); anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
