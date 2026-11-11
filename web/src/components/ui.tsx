/** 工作台共用小部件：状态徽标、降级/错误/加载盒、分节标题。
 *
 *  状态类控件（加载/错误/空态、稳定性徽标）自 2026-11-10 起改由共享壳原语实现
 *  （`src/kit/primitives`，change lex-web-shell-convergence 5.3）。本文件保留同名导出，
 *  调用点零改动；**视觉不变**——尺寸/间距/字重/配色仍用本宿主原来的类名，
 *  经 `className` / `toneClassName` 原样传给原语。
 *
 *  `DegradeBox` 刻意不并入原语：它不是通用错误态，而是"诚实降级契约"的呈现
 *  （问辩谱未接线），换成通用 ErrorState 会丢语义。
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Stability } from "../api/client";
import { Loadable } from "../api/state";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusPill,
  type StatusTone,
} from "../kit/primitives/index";

/** 加载态（原语：LoadingState）。外观类名逐字沿用旧值。 */
export function Loading() {
  const { t } = useTranslation();
  return (
    <LoadingState label={t("workbench.loading")} className="animate-pulse text-sm text-neutral-400" />
  );
}

/** 「该能力接线中」降级盒（问辩谱 5xx/超时/未接线）。保持宿主自有实现。 */
export function DegradeBox({ extra }: { extra?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <p>{t("workbench.unavailable")}</p>
      {extra ? <div className="mt-1 text-xs text-amber-700">{extra}</div> : null}
    </div>
  );
}

/** 业务错误盒（4xx 等）；401 追加「请先在顶栏设置访问令牌」。 */
export function ErrorBox({ message, code }: { message: string; code?: number }) {
  const { t } = useTranslation();
  return (
    <ErrorState
      label={t("workbench.error")}
      detail={message || undefined}
      hint={code === 401 ? t("workbench.tokenHint") : undefined}
      toneClassName="border-red-200 bg-red-50 text-red-800"
    />
  );
}

/** Loadable 四态统一渲染：idle 空、loading、unavailable 降级、error 报错、ready 渲染 children。 */
export function LoadBox<T>({
  state,
  children,
}: {
  state: Loadable<T>;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "idle") return null;
  if (state.status === "loading") return <Loading />;
  if (state.status === "unavailable") return <DegradeBox />;
  if (state.status === "error") return <ErrorBox message={state.message} code={state.code} />;
  return <>{children(state.data)}</>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="font-serif text-lg text-neutral-900">{children}</h2>;
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-sm text-green-700">{children}</p>;
}

/** 空态（原语：EmptyState）。 */
export function EmptyLine({ children }: { children: ReactNode }) {
  return <EmptyState className="text-sm text-neutral-400">{children}</EmptyState>;
}

const STABILITY_TONE: Record<Stability, { tone: StatusTone; cls: string }> = {
  stable: { tone: "positive", cls: "border-green-300 bg-green-50 text-green-800" },
  wavering: { tone: "warn", cls: "border-amber-300 bg-amber-50 text-amber-800" },
  shelved: { tone: "neutral", cls: "border-neutral-300 bg-neutral-100 text-neutral-500" },
};

/** 稳定性徽标（stable / wavering / shelved）。 */
export function StabilityBadge({ s }: { s: Stability }) {
  const { t } = useTranslation();
  // 未知状态沿用旧兜底：按 shelved 的配色
  const spec = STABILITY_TONE[s] ?? STABILITY_TONE.shelved;
  // 5.4b：只传 tone 不传 toneClassName → 配色走 CSS 变量（--fd-status-*）。
  // 亮色值在 theme-tokens.css 里精确等于原 Tailwind 类名的色值，故观感不变；
  // 代价是暗色主题下这枚徽标会随 [data-theme=dark] 变色，这正是要的效果。
  // spec.cls 保留为注释性对照，不再参与渲染。
  return (
    <StatusPill
      tone={spec.tone}
      className="shrink-0 rounded-full border px-2 py-0.5 text-xs"
    >
      {t(`workbench.stability.${s}`)}
    </StatusPill>
  );
}
