import { useId } from "react"
import { Sun, Moon } from "lucide-react"
import { useTheme } from "@/context/ThemeContext"

export function ThemeSwitch(): JSX.Element {
  const { theme, toggleTheme } = useTheme()
  const id = useId()
  const isLight = theme === "light"

  return (
    <div className="flex items-center gap-2">
      <Moon size={13} style={{ color: "var(--fg-faint)" }} />
      <label className="theme-switch" aria-label="Toggle light/dark theme">
        <input
          id={id}
          type="checkbox"
          checked={isLight}
          onChange={toggleTheme}
        />
        <span className="theme-switch-track" />
        <span className="theme-switch-thumb" />
      </label>
      <Sun size={13} style={{ color: "var(--fg-faint)" }} />
    </div>
  )
}