import { type ReactNode } from "react"

export type SheetState = "idle" | "controls" | "routes"

interface BottomSheetProps {
  state: SheetState
  onHandleTap: () => void
  children: ReactNode
}

const TRANSLATE: Record<SheetState, string> = {
  idle:     "translateY(100%)",
  controls: "translateY(0%)",
  routes:   "translateY(calc(100% - 176px))",
}

export function BottomSheet({ state, onHandleTap, children }: BottomSheetProps): JSX.Element {
  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-30 flex flex-col rounded-t-2xl"
      style={{
        height: "85dvh",
        background: "var(--surface)",
        borderTop: "1px solid var(--border-mid)",
        boxShadow: "0 -8px 40px rgba(0,0,0,0.35)",
        transform: TRANSLATE[state],
        transition: "transform 0.38s cubic-bezier(0.32, 0.72, 0, 1)",
        willChange: "transform",
      }}
    >
      {/* Drag handle — tapping transitions state */}
      <div
        className="flex justify-center items-center pt-3 pb-2 shrink-0 cursor-pointer"
        onClick={onHandleTap}
        role="button"
        aria-label="Toggle panel"
      >
        <div className="w-10 h-1 rounded-full" style={{ background: "var(--border-mid)" }} />
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {children}
      </div>
    </div>
  )
}
