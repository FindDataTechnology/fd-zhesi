/** 谱 · 定位合成：投影（六轴雷达+邻居+skipped）+ 张力簿 + 思想年轮（annals+历史投影）。 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AnnalEntry, type Projection, type TensionItem } from "../../api/client";
import { Loadable, mapApiError } from "../../api/state";
import { DegradeBox, EmptyLine, ErrorBox, Loading, SectionTitle } from "../../components/ui";
import RadarChart from "../../components/RadarChart";

export const MIN_CARDS_FOR_PROJECTION = 5;

/** 邻居距离条：以当前列表最大距离为比例尺。 */
function distanceWidth(distance: number, max: number): number {
  if (!Number.isFinite(distance) || !Number.isFinite(max) || max <= 0) return 0;
  return Math.max(0, Math.min(100, (distance / max) * 100));
}

/**
 * 降级标注（spec「Atlas 缺失时谱闭环降级」）：把缺失层与置信度摆在投影上方，
 * 不让用户把降级结果误读成完整结果。
 */
export function DegradationNote({ p }: { p: Projection }) {
  const { t } = useTranslation();
  const missing = p.missing_layers ?? [];
  if (!p.degraded && missing.length === 0) return null;
  const confidence = Number.isFinite(p.confidence) ? (p.confidence as number) : null;
  return (
    <div
      className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
      role="status"
    >
      <p className="font-medium">
        {t("workbench.map.degradedHeading")}
        {confidence !== null
          ? ` · ${t("workbench.map.confidence", { value: Math.round(confidence * 100) })}`
          : ""}
      </p>
      {missing.length > 0 ? (
        <p className="mt-1 text-xs">
          {t("workbench.map.missingLayers")}：{missing.join("、")}
          {p.neighbor_layer === "manual-seed"
            ? ` · ${t("workbench.map.seedNeighbors")}`
            : ""}
        </p>
      ) : null}
      {(p.degradation_reasons ?? []).length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
          {(p.degradation_reasons ?? []).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** 张力条目：候选与既成在表述上必须可区分（spec「候选不冒充既成张力」）。 */
function TensionEntry({
  item,
  onConfirm,
  onIgnore,
}: {
  item: TensionItem;
  onConfirm?: (id: string) => void;
  onIgnore?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const isCandidate = item.kind === "candidate";
  return (
    <li
      className={
        isCandidate
          ? "rounded-lg border border-dashed border-neutral-300 bg-neutral-50 p-4 text-sm"
          : "rounded-lg border border-neutral-200 bg-white p-4 text-sm"
      }
    >
      <p className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
        <span
          className={
            isCandidate
              ? "rounded bg-neutral-200 px-2 py-0.5 text-neutral-700"
              : "rounded bg-neutral-900 px-2 py-0.5 text-white"
          }
        >
          {isCandidate ? t("workbench.map.kindCandidate") : t("workbench.map.kindConfirmed")}
        </span>
        {item.tension_type ? (
          <span>{t(`workbench.map.tensionType.${item.tension_type}`, { defaultValue: item.tension_type })}</span>
        ) : null}
        {item.status ? <span>· {item.status}</span> : null}
      </p>
      <p className="mt-2 text-neutral-800">{item.description ?? item.id}</p>
      <p className="mt-1 text-xs text-neutral-400">
        {item.source ?? ""}
        {item.card_ids?.length
          ? ` · ${t("workbench.map.relatedCards", { count: item.card_ids.length })}`
          : ""}
      </p>
      {isCandidate ? (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => onConfirm?.(item.id)}
            className="rounded bg-neutral-900 px-3 py-1 text-xs text-white hover:bg-neutral-700"
          >
            {t("workbench.map.confirmCandidate")}
          </button>
          <button
            type="button"
            onClick={() => onIgnore?.(item.id)}
            className="rounded border border-neutral-300 px-3 py-1 text-xs text-neutral-700 hover:bg-neutral-100"
          >
            {t("workbench.map.ignoreCandidate")}
          </button>
        </div>
      ) : null}
    </li>
  );
}

// ---- 视图（显式状态，可独立渲染降级态） ----

export function MapView({
  count,
  projection,
  onProject,
  tensions,
  annals,
  history,
  onConfirmTension,
  onIgnoreTension,
}: {
  count: Loadable<number>;
  projection: Loadable<Projection>;
  onProject?: () => void;
  tensions: Loadable<TensionItem[]>;
  annals: Loadable<AnnalEntry[]>;
  history: Loadable<Projection[]>;
  onConfirmTension?: (id: string) => void;
  onIgnoreTension?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const canProject = count.status === "ready" && count.data >= MIN_CARDS_FOR_PROJECTION;
  const projecting = projection.status === "loading";

  return (
    <section className="space-y-8">
      <div>
        <SectionTitle>{t("workbench.map.heading")}</SectionTitle>
        <button
          type="button"
          disabled={!canProject || projecting}
          onClick={() => onProject?.()}
          className="mt-3 rounded bg-neutral-900 px-4 py-2 text-sm text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {projecting ? t("workbench.map.projecting") : t("workbench.map.project")}
        </button>
        {count.status === "ready" && count.data < MIN_CARDS_FOR_PROJECTION ? (
          <p className="mt-2 text-xs text-neutral-500">
            {t("workbench.map.needMore", { count: count.data })}
          </p>
        ) : null}
        {count.status === "unavailable" ? (
          <div className="mt-2">
            <DegradeBox />
          </div>
        ) : null}
        {count.status === "error" ? (
          <div className="mt-2">
            <ErrorBox message={count.message} code={count.code} />
          </div>
        ) : null}
      </div>

      {projection.status === "loading" ? <Loading /> : null}
      {projection.status === "unavailable" ? <DegradeBox /> : null}
      {projection.status === "error" ? (
        <ErrorBox message={projection.message} code={projection.code} />
      ) : null}
      {projection.status === "ready" ? <ProjectionView p={projection.data} /> : null}
      {/* 张力簿 */}
      <div>
        <SectionTitle>{t("workbench.map.tensions")}</SectionTitle>
        {tensions.status === "loading" ? <Loading /> : null}
        {tensions.status === "unavailable" ? (
          <div className="mt-3">
            <DegradeBox />
          </div>
        ) : null}
        {tensions.status === "error" ? (
          <div className="mt-3">
            <ErrorBox message={tensions.message} code={tensions.code} />
          </div>
        ) : null}
        {tensions.status === "ready" && tensions.data.length === 0 ? (
          <EmptyLine>{t("workbench.map.tensionsEmpty")}</EmptyLine>
        ) : null}
        {tensions.status === "ready" && tensions.data.length > 0 ? (
          <div className="mt-3 space-y-4">
            {/* 既成张力：参照系有明确记录 */}
            <ul className="space-y-2">
              {tensions.data
                .filter((tn) => tn.kind !== "candidate")
                .map((tn) => (
                  <TensionEntry key={tn.id} item={tn} />
                ))}
            </ul>
            {/* 候选：推断所得，明确标注「尚未确认」，可确认或忽略 */}
            {tensions.data.some((tn) => tn.kind === "candidate") ? (
              <div>
                <h3 className="text-xs font-medium text-neutral-500">
                  {t("workbench.map.tensionCandidates")}
                </h3>
                <ul className="mt-2 space-y-2">
                  {tensions.data
                    .filter((tn) => tn.kind === "candidate")
                    .map((tn) => (
                      <TensionEntry
                        key={tn.id}
                        item={tn}
                        onConfirm={onConfirmTension}
                        onIgnore={onIgnoreTension}
                      />
                    ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* 思想年轮（折叠） */}
      <details className="rounded-lg border border-neutral-200 bg-white p-5">
        <summary className="cursor-pointer font-serif text-lg">{t("workbench.map.annals")}</summary>
        <div className="mt-4 space-y-6">
          <div>
            <h3 className="text-sm font-medium text-neutral-500">{t("workbench.map.annalsHistory")}</h3>
            {annals.status === "loading" ? <Loading /> : null}
            {annals.status === "unavailable" ? (
              <div className="mt-2">
                <DegradeBox />
              </div>
            ) : null}
            {annals.status === "error" ? (
              <div className="mt-2">
                <ErrorBox message={annals.message} code={annals.code} />
              </div>
            ) : null}
            {annals.status === "ready" && annals.data.length === 0 ? (
              <EmptyLine>{t("workbench.map.annalsEmpty")}</EmptyLine>
            ) : null}
            {annals.status === "ready" && annals.data.length > 0 ? (
              <ol className="mt-2 space-y-2 border-l border-neutral-200 pl-4">
                {annals.data.map((a) => (
                  <li key={a.id} className="text-sm">
                    <p className="text-xs text-neutral-400">
                      {a.at} · {t(`workbench.map.annalsKind.${a.kind}`, { defaultValue: a.kind })}
                    </p>
                    <p className="text-neutral-800">
                      {a.snapshot?.question ?? a.card_id}
                      {a.snapshot?.position ? ` → ${a.snapshot.position}` : ""}
                    </p>
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
          <div>
            <h3 className="text-sm font-medium text-neutral-500">{t("workbench.map.projections")}</h3>
            {history.status === "loading" ? <Loading /> : null}
            {history.status === "unavailable" ? (
              <div className="mt-2">
                <DegradeBox />
              </div>
            ) : null}
            {history.status === "error" ? (
              <div className="mt-2">
                <ErrorBox message={history.message} code={history.code} />
              </div>
            ) : null}
            {history.status === "ready" && history.data.length === 0 ? (
              <EmptyLine>{t("workbench.map.projectionsEmpty")}</EmptyLine>
            ) : null}
            {history.status === "ready" && history.data.length > 0 ? (
              <ul className="mt-2 space-y-1">
                {history.data.map((p, i) => (
                  <li key={p.id ?? i} className="text-xs text-neutral-500">
                    {p.created_at ?? `#${i + 1}`} ·{" "}
                    {Object.entries(p.axes ?? {})
                      .map(([k, v]) => `${k} ${v}`)
                      .join(" · ")}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      </details>
    </section>
  );
}

function ProjectionView({ p }: { p: Projection }) {
  const { t } = useTranslation();
  const neighbors = p.neighbors ?? [];
  const maxDist = Math.max(...neighbors.map((nb) => nb.distance), 0);
  return (
    <div className="space-y-5">
      <DegradationNote p={p} />
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium text-neutral-500">{t("workbench.map.radar")}</h3>
          <RadarChart axes={p.axes ?? {}} />
        </div>
        <div>
          <h3 className="text-sm font-medium text-neutral-500">{t("workbench.map.neighbors")}</h3>
          {neighbors.length === 0 ? (
            <EmptyLine>{t("workbench.map.neighborsEmpty")}</EmptyLine>
          ) : (
            <ul className="mt-2 space-y-2">
              {neighbors.map((nb) => (
                <li key={nb.name_en} className="text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-neutral-800">
                      {nb.name_zh ? `${nb.name_zh} · ${nb.name_en}` : nb.name_en}
                    </span>
                    <span className="text-xs tabular-nums text-neutral-500">
                      {t("workbench.map.distance")} {Number.isFinite(nb.distance) ? nb.distance.toFixed(2) : "—"}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded bg-neutral-100">
                    <div
                      className="h-1.5 rounded bg-neutral-700"
                      style={{ width: `${distanceWidth(nb.distance, maxDist)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="space-y-1 text-xs text-neutral-500">
        <p>{t("workbench.map.basedOn", { count: p.based_on_cards?.length ?? 0 })}</p>
        {p.skipped?.length ? (
          <p>
            {t("workbench.map.skipped", {
              ids: p.skipped
                .map((s) => (typeof s === "string" ? s : s?.card_id ?? ""))
                .filter(Boolean)
                .join("、"),
            })}
          </p>
        ) : null}
      </div>
    </div>
  );
}

// ---- 容器：接 API ----

export default function MapPanel() {
  const [count, setCount] = useState<Loadable<number>>({ status: "loading" });
  const [projection, setProjection] = useState<Loadable<Projection>>({ status: "idle" });
  const [tensions, setTensions] = useState<Loadable<TensionItem[]>>({ status: "loading" });
  const [annals, setAnnals] = useState<Loadable<AnnalEntry[]>>({ status: "loading" });
  const [history, setHistory] = useState<Loadable<Projection[]>>({ status: "loading" });

  const loadCount = async () => {
    setCount({ status: "loading" });
    try {
      setCount({ status: "ready", data: (await api.listCards("active")).results.length });
    } catch (e) {
      setCount(mapApiError(e));
    }
  };
  const loadTensions = async () => {
    setTensions({ status: "loading" });
    try {
      setTensions({ status: "ready", data: (await api.listTensions()).results ?? [] });
    } catch (e) {
      setTensions(mapApiError(e));
    }
  };
  const loadAnnals = async () => {
    setAnnals({ status: "loading" });
    try {
      setAnnals({ status: "ready", data: (await api.annals()).results ?? [] });
    } catch (e) {
      setAnnals(mapApiError(e));
    }
  };
  const loadHistory = async () => {
    setHistory({ status: "loading" });
    try {
      setHistory({ status: "ready", data: (await api.listProjections()).results ?? [] });
    } catch (e) {
      setHistory(mapApiError(e));
    }
  };

  useEffect(() => {
    void loadCount();
    void loadTensions();
    void loadAnnals();
    void loadHistory();
  }, []);

  const doProject = async () => {
    setProjection({ status: "loading" });
    try {
      setProjection({ status: "ready", data: await api.project() });
      await loadHistory(); // 新投影入历史
    } catch (e) {
      setProjection(mapApiError(e));
    }
  };

  const onConfirmTension = async (id: string) => {
    try {
      await api.confirmTension(id);
      await loadTensions(); // 状态流转后重新拉取（留痕在服务端）
    } catch (e) {
      setTensions(mapApiError(e));
    }
  };

  const onIgnoreTension = async (id: string) => {
    try {
      await api.ignoreTension(id);
      await loadTensions();
    } catch (e) {
      setTensions(mapApiError(e));
    }
  };

  return (
    <MapView
      count={count}
      projection={projection}
      onProject={() => void doProject()}
      tensions={tensions}
      annals={annals}
      history={history}
      onConfirmTension={(id) => void onConfirmTension(id)}
      onIgnoreTension={(id) => void onIgnoreTension(id)}
    />
  );
}
