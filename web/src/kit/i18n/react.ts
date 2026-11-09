// 识律家族共享壳 · i18n 的 React 绑定（供宿主替换 react-i18next）
//
// 对外形状刻意与 `useTranslation()` 兼容：宿主迁移时只改 import 与解构那一行，
// 303 处 `t('...')` 调用点一个都不用动——减少"迁移本身引入的 bug"。
import { useCallback, useSyncExternalStore } from 'react'
import type { I18n, Locale, TParams } from './index'

export interface UseI18nResult<T> {
  t: (path: string, params?: TParams) => string
  /** 与 i18next 的 `i18n.language` 同形，便于宿主平滑替换 */
  i18n: {
    language: Locale
    changeLanguage: (next: Locale) => void
  }
  messages: T
  raw: (path: string) => unknown
}

export function useI18n<T>(store: I18n<T>): UseI18nResult<T> {
  const language = useSyncExternalStore(
    (cb) => store.subscribe(cb),
    () => store.locale(),
    () => store.locale(),
  )
  const t = useCallback(
    (path: string, params?: TParams) => store.t(path, params),
    [store, language],
  )
  return {
    t,
    i18n: {
      language,
      changeLanguage: (next: Locale) => store.setLocale(next),
    },
    messages: store.messages(),
    raw: (path: string) => store.raw(path),
  }
}
