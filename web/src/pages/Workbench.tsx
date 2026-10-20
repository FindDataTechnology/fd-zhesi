import { useTranslation } from "react-i18next";

export default function Workbench() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-2xl font-serif">{t("workbench.title")}</h1>
      <p className="mt-4 text-neutral-500">{t("workbench.placeholder")}</p>
    </main>
  );
}
