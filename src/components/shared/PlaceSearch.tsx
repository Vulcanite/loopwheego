import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api } from "@/services/api"

interface NominatimResult {
  place_id: number
  display_name: string
  lat: string
  lon: string
  name?: string
  type?: string
  importance?: number
  address?: {
    postcode?: string
    road?: string
    house_number?: string
    neighbourhood?: string
    suburb?: string
    city?: string
    town?: string
    village?: string
    country?: string
  }
}

interface PlaceSearchProps {
  query: string
  onQueryChange: (q: string) => void
  onPlaceSelected: (lng: number, lat: number, label: string) => void
  placeholder?: string
  disabled?: boolean
}

export function PlaceSearch({
  query,
  onQueryChange,
  onPlaceSelected,
  placeholder = "Search address, place, or postcode…",
  disabled = false,
}: PlaceSearchProps): JSX.Element {
  const [results, setResults] = useState<NominatimResult[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)
  const blurTimeoutRef = useRef<number | null>(null)

  const canSearch = useMemo(
    () => !disabled && query.trim().length >= 2,
    [disabled, query]
  )

  const normalizeQuery = (raw: string): string =>
    raw
      .replace(/@/g, " ")
      .replace(/[.,]/g, " ")
      .replace(/\s+/g, " ")
      .trim()

  const isSyntheticDisplayQuery = (raw: string, normalized: string): boolean => {
    const rawLower = raw.trim().toLowerCase()
    const normalizedLower = normalized.toLowerCase().replace(/…/g, "")

    return (
      rawLower.startsWith("detecting current location") ||
      rawLower.startsWith("my location") ||
      normalizedLower.startsWith("detecting current location") ||
      normalizedLower.startsWith("my location") ||
      normalizedLower === "singapore city centre"
    )
  }

  const clearBlurTimeout = (): void => {
    if (blurTimeoutRef.current !== null) {
      window.clearTimeout(blurTimeoutRef.current)
      blurTimeoutRef.current = null
    }
  }

  const cleanLabel = (label: string): string => {
    return label.replace(/,\s*Singapore$/i, "")
  }

  const dedupe = (rows: NominatimResult[]): NominatimResult[] => {
    const seen = new Set<string>()
    const out: NominatimResult[] = []

    for (const row of rows) {
      const key = `${row.lat},${row.lon},${row.display_name}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push(row)
    }

    return out
  }

  const sortResults = (rows: NominatimResult[], normalized: string): NominatimResult[] => {
    const q = normalized.toLowerCase()

    return [...rows].sort((a, b) => {
      const aName = a.display_name.toLowerCase()
      const bName = b.display_name.toLowerCase()

      const aExactPostcode = a.address?.postcode === normalized ? 1 : 0
      const bExactPostcode = b.address?.postcode === normalized ? 1 : 0
      if (aExactPostcode !== bExactPostcode) return bExactPostcode - aExactPostcode

      const aStarts = aName.startsWith(q) ? 1 : 0
      const bStarts = bName.startsWith(q) ? 1 : 0
      if (aStarts !== bStarts) return bStarts - aStarts

      const aIncludes = aName.includes(q) ? 1 : 0
      const bIncludes = bName.includes(q) ? 1 : 0
      if (aIncludes !== bIncludes) return bIncludes - aIncludes

      return (b.importance ?? 0) - (a.importance ?? 0)
    })
  }

  const runSearch = useCallback(async (): Promise<void> => {
    if (!canSearch) {
      abortRef.current?.abort()
      setLoading(false)
      setResults([])
      return
    }

    const normalized = normalizeQuery(query)
    if (normalized.length < 2) {
      abortRef.current?.abort()
      setLoading(false)
      setResults([])
      return
    }
    if (isSyntheticDisplayQuery(query, normalized)) {
      abortRef.current?.abort()
      setLoading(false)
      setResults([])
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const currentRequestId = ++requestIdRef.current

    setLoading(true)

    try {
      const data = await api.searchPlaces(normalized, controller.signal) as NominatimResult[]

      if (currentRequestId === requestIdRef.current) {
        const cleaned = dedupe(data ?? [])
        const sorted = sortResults(cleaned, normalized)
        setResults(sorted)
        setLoading(false)
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") return

      if (currentRequestId === requestIdRef.current) {
        setResults([])
        setLoading(false)
      }
    }
  }, [canSearch, query])

  useEffect(() => {
    const t = window.setTimeout(() => {
      void runSearch()
    }, 350)

    return () => {
      window.clearTimeout(t)
    }
  }, [runSearch])

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      clearBlurTimeout()
    }
  }, [])

  const showDropdown = open && !disabled && (loading || results.length > 0)

  return (
    <div className="relative" style={{ zIndex: 100 }}>
      <input
        value={query}
        onChange={(e) => {
          onQueryChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => {
          if (!disabled) {
            clearBlurTimeout()
            setOpen(true)
          }
        }}
        onBlur={() => {
          clearBlurTimeout()
          blurTimeoutRef.current = window.setTimeout(() => {
            setOpen(false)
          }, 120)
        }}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        className="w-full px-3 py-2.5 rounded-lg text-base md:text-sm outline-none transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: "var(--input-bg)",
          border: "1px solid var(--border-mid)",
          color: "var(--fg)",
        }}
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        aria-haspopup="listbox"
      />

      {showDropdown ? (
        <ul
          className="mt-1 w-full overflow-auto rounded-lg shadow-2xl md:absolute md:left-0 md:top-full"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border-mid)",
            maxHeight: "280px",
            zIndex: 200,
          }}
          role="listbox"
        >
          {loading ? (
            <li>
              <div
                className="px-4 py-3 text-sm"
                style={{ color: "var(--fg-muted)" }}
              >
                Searching...
              </div>
            </li>
          ) : (
            results.map((item) => {
              const lng = Number(item.lon)
              const lat = Number(item.lat)
              const label = cleanLabel(item.display_name)

              return (
                <li
                  key={`${item.place_id}-${item.lat}-${item.lon}`}
                  style={{ borderBottom: "1px solid var(--app-border)" }}
                >
                  <button
                    type="button"
                    className="w-full px-4 py-3 text-left text-sm transition-colors flex items-start gap-3"
                    style={{ color: "var(--fg-muted)", background: "var(--surface)" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "var(--pill-hover)"
                      e.currentTarget.style.color = "var(--fg)"
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent"
                      e.currentTarget.style.color = "var(--fg-muted)"
                    }}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      clearBlurTimeout()
                      onPlaceSelected(lng, lat, label)
                      setOpen(false)
                    }}
                  >
                    <span style={{ color: "var(--red)" }} className="mt-0.5">
                      ↗
                    </span>
                    <span className="leading-snug">{label}</span>
                  </button>
                </li>
              )
            })
          )}
        </ul>
      ) : null}
    </div>
  )
}
