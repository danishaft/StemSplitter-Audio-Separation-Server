import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource/dm-mono/latin-400.css";
import "@fontsource/dm-mono/latin-500.css";
import "@fontsource/space-grotesk/latin-400.css";
import "@fontsource/space-grotesk/latin-500.css";
import "@fontsource/space-grotesk/latin-700.css";
import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Application root element is missing");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
