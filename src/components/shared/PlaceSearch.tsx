import { useCallback, useEffect, useMemo, useState } from "react"

// Optimized Singapore bounding box
const SG_BBOX = "103.60,1.13,104.05,1.48"
// Central point for proximity weight (near Orchard/Botanic)
const SG_CENTER = "103.8198,1.3521"

interface GeocodeFeature {
  id: string
  place_name: string
  center: [number, number]
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
    const q = encodeURIComponent(query.trim())
    
    // ADDED: proximity= for relevance, types= to catch POIs like "The Creek", and country=SG
    const url = new URL(`https://api.mapbox.com/geocoding/v5/mapbox.places/${q}.json`)
    url.searchParams.set("access_token", mapboxToken)
    url.searchParams.set("bbox", SG_BBOX)
    url.searchParams.set("proximity", SG_CENTER)
    url.searchParams.set("types", "address,poi,place")
    url.searchParams.set("country", "SG")
    url.searchParams.set("limit", "5")

    try {
      const res = await fetch(url.toString())
      if (!res.ok) { setResults([]); return }
      const data = (await res.json()) as { features?: GeocodeFeature[] }
      setResults(data.features ?? [])
    } catch {
      setResults([])
    }
  }, [canSearch, mapboxToken, query])

  useEffect(() => {
    const t = window.setTimeout(() => { void runSearch() }, 350)
    return () => window.clearTimeout(t)
  }, [runSearch])

  return (
    <div className="relative">
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
            // FIX: Use a hardcoded solid hex if var(--card) is translucent
            background: "#1a1a1a", // Force solid dark background
            border: "1px solid var(--border-mid)", 
            maxHeight: "280px",
            zIndex: 9999, // FIX: Ensure it floats above the "Generate" button
          }}
          role="listbox"
        >
          {results.map((f) => (
            <li key={f.id} className="border-b border-white/5 last:border-0">
              <button
                type="button"
                className="w-full px-4 py-3 text-left text-sm transition-colors flex items-start gap-3"
                onMouseEnter={(e) => { 
                  (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)",
                  (e.currentTarget as HTMLElement).style.color = "#fff"
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