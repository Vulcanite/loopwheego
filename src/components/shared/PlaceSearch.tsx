import { useCallback, useEffect, useMemo, useState } from "react"

// Optimized Singapore bounding box
const SG_BBOX = "103.60,1.13,104.05,1.48"
// Central point for proximity weight (near Orchard/Botanic)
const SG_CENTER = "103.8198,1.3521"

interface GeocodeFeature {
  id: string
  place_name: string
  center: [number, number]
  relevance?: number
}

interface GeocodeResponse {
  features?: GeocodeFeature[]
}

interface PlaceSearchProps {
  mapboxToken: string
  query: string
  onQueryChange: (q: string) => void
  onPlaceSelected: (lng: number, lat: number, label: string) => void
  placeholder?: string
  disabled?: boolean
}

export function PlaceSearch({
  mapboxToken,
  query,
  onQueryChange,
  onPlaceSelected,
  placeholder = "Search address or place…",
  disabled = false,
}: PlaceSearchProps): JSX.Element {
  const [results, setResults] = useState<GeocodeFeature[]>([])
  const [open, setOpen] = useState(false)

  const canSearch = useMemo(
    () => !disabled && mapboxToken.length > 0 && query.trim().length >= 2,
    [disabled, mapboxToken, query]
  )

  const runSearch = useCallback(async (): Promise<void> => {
    if (!canSearch) { setResults([]); return }
    const sanitizeQuery = (value: string): string =>
      value.replace(/@/g, " ").replace(/[.,]/g, " ").replace(/\s+/g, " ").trim()

    const buildUrl = (rawQuery: string): string => {
      const q = encodeURIComponent(rawQuery.trim())
      const url = new URL(`https://api.mapbox.com/geocoding/v5/mapbox.places/${q}.json`)
      url.searchParams.set("access_token", mapboxToken)
      url.searchParams.set("bbox", SG_BBOX)
      url.searchParams.set("proximity", SG_CENTER)
      url.searchParams.set("types", "poi,address,neighborhood,locality,place")
      url.searchParams.set("country", "SG")
      url.searchParams.set("autocomplete", "true")
      url.searchParams.set("fuzzyMatch", "true")
      url.searchParams.set("language", "en")
      url.searchParams.set("limit", "8")
      return url.toString()
    }

    const dedupe = (rows: GeocodeFeature[]): GeocodeFeature[] => {
      const seen = new Set<string>()
      const out: GeocodeFeature[] = []
      for (const r of rows) {
        const key = `${r.id}|${r.place_name.toLowerCase()}`
        if (seen.has(key)) continue
        seen.add(key)
        out.push(r)
      }
      return out
    }

    const normalized = sanitizeQuery(query.trim())
    if (normalized.length < 2) {
      setResults([])
      return
    }
    const fallback = normalized.toLowerCase().includes("singapore")
      ? normalized
      : `${normalized} singapore`

    const rank = (rows: GeocodeFeature[]): GeocodeFeature[] => {
      const needle = normalized.toLowerCase()
      const tokens = needle.split(" ").filter(Boolean)
      return rows
        .map((row) => {
          const name = row.place_name.toLowerCase()
          let score = Number(row.relevance ?? 0)
          if (name.includes(needle)) score += 3.0
          if (tokens.every((t) => name.includes(t))) score += 2.0
          if (name.startsWith(tokens[0] ?? "")) score += 0.8
          return { row, score }
        })
        .sort((a, b) => b.score - a.score)
        .map((x) => x.row)
    }

    try {
      const queries = Array.from(new Set([normalized, fallback]))
      const responses = await Promise.all(
        queries.map(async (q) => {
          const res = await fetch(buildUrl(q))
          if (!res.ok) return [] as GeocodeFeature[]
          const data = (await res.json()) as GeocodeResponse
          return data.features ?? []
        })
      )
      const merged = dedupe(responses.flat())
      setResults(rank(merged))
    } catch {
      setResults([])
    }
  }, [canSearch, mapboxToken, query])

  useEffect(() => {
    const t = window.setTimeout(() => { void runSearch() }, 350)
    return () => window.clearTimeout(t)
  }, [runSearch])

  return (
    <div className="relative z-40">
      <input
        value={query}
        onChange={(e) => { onQueryChange(e.target.value); setOpen(true) }}
        onFocus={() => { if (!disabled) setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 200)} // Increased delay for click registration
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: "var(--input-bg)",
          border: "1px solid var(--border-mid)",
          color: "var(--fg)",
        }}
      />

      {open && results.length > 0 && !disabled ? (
        <ul
          className="absolute mt-1 w-full overflow-auto rounded-lg shadow-2xl"
          style={{ 
            background: "var(--surface)",
            border: "1px solid var(--border-mid)", 
            maxHeight: "280px",
            zIndex: 9999,
            opacity: 1,
            backdropFilter: "none",
            WebkitBackdropFilter: "none",
          }}
          role="listbox"
        >
          {results.map((f) => (
            <li key={f.id} style={{ borderBottom: "1px solid var(--border)" }}>
              <button
                type="button"
                className="w-full px-4 py-3 text-left text-sm transition-colors flex items-start gap-3"
                style={{ color: "var(--fg-muted)" }}
                onMouseEnter={(e) => { 
                  (e.currentTarget as HTMLElement).style.background = "var(--pill-hover)",
                  (e.currentTarget as HTMLElement).style.color = "var(--fg)"
                }}
                onMouseLeave={(e) => { 
                  (e.currentTarget as HTMLElement).style.background = "transparent",
                  (e.currentTarget as HTMLElement).style.color = "var(--fg-muted)"
                }}
                onMouseDown={() => {
                  const [lng, lat] = f.center
                  onPlaceSelected(lng, lat, f.place_name)
                  onQueryChange(f.place_name)
                  setOpen(false)
                }}
              >
                <span style={{ color: "var(--red)" }} className="mt-0.5">↗</span>
                <span className="leading-snug">{f.place_name}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
