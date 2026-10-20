import { useTranslation } from "react-i18next";

export default function Landing() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-serif">{t("landing.title")}</h1>
      <p className="mt-4 text-lg text-neutral-600">{t("landing.subtitle")}</p>
      <div className="mt-10 grid grid-cols-3 gap-4">
        {(["ask", "debate", "map"] as const).map((k) => (
          <div key={k} className="rounded-lg border border-neutral-200 bg-white p-4 text-center">
            {t(`landing.loops.${k}`)}
          </div>
        ))}
      </div>
    </main>
  );
}
