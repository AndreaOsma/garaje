import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./vendor/design-system/tokens.css";
import "./vendor/design-system/base.css";
import "./styles/base.css";
// Modo dev de ágora (🛠️): elegir un elemento y pedir el cambio a la fábrica. Solo se activa dentro de ágora.
import "./vendor/dev-overlay/overlay";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
