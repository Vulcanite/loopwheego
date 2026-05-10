import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  build: {
    // MapLibre is the intentionally large engine chunk; warn only if it grows materially.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined
          if (id.includes("maplibre-gl")) return "maplibre"
          if (id.includes("lucide-react")) return "icons"
          if (id.includes("@radix-ui")) return "radix-ui"
          if (id.includes("react") || id.includes("react-dom")) return "react"
          return "vendor"
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
