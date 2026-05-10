import React from "react"
import ReactDOM from "react-dom/client"

import App from "@/App"
import { Toaster } from "@/components/ui/toaster"
import { ThemeProvider } from "@/context/ThemeContext"
import "@/index.css"

const rootEl = document.getElementById("root")
if (!rootEl) throw new Error("Root element not found")

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
      <Toaster />
    </ThemeProvider>
  </React.StrictMode>
)
