import { useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getToken, setToken } from "./api/client";
import Landing from "./pages/Landing";
import Workbench from "./pages/Workbench";
import Admin from "./pages/Admin";

export default function App() {
  const { t, i18n } = useTranslation();
  const [token, setTokenState] = useState(() => getToken());
  const [lang, setLang] = useState(i18n.language ?? "zh");

  const changeLang = (l: string) => {
    setLang(l);
    void i18n.changeLanguage(l);
  };

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <nav className="flex items-center gap-6 border-b border-neutral-200 px-6 py-3 text-sm">
        <Link to="/">{t("nav.home")}</Link>
        <Link to="/workbench">{t("nav.workbench")}</Link>
        <Link to="/admin">{t("nav.admin")}</Link>

        {/* 开发态：顶栏直填访问令牌（存 localStorage["zhesi_token"]） */}
        <input
          aria-label={t("nav.token")}
          title={t("nav.token")}
          value={token}
          placeholder={t("nav.token")}
          autoComplete="off"
          onChange={(e) => {
            setTokenState(e.target.value);
            setToken(e.target.value);
          }}
          className="ml-auto w-44 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-700 focus:border-neutral-900 focus:outline-none"
        />
        <div className="flex overflow-hidden rounded border border-neutral-300 text-xs">
          {["zh", "en"].map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => changeLang(l)}
              className={`px-2 py-1 ${
                lang === l ? "bg-neutral-900 text-white" : "bg-white text-neutral-500 hover:bg-neutral-100"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </div>
  );
}
