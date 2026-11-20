// 站点页脚（门面家具 spec：产品站档最低件 = 品牌名 + 一句定位 + 回官网入口 + 双备案号）。
// 四个宿主共用同一份实现（web-shell-kit「壳以源码随宿主出货」），品牌名与定位经 props 注入。
import type { ReactNode } from 'react'

const ICP = { label: '粤ICP备2026118740号-1', href: 'https://beian.miit.gov.cn/' }
const MPS = {
  label: '粤公网安备44030002016558号',
  href: 'https://beian.mps.gov.cn/#/query/webSearch?code=44030002016558',
}

export interface SiteFooterProps {
  brand: string
  tagline: string
  /** 兄弟站或回官网入口；不传则不渲染该行 */
  links?: { href: string; label: string }[]
}

export function SiteFooter({ brand, tagline, links = [] }: SiteFooterProps): ReactNode {
  return (
    <footer
      data-testid="site-footer"
      className="mt-12 border-t border-neutral-200 px-6 py-8 text-xs text-neutral-500"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium text-neutral-700">{brand}</span>
        <span>·</span>
        <span>{tagline}</span>
      </div>
      {links.length > 0 && (
        <nav className="mt-2 flex flex-wrap gap-x-4 gap-y-1" aria-label="页脚导航">
          {links.map((l) => (
            <a key={l.href} href={l.href} className="hover:text-neutral-800">
              {l.label}
            </a>
          ))}
        </nav>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        <a href={ICP.href} target="_blank" rel="noopener noreferrer" className="hover:text-neutral-800">
          {ICP.label}
        </a>
        <a href={MPS.href} target="_blank" rel="noopener noreferrer" className="hover:text-neutral-800">
          {MPS.label}
        </a>
      </div>
    </footer>
  )
}
