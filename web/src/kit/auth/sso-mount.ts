// 宿主的静默 SSO 挂载点（web-shell-kit「同租户静默单点登录」的宿主侧）。
//
// 一段逻辑要写对两个判断，所以只该有一份实现：
//   ① 本机是不是带着回跳参数落地（code / error）——是就收口，不是就看要不要发起；
//   ② 要不要为这个访客发起一次 `prompt=none`（整页跳转）——只有「本浏览器在本租户
//      登录过」才值得，否则每个首次访客白跳两趟。
//
// 宿主只需要给三样东西：auth 实例、怎么读/写宿主自己的 token 槽、提示 cookie 的域。

import { ssoHintMark, ssoHintSeen } from './sso-hint'

export type SsoOutcome =
  | { outcome: 'logged-in'; token: string }
  | { outcome: 'interactive-required' }
  /** 真实故障（网络 / 上游 / 配置）：调用方 SHALL 呈现可重试错误，MUST NOT
   *  渲染成「未登录」——那会让用户去点一次注定失败的登录。 */
  | { outcome: 'error'; error: unknown }

export interface SsoMountOptions {
  /** 共享壳的 auth 实例（`createAuth(...)` 的返回值） */
  auth: {
    trySilentLogin(): Promise<'logged-in' | 'interactive-required'>
    beginSilentLogin(): Promise<void>
    completeLogin(): Promise<{ ok: boolean; returnTo?: string }>
    loadSession(): { idToken: string } | null
  }
  /** 宿主的 token 槽（写宿主自己的读取键，让页面组件能感知） */
  setToken: (token: string) => void
  /** 宿主是否已有会话（有就不打扰） */
  hasToken: () => boolean
  /** 提示 cookie 的作用域，如 '.finddatatech.cloud'；本地开发传 undefined */
  hintDomain?: string
  /** 回跳成功后的附带动作（如刷新本地 React 态）；可选 */
  onLoggedIn?: (token: string) => void
  /** 浏览器环境（测试注入） */
  location?: { href: string; search: string }
  history?: { replaceState: (d: unknown, t: string, url: string) => void }
}

/** 收口回跳或发起一次静默尝试；返回的 outcome 让调用方能区分三种结局。 */
export async function runSsoOnMount(o: SsoMountOptions): Promise<SsoOutcome> {
  const loc = o.location ?? (typeof window !== 'undefined' ? window.location : null)
  if (!loc) return { outcome: 'interactive-required' }
  const hasCallback = /[?&](code|error)=/.test(loc.search)

  const commit = (token: string) => {
    o.setToken(token)
    ssoHintMark(o.hintDomain)
    o.onLoggedIn?.(token)
  }

  if (hasCallback) {
    // 有 code：交互式或被静默带回来的，走同一条交换路径。
    // 交换失败不等于「没登录」——凭据被拒/网络故障要如实上抛（spec 3.6）。
    try {
      const result = await o.auth.completeLogin()
      if (result.ok) {
        const token = o.auth.loadSession()?.idToken
        if (token) {
          commit(token)
          return { outcome: 'logged-in', token }
        }
      }
    } catch (error) {
      return { outcome: 'error', error }
    }
    // 没有 code = 静默尝试被拒（error=login_required）：无副作用地降级；
    // 其他错误（unauthorized_client / 上游故障）由壳抛出，这里如实上报。
    try {
      const outcome = await o.auth.trySilentLogin()
      if (outcome === 'logged-in') {
        const token = o.auth.loadSession()?.idToken
        if (token) {
          commit(token)
          return { outcome: 'logged-in', token }
        }
      }
    } catch (error) {
      return { outcome: 'error', error }
    }
    return { outcome: 'interactive-required' }
  }

  if (o.hasToken()) return { outcome: 'interactive-required' }
  if (!ssoHintSeen(o.hintDomain)) return { outcome: 'interactive-required' }
  // 发起即整页跳走；跳不出去（配置缺失/网络拒绝）是真实故障。
  try {
    await o.auth.beginSilentLogin()
  } catch (error) {
    return { outcome: 'error', error }
  }
  return { outcome: 'interactive-required' }
}
