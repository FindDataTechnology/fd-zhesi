import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./i18n";
import '@fontsource/noto-serif-sc/600.css'
import '@fontsource/noto-serif-sc/700.css'
import './index.css'
// 品牌令牌（5.4b）：覆盖 kit 原语的 --fd-status-*/--fd-error-* 取值。
// 必须在 index.css 之后导入——@theme 里的宿主调色板先定义，这里再覆盖原语变量。
import './theme-tokens.css';
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
