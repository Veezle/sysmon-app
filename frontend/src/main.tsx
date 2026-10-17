import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/style.css";

const root = document.getElementById("root");
if (root === null) throw new Error("chybí #root v index.html");
// `body` je dvanactisloupcova mrizka a ocekava `.topbar`/`.card` jako sve
// prime potomky. Vite obal je #root, ktery by byl jedinym grid itemem -
// `contents` ho z mrizky vynda a deti se zaradi stejne jako v sysmonu.
root.style.display = "contents";
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
