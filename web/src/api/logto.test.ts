// 哲思登录哨兵（change lex-web-shell-convergence 6.3）。
//
// 这份登录原先与实论同源、只有 code→id_token，**没有 refresh**。
// 本文件守三件事：静默续期、issuer 不得拼出双 /oidc、audience 兼容
// （未配 resource 时带 aud 的令牌不被拒——该坑本仓线上踩过 InvalidAudienceError）。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { currentToken, ensureFreshToken, handleCallback, isLoggedIn, login, logout } from './logto'

function b64url(o: Record<string, unknown>): string {
  return btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function idToken(expSeconds = Math.floor(Date.now() / 1000) + 3600, extra: Record<string, unknown> = {}): string {
  return `${b64url({ alg: 'ES384' })}.${b64url({ sub: 'u-1', exp: expSeconds, ...extra })}.sig`
}

function makeStorage() {
  const map = new Map<string, string>()
  return {
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => void map.set(k, String(v)),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  }
}

let sessionStore: ReturnType<typeof makeStorage>
let localStore: ReturnType<typeof makeStorage>
let assigned: string[] = []

function installWindow(href = 'https://zhesi.test/workbench') {
  sessionStore = makeStorage()
  localStore = makeStorage()
  assigned = []
  const g = globalThis as unknown as Record<string, unknown>
  g.window = {
    location: {
      origin: 'https://zhesi.test',
      href,
      assign: (url: string) => assigned.push(url),
    },
    sessionStorage: sessionStore,
    localStorage: localStore,
    history: { replaceState: () => {} },
  }
  // client.ts 读全局 localStorage，壳读 window.sessionStorage——同一份桩
  g.localStorage = localStore
  g.sessionStorage = sessionStore
}

beforeEach(() => {
  installWindow()
})

afterEach(() => {
  const g = globalThis as unknown as Record<string, unknown>
  delete g.window
  delete g.localStorage
  delete g.sessionStorage
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('哲思登录', () => {
  it('未登录时 currentToken 为空', () => {
    expect(currentToken()).toBeNull()
    expect(isLoggedIn()).toBe(false)
  })

  it('回跳成功把 token 同步给 client 的读取键', async () => {
    installWindow('https://zhesi.test/workbench?code=c&state=s-1')
    sessionStore.setItem('zhesi.pkce', JSON.stringify({ verifier: 'v-1', state: 's-1' }))
    const token = idToken()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ id_token: token }) }) as Response),
    )
    expect(await handleCallback()).toBe(true)
    expect(currentToken()).toBe(token)
    expect(localStore.getItem('zhesi_token')).toBe(token)
  })

  it('登录跳转的授权端点不含双 /oidc（issuer 必须是基地址）', async () => {
    await login()
    expect(assigned).toHaveLength(1)
    expect(assigned[0].startsWith('https://auth.finddatatech.cloud/oidc/auth?')).toBe(true)
    expect(assigned[0]).not.toContain('/oidc/oidc')
  })

  it('静默续期：过期会话用 refresh token 换新', async () => {
    sessionStore.setItem(
      'zhesi.session',
      JSON.stringify({
        idToken: idToken(Math.floor(Date.now() / 1000) - 60),
        refreshToken: 'refresh-1',
        expiresAt: Date.now() - 60_000,
        identity: 'u-1',
      }),
    )
    const fresh = idToken()
    const bodies: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
        bodies.push(String(init?.body ?? ''))
        return { ok: true, status: 200, json: async () => ({ id_token: fresh, refresh_token: 'r2' }) } as Response
      }),
    )
    expect(await ensureFreshToken()).toBe(fresh)
    expect(bodies[0]).toContain('grant_type=refresh_token')
    expect(localStore.getItem('zhesi_token')).toBe(fresh)
  })

  it('audience 兼容：未配 resource 时带 aud 的令牌不被拒（线上踩过 InvalidAudienceError）', async () => {
    installWindow('https://zhesi.test/workbench?code=c&state=s-2')
    sessionStore.setItem('zhesi.pkce', JSON.stringify({ verifier: 'v', state: 's-2' }))
    const token = idToken(undefined, { aud: 'some-audience' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ id_token: token }) }) as Response),
    )
    expect(await handleCallback()).toBe(true)
    expect(currentToken()).toBe(token)
  })

  it('登录全链：登录 → 受保护请求带 Bearer → 续期 → 重放 → 退出后不可达', async () => {
    await login()
    expect(assigned[0]).toContain('https://auth.finddatatech.cloud/oidc/auth?')
    const pkceRaw = sessionStore.getItem('zhesi.pkce')
    expect(pkceRaw).toBeTruthy()
    const pkce = JSON.parse(pkceRaw as string)

    const shortExp = Math.floor(Date.now() / 1000) + 5
    installWindow('https://zhesi.test/workbench')
    sessionStore.setItem('zhesi.pkce', pkceRaw as string)
    ;(globalThis as unknown as { window: { location: { href: string } } }).window.location.href =
      `https://zhesi.test/workbench?code=c-1&state=${pkce.state}`

    const seenAuth: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url)
        if (u.includes('/oidc/token')) {
          const body = String(init?.body ?? '')
          const isRefresh = body.includes('grant_type=refresh_token')
          return {
            ok: true,
            status: 200,
            json: async () =>
              isRefresh
                ? { id_token: idToken(Math.floor(Date.now() / 1000) + 3600), refresh_token: 'r-2' }
                : { id_token: idToken(shortExp), refresh_token: 'r-1' },
          } as Response
        }
        seenAuth.push(String(new Headers(init?.headers).get('Authorization')))
        if (seenAuth.length === 1) return new Response('expired', { status: 401 })
        return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
      }),
    )

    expect(await handleCallback()).toBe(true)

    const { api } = await import('./client')
    await api.project()
    expect(seenAuth.length).toBe(2)
    expect(seenAuth[1]).not.toBe(seenAuth[0])

    logout()
    expect(currentToken()).toBeNull()
    expect(localStore.getItem('zhesi_token')).toBeNull()
  })

  it('登出跳 Logto session/end 并清本地 token', () => {
    localStore.setItem('zhesi_token', 'x')
    logout()
    expect(assigned).toHaveLength(1)
    expect(assigned[0]).toContain('/oidc/session/end?')
    expect(localStore.getItem('zhesi_token')).toBeNull()
  })
})
