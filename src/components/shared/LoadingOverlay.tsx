import { useEffect, useState, useRef } from "react"
import { Loader2 } from "lucide-react"

interface LoadingOverlayProps {
  visible: boolean
  timeoutSecs?: number
  label?: string
}

export function LoadingOverlay({ visible, timeoutSecs = 60, label = "Generating routes…" }: LoadingOverlayProps): JSX.Element | null {
  const [elapsed, setElapsed] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (visible) {
      setElapsed(0)
      intervalRef.current = setInterval(() => {
        setElapsed((e) => e + 1)
      }, 1000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [visible])

  if (!visible) return null

  const pct = Math.min((elapsed / timeoutSecs) * 100, 100)
  const remaining = Math.max(timeoutSecs - elapsed, 0)

  return (
    <div
      className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center"
      style={{ background: "var(--overlay)", backdropFilter: "blur(4px)" }}
    >
      <div
        className="rounded-xl border px-5 py-4 shadow-2xl min-w-[220px]"
        style={{ background: "var(--app-card)", borderColor: "color-mix(in srgb, var(--red) 35%, transparent)" }}
      >
        <div className="flex items-center gap-3 mb-3">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" style={{ color: "var(--red)" }} aria-hidden />
          <span className="text-sm font-medium" style={{ color: "var(--fg)" }}>{label}</span>
        </div>
        {/* Timeout progress bar */}
        <div className="rounded-full overflow-hidden h-1" style={{ background: "var(--border-mid)" }}>
          <div
            className="h-full rounded-full transition-none"
            style={{
              width: `${100 - pct}%`,
              background: pct > 80 ? "#f59e0b" : "var(--red)",
              transition: "width 1s linear, background 0.3s",
            }}
          />
        </div>
        <p className="text-[11px] mt-1.5 text-right tabular-nums" style={{ color: "var(--fg-faint)" }}>
          {remaining}s remaining
        </p>
      </div>
    </div>
  )
}
