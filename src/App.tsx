// App.tsx
import { useState } from "react"
import { Home } from "@/pages/Home"
import { ThemeSwitch } from "@/components/shared/ThemeSwitch"

export default function App(): JSX.Element {
  const [aboutOpen, setAboutOpen] = useState(false)

  return (
    /* CHANGE: h-screen instead of min-h-screen, add flex-col and overflow-hidden */
    <div className="h-[100dvh] flex flex-col overflow-hidden font-body" style={{ background: "var(--bg)" }}>
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
            <p className="text-[10px] md:text-[11px] mt-0.5 tracking-widest uppercase" style={{ color: "var(--fg-faint)" }}>Walk · Cycle · Discover</p>
          </div>
        </div>
        <div className="flex items-center gap-3 md:gap-4">
          <ThemeSwitch />
          <button
            type="button"
            onClick={() => setAboutOpen(true)}
            className="text-xs md:text-sm px-2.5 py-1.5 rounded-md transition-colors"
            style={{ color: "var(--fg-muted)" }}
          >
            Story
          </button>
        </div>
      </header>
      
      {/* Home must be flex-1 to fill the remaining height */}
      <Home />

      {aboutOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.45)" }}
          onClick={() => setAboutOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl p-5 border text-center"
            style={{ background: "var(--surface)", borderColor: "var(--border-mid)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm leading-relaxed" style={{ color: "var(--fg)" }}>
              LoopWheeGo turns Singapore into a route playground for walkers and cyclists.
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--fg-faint)" }}>
              Designed by{" "}
              <a
                href="https://www.linkedin.com/in/amish-thekke-parambil/"
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-2"
                style={{ color: "var(--red)" }}
              >
                an explorer
              </a>
              .
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--fg-faint)" }}>
              Built to make everyday movement feel like a small adventure.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
