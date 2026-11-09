// 识律家族共享壳 · 认证（spec web-shell-kit「认证实现唯一」）
//
// 从 fd-lex/web/src/console/auth.ts 抽出（change lex-web-shell-convergence 2.1）。
// 相对原实现的三处变化，全部是"把宿主差异变成参数"：
//   1. 不再是模块单例——`createAuth(options)` 产出一个实例，宿主可并存多套；
//   2. 三个硬编码消失：config 端点、回跳地址、存储键前缀都由宿主传入；
//   3. 网络与跳转可注入（`fetchImpl` / `assign` / `now`），单测不需要真起浏览器。
//
// 纪律：本文件 MUST NOT 引入任何宿主模块（含路由库）；它是纯 TypeScript。

export interface AuthConfig {
  configured: boolean
  issuer: string
  client_id: string
  /** 可选 API resource（部分宿主不需要，如 fd-wire） */
  resource?: string
  scopes: string[]
  organization_required?: boolean
  missing: string[]
}

export interface AuthSession {
  idToken: string
  accessToken?: string
  refreshToken?: string
  /** 过期时刻（ms epoch，取 ID/access 较早者） */
  expiresAt: number
  identity: string
  email?: string
  name?: string
  roles?: string[]
  organizations?: string[]
}

export class AuthError extends Error {
  readonly status: number | undefined
  readonly detail: string | undefined
  /** `invalid`=凭据失效（须重新登录）；`transient`=可重试（保留会话） */
  readonly kind: 'invalid' | 'transient' | 'config'

  constructor(kind: AuthError['kind'], message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'AuthError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }
}

export interface AuthOptions {
  /** 配置来源：给 fetchConfig 则优先；否则用 configUrl 拉取 */
  configUrl?: string
  fetchConfig?: () => Promise<AuthConfig>
  /** 宿主回跳地址（如 `${origin}/console/callback`、`${origin}/workbench`） */
  redirectUri: string
  /** 存储键前缀，如 'lex.console' → 'lex.console.session' / '.pkce' */
  storagePrefix: string
  /** 令牌落哪：session=关标签即失效（推荐）；local=跨标签保留 */
  tokenStorage?: 'session' | 'local'
  /** 过期前多少毫秒开始视为"该续期" */
  expirySkewMs?: number
  /** 是否携带 OIDC nonce（缺省 true；某些 IdP 应用不需要可关） */
  useNonce?: boolean
  /** 登录完成后的回跳路径（缺省由宿主在 completeLogin 后用 state.returnTo 决定） */
  defaultReturnTo?: string
  // ---- 测试接缝（生产留空） ----
  now?: () => number
  fetchImpl?: typeof fetch
  assign?: (url: string) => void
}

export interface Auth {
  config(): Promise<AuthConfig>
  /** 未配置时抛 AuthError('config')，不发起任何跳转 */
  beginLogin(): Promise<void>
  /** 用授权码换令牌（低层原语：state/nonce 校验与跳转清理由调用方决定）。
   *  供需要自有契约的宿主复用——它只做 exchange，不改 window、不落存储。 */
  exchangeCode(code: string, verifier: string): Promise<AuthSession>
  /** 处理回跳；非回跳（无 code）返回 false；state 不符也返回 false。
   *  成功时返回 { ok, returnTo }，宿主据此决定落到哪个页面。 */
  completeLogin(): Promise<{ ok: boolean; returnTo?: string }>
  loadSession(): AuthSession | null
  saveSession(session: AuthSession): void
  clearSession(): void
  isExpired(session: AuthSession): boolean
  /** 到期前续期。成功返回新会话；凭据失效抛 AuthError('invalid')；
   *  网络/上游故障抛 AuthError('transient')（调用方应保留会话、可重试）。 */
  refresh(session: AuthSession): Promise<AuthSession>
  /** 受保护请求前调用：必要时先续期；无法续期则抛 AuthError('invalid') */
  ensureFresh(): Promise<AuthSession | null>
  logoutLocal(): void
  decodeClaims(token: string): Record<string, unknown>
}

const b64url = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')

async function sha256B64Url(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
  return b64url(new Uint8Array(digest))
}

function randomString(len = 48): string {
  const bytes = new Uint8Array(len)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(36).padStart(2, '0')).join('').slice(0, 64)
}

function claimsOf(token: string): Record<string, unknown> {
  try {
    const part = token.split('.')[1]
    if (!part) return {}
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const parsed = JSON.parse(json)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

export function createAuth(options: AuthOptions): Auth {
  const {
    configUrl,
    fetchConfig,
    redirectUri,
    storagePrefix,
    tokenStorage = 'session',
    expirySkewMs = 60_000,
    useNonce = true,
    defaultReturnTo,
    now = () => Date.now(),
    fetchImpl, // 缺省时每次调用再解析（见 needFetch）：构造期绑定会让测试替身/运行时替换失效
    assign = (url: string) => {
      if (typeof window !== 'undefined') window.location.assign(url)
    },
  } = options

  const SESSION_KEY = `${storagePrefix}.session`
  const PKCE_KEY = `${storagePrefix}.pkce`

  interface PkceState {
    verifier: string
    state: string
    nonce?: string
    returnTo?: string
  }

  const loadPkce = (): PkceState | null => {
    const raw = store()?.getItem(PKCE_KEY)
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === "object" ? (parsed as PkceState) : null
    } catch {
      return null
    }
  }
  const savePkce = (value: PkceState): void => {
    store()?.setItem(PKCE_KEY, JSON.stringify(value))
  }

  const store = (): Storage | null => {
    if (typeof window === 'undefined') return null
    return tokenStorage === 'local' ? window.localStorage : window.sessionStorage
  }

  const needFetch = (): typeof fetch => {
    // 每次调用再解析：既尊重宿主的显式注入，也支持运行时替换（含测试替身）
    const impl = fetchImpl ?? (typeof fetch === 'function' ? fetch : undefined)
    if (!impl) throw new AuthError('config', 'auth.fetch_unavailable')
    return impl
  }

  function loadSession(): AuthSession | null {
    const raw = store()?.getItem(SESSION_KEY)
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as AuthSession) : null
    } catch {
      return null
    }
  }

  function saveSession(session: AuthSession): void {
    store()?.setItem(SESSION_KEY, JSON.stringify(session))
  }

  function clearSession(): void {
    store()?.removeItem(SESSION_KEY)
  }

  function isExpired(session: AuthSession): boolean {
    return !session.expiresAt || session.expiresAt - expirySkewMs <= now()
  }

  function sessionFromTokens(payload: Record<string, unknown>, fallbackRefresh?: string): AuthSession {
    const idToken = String(payload.id_token ?? '')
    const accessToken = payload.access_token ? String(payload.access_token) : undefined
    const refreshToken = payload.refresh_token ? String(payload.refresh_token) : fallbackRefresh
    const claims = claimsOf(idToken)
    const expSeconds = Number(claims.exp ?? 0)
    return {
      idToken,
      accessToken,
      refreshToken,
      expiresAt: expSeconds ? expSeconds * 1000 : now() + 3600_000,
      // 身份口径与原实现一致：username → email → sub。
      // 控制台与结算侧的历史口径把「登录名」当客户身份键（见 MCP-REGISTRY
      // 「MAP 键 = 控制台登录名」），改成 email 优先会让既有客户对不上账。
      identity: String(claims.username ?? claims.email ?? claims.sub ?? ''),
      email: typeof claims.email === 'string' ? claims.email : undefined,
      name: typeof claims.name === 'string' ? claims.name : undefined,
      roles: Array.isArray(claims.roles) ? (claims.roles as string[]) : undefined,
      organizations: Array.isArray(claims.organizations)
        ? (claims.organizations as string[])
        : undefined,
    }
  }

  async function tokenRequest(config: AuthConfig, body: URLSearchParams) {
    if (!config.configured) {
      throw new AuthError('config', 'auth.not_configured', undefined, config.missing.join(', '))
    }
    let resp: Response
    try {
      resp = await needFetch()(`${config.issuer}/oidc/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })
    } catch (err) {
      // 网络层失败 = 可重试，不是凭据失效
      throw new AuthError('transient', 'auth.issuer_unreachable', undefined, String(err))
    }
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      // 400/401 = 授权码或刷新令牌被拒 = 凭据失效
      if (resp.status === 400 || resp.status === 401) {
        throw new AuthError('invalid', 'auth.credentials_rejected', resp.status, detail.slice(0, 300))
      }
      throw new AuthError('transient', 'auth.issuer_error', resp.status, detail.slice(0, 300))
    }
    return (await resp.json()) as Record<string, unknown>
  }

  async function resolveConfig(): Promise<AuthConfig> {
    if (fetchConfig) return fetchConfig()
    if (!configUrl) throw new AuthError('config', 'auth.config_source_missing')
    let resp: Response
    try {
      resp = await needFetch()(configUrl)
    } catch (err) {
      throw new AuthError('transient', 'auth.config_unreachable', undefined, String(err))
    }
    if (!resp.ok) {
      throw new AuthError('transient', 'auth.config_unreadable', resp.status)
    }
    return (await resp.json()) as AuthConfig
  }

  async function exchangeCode(code: string, verifier: string): Promise<AuthSession> {
    const config = await resolveConfig()
    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri,
      client_id: config.client_id,
      code_verifier: verifier,
    })
    if (config.resource) body.set('resource', config.resource)
    const tokens = await tokenRequest(config, body)
    if (!tokens.id_token) {
      throw new AuthError('invalid', 'auth.no_id_token')
    }
    return sessionFromTokens(tokens)
  }

  return {
    config: resolveConfig,

    async beginLogin(): Promise<void> {
      const config = await resolveConfig()
      if (!config.configured) {
        // 如实阻塞：不跳转、不假登录
        throw new AuthError(
          'config',
          'auth.not_configured',
          undefined,
          config.missing.join(', '),
        )
      }
      const verifier = randomString(48)
      const state = randomString(16)
      const nonce = useNonce ? randomString(16) : undefined
      savePkce({ verifier, state, nonce, returnTo: defaultReturnTo })
      const params = new URLSearchParams({
        client_id: config.client_id,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: config.scopes.join(' '),
        state,
        code_challenge: await sha256B64Url(verifier),
        code_challenge_method: 'S256',
      })
      if (nonce) params.set('nonce', nonce)
      if (config.resource) params.set('resource', config.resource)
      assign(`${config.issuer}/oidc/auth?${params.toString()}`)
    },

    async completeLogin(): Promise<{ ok: boolean; returnTo?: string }> {
      if (typeof window === 'undefined') return { ok: false }
      const url = new URL(window.location.href)
      const code = url.searchParams.get('code')
      const state = url.searchParams.get('state')
      if (!code) return { ok: false }
      const pkce = loadPkce()
      if (!state || !pkce || state !== pkce.state) {
        url.searchParams.delete('code')
        url.searchParams.delete('state')
        window.history.replaceState({}, '', url.pathname)
        return { ok: false }
      }
      const verifier = pkce.verifier
      // nonce 校验：发起时带了就要求回执里有且相等（防重放）
      const session = await exchangeCode(code, verifier)
      if (pkce.nonce) {
        const claims = claimsOf(session.idToken)
        if (claims.nonce !== undefined && claims.nonce !== pkce.nonce) {
          url.searchParams.delete('code')
          url.searchParams.delete('state')
          window.history.replaceState({}, '', url.pathname)
          store()?.removeItem(PKCE_KEY)
          return { ok: false }
        }
      }
      url.searchParams.delete('code')
      url.searchParams.delete('state')
      window.history.replaceState({}, '', url.pathname)
      store()?.removeItem(PKCE_KEY)
      saveSession(session)
      return { ok: true, returnTo: pkce.returnTo }
    },

    exchangeCode,

    loadSession,
    saveSession,
    clearSession,
    isExpired,

    async refresh(session: AuthSession): Promise<AuthSession> {
      if (!session.refreshToken) {
        throw new AuthError('invalid', 'auth.no_refresh_token')
      }
      const config = await resolveConfig()
      const body = new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: session.refreshToken,
        client_id: config.client_id,
      })
      if (config.resource) body.set('resource', config.resource)
      // tokenRequest 已把 400/401 归为 invalid、网络/5xx 归为 transient；
      // 这里**不清会话**——transient 时用户仍在登录态，清掉等于替他登出。
      const tokens = await tokenRequest(config, body)
      const next = sessionFromTokens(tokens, session.refreshToken)
      saveSession(next)
      return next
    },

    async ensureFresh(): Promise<AuthSession | null> {
      const session = loadSession()
      if (!session) return null
      if (!isExpired(session)) return session
      return this.refresh(session)
    },

    logoutLocal(): void {
      clearSession()
    },

    decodeClaims: claimsOf,
  }
}

export const __test__ = { randomString, sha256B64Url, claimsOf }
