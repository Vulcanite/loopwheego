// App.tsx
import { Home } from "@/pages/Home"
import { ThemeSwitch } from "@/components/shared/ThemeSwitch"

export default function App(): JSX.Element {
  return (
    /* CHANGE: h-screen instead of min-h-screen, add flex-col and overflow-hidden */
    <div className="h-screen flex flex-col overflow-hidden font-body" style={{ background: "var(--bg)" }}>
      <header
        className="flex-shrink-0 flex items-center justify-between px-4 md:px-6 py-3 md:py-4"
        style={{ background: "var(--surface)", borderBottom: "1px solid var(--sidebar-border)" }}
      >
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 md:w-9 md:h-9 rounded-lg" style={{ background: "var(--red)" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12h4l3-9 4 18 3-9h4"/>
            </svg>
          </div>
          <div>
            <h1 className="text-sm md:text-base font-display font-bold leading-none" style={{ color: "var(--fg)" }}>LoopWheeGo</h1>
            <p className="text-[10px] md:text-[11px] mt-0.5 tracking-widest uppercase" style={{ color: "var(--fg-faint)" }}>Walk · Explore · Discover</p>
          </div>
        </div>
        <div className="flex items-center gap-3 md:gap-4">
          <ThemeSwitch />
          <div className="hidden md:flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-faint)" }}>
            <span className="w-2 h-2 rounded-full inline-block animate-pulse" style={{ background: "var(--green)" }} />
            Singapore
          </div>
        </div>
      </header>
      
      {/* Home must be flex-1 to fill the remaining height */}
      <Home />
    </div>
  )
}