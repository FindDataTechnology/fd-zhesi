import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getToken, setToken } from "./api/client";
import { authShell, login, logout, SSO_HINT_DOMAIN } from "./api/logto";
import { runSsoOnMount } from "./kit/auth/sso-mount";
import Landing from "./pages/Landing";
import Workbench from "./pages/Workbench";
import Admin from "./pages/Admin";

export default function App() {
  const { t, i18n } = useTranslation();
  const [token, setTokenState] = useState(() => getToken());
  const [ssoError, setSsoError] = useState(false);
  const [lang, setLang] = useState(i18n.language ?? "zh");

  // 回跳收口 + 静默 SSO（web-shell-kit「同租户静默单点登录」）：
  // 逻辑在共享壳的 `runSsoOnMount` 里，三宿主共用一份，别再各抄一遍。
  useEffect(() => {
    void runSsoOnMount({
      auth: authShell(),
      setToken,
      hasToken: () => Boolean(getToken()),
      hintDomain: SSO_HINT_DOMAIN,
      onLoggedIn: (t) => setTokenState(t),
    }).then((r) => {
      // 真实故障（网络/上游/配置）必须可见且可重试，绝不渲染成「未登录」。
      if (r.outcome === 'error') setSsoError(true);
    });
  }, []);

  const changeLang = (l: string) => {
    setLang(l);
    void i18n.changeLanguage(l);
  };

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      {ssoError && (
        <div
          role="alert"
          data-testid="sso-error"
          className="flex items-center gap-3 border-b border-amber-300 bg-amber-50 px-6 py-2 text-xs text-amber-900"
        >
          <span>{t("nav.sessionCheckFailed")}</span>
          <button
            type="button"
            onClick={() => {
              setSsoError(false);
              void runSsoOnMount({
                auth: authShell(),
                setToken,
                hasToken: () => Boolean(getToken()),
                hintDomain: SSO_HINT_DOMAIN,
                onLoggedIn: (t) => setTokenState(t),
              }).then((r) => {
                if (r.outcome === "error") setSsoError(true);
              });
            }}
            className="rounded border border-amber-400 px-2 py-0.5 hover:bg-amber-100"
          >
            {t("nav.retry")}
          </button>
        </div>
      )}
      <nav className="flex items-center gap-6 border-b border-neutral-200 px-6 py-3 text-sm">
        <Link to="/">{t("nav.home")}</Link>
        <Link to="/workbench">{t("nav.workbench")}</Link>
        <Link to="/admin">{t("nav.admin")}</Link>

        <div className="ml-auto flex items-center gap-3">
          {token ? (
            <button
              type="button"
              onClick={() => logout()}
              className="rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100"
            >
              {t("nav.logout")}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void login()}
              className="rounded bg-neutral-900 px-2 py-1 text-xs text-white hover:bg-neutral-700"
            >
              {t("nav.login")}
            </button>
          )}
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
