import type { Metadata } from "next"
import type { ReactNode } from "react"
import "maplibre-gl/dist/maplibre-gl.css"

import "@/index.css"
import { Providers } from "@/app/providers"

export const metadata: Metadata = {
  title: "LoopWheeGo",
  description: "Walk, cycle, and discover Singapore routes.",
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>): JSX.Element {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
