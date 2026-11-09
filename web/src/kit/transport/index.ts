// 识律家族共享壳 · 传输层（spec web-shell-kit「登录态可静默续期」/「未配置时如实阻塞」）
//
// 宿主只注入三件事：baseUrl、取令牌、以及"续不过去时怎么办"。
// 这里统一处理 401：先尝试一次续期再重放；二次 401 上抛，绝不无限重试。
//
// 纪律：MUST NOT 把令牌写进日志或错误对象；本文件不 import 任何路由库。

export interface TransportOptions {
  /** 如 '/api' 或 'https://lex.example/api' */
  baseUrl: string
  /** 每次请求取当前令牌（可返回 null＝未登录） */
  getToken: () => string | null | Promise<string | null>
  /** 401 时调用；返回 true 表示已续期，可重放一次 */
  onUnauthorized?: () => Promise<boolean>
  /** 超时（毫秒），缺省 20s */
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

export interface Transport {
  request<T = unknown>(path: string, init?: RequestInit): Promise<T>
  get<T = unknown>(path: string, init?: RequestInit): Promise<T>
  post<T = unknown>(path: string, body?: unknown, init?: RequestInit): Promise<T>
}

export class TransportError extends Error {
  readonly status: number | undefined
  readonly detail: string | undefined
  constructor(message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'TransportError'
    this.status = status
    this.detail = detail
  }
}

/** 从任意对象里剥掉疑似令牌的字段，保证错误对象不携带凭据。 */
export function redact(value: unknown): unknown {
  if (typeof value === 'string') {
    return value.replace(/\b(?:Bearer\s+)?[A-Za-z0-9._-]{20,}\b/g, '<redacted>')
  }
  if (Array.isArray(value)) return value.map(redact)
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = /token|authorization|secret|password/i.test(k) ? '<redacted>' : redact(v)
    }
    return out
  }
  return value
}

export function createTransport(options: TransportOptions): Transport {
  const { baseUrl, getToken, onUnauthorized, timeoutMs = 20_000 } = options
  // 同 auth：每次调用再解析，避免构造期绑定让测试替身/运行时替换失效
  const resolveFetch = () =>
    options.fetchImpl ?? (typeof fetch === 'function' ? fetch : undefined)
  const base = baseUrl.replace(/\/$/, '')

  async function once(path: string, init: RequestInit, token: string | null): Promise<Response> {
    const doFetch = resolveFetch()
    if (!doFetch) throw new TransportError('transport.fetch_unavailable')
    const headers = new Headers(init.headers ?? {})
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (init.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await doFetch(`${base}${path.startsWith('/') ? path : `/${path}`}`, {
        ...init,
        headers,
        signal: init.signal ?? controller.signal,
      })
    } catch (err) {
      throw new TransportError('transport.request_failed', undefined, redact(String(err)) as string)
    } finally {
      clearTimeout(timer)
    }
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await getToken()
    let resp = await once(path, init, token)
    if (resp.status === 401 && onUnauthorized) {
      const renewed = await onUnauthorized()
      if (renewed) {
        resp = await once(path, init, await getToken())
      }
    }
    if (resp.status === 401) {
      throw new TransportError('transport.unauthenticated', 401, redact(await resp.text().catch(() => '')) as string)
    }
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      throw new TransportError(`transport.http_${resp.status}`, resp.status, (redact(detail) as string).slice(0, 500))
    }
    if (resp.status === 204) return undefined as T
    const text = await resp.text()
    if (!text) return undefined as T
    try {
      return JSON.parse(text) as T
    } catch {
      return text as unknown as T
    }
  }

  return {
    request,
    get: (path, init) => request(path, { ...init, method: 'GET' }),
    post: (path, body, init) =>
      request(path, {
        ...init,
        method: 'POST',
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
  }
}
