// 站点接待副驾（openspec: line-reception-copilot「宿主以一行 loader 接入」）。
//
// 一行 loader 完成全部协议：宿主只声明页面上下文与允许的导航动作，postMessage
// 握手、身份递送、意图分派都在 `copilot.js` 里——宿主写零协议代码。
//
// 未绑定 / 已暂停 / 未开放时 loader 自己零注入，页面不留死卡。所以这个组件
// 挂上去永远安全：最差的结果是没有副驾，绝不是坏掉的按钮。
//
// `VITE_COPILOT_MOUNT=off` 可独立撤下挂载而不必改绑定记录（spec「挂载与绑定
// 分离」）：撤挂载与解绑是两条独立的回滚路径。

import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

export interface SiteCopilotProps {
  /** 该站点在线副驾绑定表里的线 id（如 'zhesi'） */
  line: string
  /** 页面上下文里的线名，展示给 agent 看（如 '哲思'） */
  lineName: string
  /** 允许副驾执行的站内导航目标（前缀匹配）；设为空数组即不给导航动作 */
  navTargets?: readonly string[]
  /** 萬星 origin；宿主可经 VITE_WANXING_ORIGIN 覆盖 */
  origin?: string
  /** 首屏是否展开（缺省收起：只留 48px 圆钮） */
  defaultOpen?: boolean
}

type CopilotApi = {
  context?: () => Record<string, unknown>
  intents?: Record<string, (arg: unknown) => unknown>
  pushContext?: () => void
  __loaderMounted?: boolean
}

/** 站内导航白名单：只接受站内路径前缀或页内锚点。 */
function allowedTarget(to: string, targets: readonly string[]): boolean {
  if (to.startsWith('#') && !to.startsWith('//')) return true
  if (!to.startsWith('/') || to.startsWith('//')) return false
  return targets.some((t) => to === t || to.startsWith(`${t}/`) || to.startsWith(`${t}#`))
}

export function SiteCopilot({
  line,
  lineName,
  navTargets = [],
  origin,
  defaultOpen = false,
}: SiteCopilotProps) {
  const navigate = useNavigate()
  const location = useLocation()
  // 惰性求值：模块加载期读 import.meta.env 在测试环境里会炸。
  const wanxingOrigin =
    origin ||
    String((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_WANXING_ORIGIN ?? '').trim() ||
    'https://wanxing.finddatatech.cloud'

  // 钩子每次渲染刷新：navigate 闭包要跟住路由器实例，上下文要跟住当前路由。
  useEffect(() => {
    const api: CopilotApi = ((window as unknown as { WanxingCopilot?: CopilotApi }).WanxingCopilot ??= {})
    api.context = () => ({ line: lineName, page: location.pathname + location.hash })
    if (navTargets.length > 0) {
      api.intents = {
        navigate: (arg: unknown) => {
          const to = String(arg ?? '')
          if (!allowedTarget(to, navTargets)) {
            throw new Error(`not allowed: navigate 只接受站内路径或锚点（${navTargets.join(' ')}）`)
          }
          if (to.startsWith('#')) {
            window.location.hash = to
            return { message: `已跳转到 ${to}` }
          }
          navigate(to)
          return { message: `已导航到 ${to}` }
        },
      }
    }
    api.pushContext?.()
  }, [navigate, location.pathname, location.hash, lineName, navTargets])

  useEffect(() => {
    // 挂载侧开关（spec「挂载与绑定分离」）：置 'off' 即撤下本站副驾，不动绑定。
    const env = (import.meta as unknown as { env?: Record<string, string> }).env ?? {}
    if (String(env.VITE_COPILOT_MOUNT ?? '').toLowerCase() === 'off') return

    const api: CopilotApi = ((window as unknown as { WanxingCopilot?: CopilotApi }).WanxingCopilot ??= {})
    // 一个页面只挂一个副驾：布局重渲染 / StrictMode 双挂载都不留第二份。
    if (document.querySelector('iframe[data-wanxing-copilot]')) return
    if (document.querySelector(`script[data-line="${line}"]`)) return

    const script = document.createElement('script')
    script.src = `${wanxingOrigin}/copilot.js`
    script.async = true
    script.setAttribute('data-line', line)
    script.setAttribute('data-open', defaultOpen ? '1' : '0')
    document.head.appendChild(script)

    return () => {
      document.querySelector('iframe[data-wanxing-copilot]')?.remove()
      script.remove()
      api.__loaderMounted = false
      delete (window as unknown as { WanxingCopilot?: CopilotApi }).WanxingCopilot
    }
  }, [line, wanxingOrigin, defaultOpen])

  return null // widget 由 loader 注入，React 不渲染任何节点
}
