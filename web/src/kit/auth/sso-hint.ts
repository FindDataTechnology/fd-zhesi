// 跨站登录提示（web-shell-kit「同租户静默单点登录」的配套件）。
//
// 为什么需要它：`prompt=none` 是**整页跳转**（auth 域带 X-Frame-Options: SAMEORIGIN，
// iframe 静默不可行）。没有提示就发起的后果是：每个首次访客都要白跳两趟才看到登录入口。
// 提示的语义只有一个——「本浏览器在这个租户登录过」，不含任何身份信息。
//
// 为什么是**注册域 cookie**而不是 localStorage：localStorage 按源隔离，实论记不到
// 「你在柏讯登录过」。同一注册域下的 cookie 是唯一跨子域可见的非服务端状态。
// domain 参数由宿主传入（生产 `.finddatatech.cloud`；本地不传 = 只作用于当前源）。

const NAME = 'fd_sso_hint'
const MAX_AGE = 60 * 60 * 24 * 180

export function ssoHintSeen(domain?: string): boolean {
  if (typeof document === 'undefined') return false
  void domain // cookie 可见性由浏览器按域决定；读时不需要（也不该）指定域
  return document.cookie.split('; ').some((c) => c.startsWith(`${NAME}=1`))
}

export function ssoHintMark(domain?: string): void {
  if (typeof document === 'undefined') return
  const scope = domain ? `domain=${domain}; ` : ''
  document.cookie = `${NAME}=1; ${scope}path=/; max-age=${MAX_AGE}; samesite=lax`
}

export function ssoHintClear(domain?: string): void {
  if (typeof document === 'undefined') return
  const scope = domain ? `domain=${domain}; ` : ''
  document.cookie = `${NAME}=; ${scope}path=/; max-age=0; samesite=lax`
}
