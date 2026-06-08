import React from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./styles.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element #root was not found.");
}

// 挂载 React 控制台应用到 index.html 的 root 节点。
// Mounts the React console app into the root node from index.html.
createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
