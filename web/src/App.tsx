import { Link, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Landing from "./pages/Landing";
import Workbench from "./pages/Workbench";
import Admin from "./pages/Admin";

export default function App() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <nav className="flex gap-6 border-b border-neutral-200 px-6 py-3 text-sm">
        <Link to="/">{t("nav.home")}</Link>
        <Link to="/workbench">{t("nav.workbench")}</Link>
        <Link to="/admin">{t("nav.admin")}</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </div>
  );
}
