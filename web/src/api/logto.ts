// 哲思（zhesi）登录：内核换成共享壳（change lex-web-shell-convergence 6.3）。
//
// 原先这份是从实论（fd-shilun）同源的 103 行残版：只有 code→id_token，
// **没有 refresh**——会话一过期就得重新登录。切到壳后获得静默续期。
//
// 对外形状保持不变（currentToken / isLoggedIn / login / handleCallback / logout），
// 所以 App.tsx 与 client.ts 的调用点不动。
//
// 两个本仓特有的点必须保留：
// 1. issuer 传**基地址**（不含 /oidc）：壳拼 `${issuer}/oidc/auth`，传完整
//    issuer 会拼出 /oidc/oidc/auth（实论侧已踩过并被回归用例抓住）。
// 2. 登出仍跳 Logto 的 `/session/end`（壳的 logoutLocal 只清本地会话）。
import { createAuth } from '../kit/auth/index'
import { setToken } from './client'

const ISSUER_BASE = 'https://auth.finddatatech.cloud'
const CLIENT_ID = '8l4ogqpoino6uwvlri5wa' // Logto: zhesi-workbench（SPA）
const SCOPE = 'openid profile offline_access'

/** 惰性构造：回跳地址依赖 window.location.origin，模块加载期读它会让本文件在 node 下抛。 */
let instance: ReturnType<typeof createAuth> | null = null
function auth() {
  if (!instance) {
    instance = createAuth({
      fetchConfig: async () => ({
        configured: true,
        issuer: ISSUER_BASE,
        client_id: CLIENT_ID,
        scopes: SCOPE.split(' '),
        organization_required: false,
        missing: [],
      }),
      redirectUri: `${window.location.origin}/workbench`,
      storagePrefix: 'zhesi',
      tokenStorage: 'session',
    })
  }
  return instance
}

export function currentToken(): string | null {
  return auth().loadSession()?.idToken ?? null
}

export function isLoggedIn(): boolean {
  return Boolean(currentToken())
}

export async function login(): Promise<void> {
  await auth().beginLogin()
}

export async function handleCallback(): Promise<boolean> {
  try {
    const result = await auth().completeLogin()
    if (!result.ok) return false
    const token = auth().loadSession()?.idToken
    if (token) setToken(token)
    return Boolean(token)
  } catch {
    return false
  }
}

/**
 * 静默续期：受保护请求前调用；续不上返回 null（调用方按需重新登录）。
 */
export async function ensureFreshToken(): Promise<string | null> {
  try {
    const session = await auth().ensureFresh()
    if (!session) return null
    setToken(session.idToken)
    return session.idToken
  } catch {
    return null
  }
}

/** 登出：清本地会话后跳 Logto 的 session/end（该跳转是本仓既有行为）。 */
export function logout(): void {
  auth().logoutLocal()
  setToken('')
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    post_logout_redirect_uri: `${window.location.origin}/`,
  })
  window.location.assign(`${ISSUER_BASE}/oidc/session/end?${params}`)
}
