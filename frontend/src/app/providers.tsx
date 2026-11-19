"use client"

import { type ReactNode } from "react"

import { Toaster } from "@/components/ui/toaster"
import { ThemeProvider } from "@/context/ThemeContext"

export function Providers({ children }: { children: ReactNode }): JSX.Element {
  return (
    <ThemeProvider>
      {children}
      <Toaster />
    </ThemeProvider>
  )
}
