import { useEffect } from "react"
import maplibregl from "maplibre-gl"
import type { POI } from "@/types/poi"
import { formatPOICategory, getPOICategoryColor } from "@/lib/poiPresentation"

interface POIMarkerProps {
  map: maplibregl.Map
  poi: POI
  index: number
  isSelected: boolean
  onSelect: (id: string) => void
  onAddWaypoint?: (lng: number, lat: number, poiId: string) => void
  isAdded?: boolean
}

export function POIMarker({ map, poi, index, isSelected, onSelect, onAddWaypoint, isAdded = false }: POIMarkerProps): null {
  useEffect(() => {
    const color = getPOICategoryColor(poi.category)
    const markerColor = isSelected ? "#c0271e" : color

    const el = document.createElement("button")
    el.type = "button"
    el.style.cssText = `
      width: 32px; height: 32px;
      border-radius: 50%;
      border: 2.5px solid white;
      background: ${markerColor};
      color: white;
      font-size: 11px;
      font-weight: 700;
      font-family: 'DM Sans', sans-serif;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      box-shadow: 0 2px 14px ${markerColor}80;
      transform: ${isSelected ? "scale(1.25)" : "scale(1)"};
      transition: transform 0.18s ease, box-shadow 0.18s ease;
      position: relative;
      z-index: ${isSelected ? 10 : 1};
    `
    el.textContent = String(index + 1)

    // ── Popup content ──────────────────────────────────────────
    const wrap = document.createElement("div")
    wrap.style.cssText = `
      min-width: 200px; max-width: 260px;
      font-family: 'DM Sans', sans-serif;
    `

    // Header row: index badge + name
    const header = document.createElement("div")
    header.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:6px;"

    const badge = document.createElement("span")
    badge.textContent = String(index + 1)
    badge.style.cssText = `
      width:22px; height:22px; border-radius:50%;
      background:${color}; color:#fff;
      font-size:10px; font-weight:700;
      display:inline-flex; align-items:center; justify-content:center;
      flex-shrink:0;
    `

    const name = document.createElement("span")
    name.textContent = poi.name
    name.style.cssText = `
      font-size:13px; font-weight:700; line-height:1.3;
      color:#0f172a; flex:1;
    `

    header.appendChild(badge)
    header.appendChild(name)

    // Category pill
    const cat = document.createElement("span")
    cat.textContent = formatPOICategory(poi.category)
    cat.style.cssText = `
      display:inline-block;
      font-size:10px; font-weight:600;
      padding:2px 8px; border-radius:999px;
      background:${color}18; color:${color};
      margin-bottom:6px;
    `

    // Duration hint
    const dur = document.createElement("div")
    dur.style.cssText = "font-size:11px; color:#64748b; margin-bottom:6px; display:flex; align-items:center; gap:4px;"
    dur.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ~${poi.duration_suggested_minutes} min`

    // Narration
    if (poi.narration) {
      const body = document.createElement("div")
      body.textContent = poi.narration
      body.style.cssText = `
        font-size:11.5px; line-height:1.5; color:#475569;
        margin-bottom:10px;
        display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
      `
      wrap.appendChild(header)
      wrap.appendChild(cat)
      wrap.appendChild(dur)
      wrap.appendChild(body)
    } else {
      wrap.appendChild(header)
      wrap.appendChild(cat)
      wrap.appendChild(dur)
    }

    // Add to Route / Added indicator
    if (onAddWaypoint) {
      const divider = document.createElement("div")
      divider.style.cssText = "height:1px; background:#e2e8f0; margin-bottom:8px;"
      wrap.appendChild(divider)

      if (isAdded) {
        const addedBadge = document.createElement("span")
        addedBadge.style.cssText = `
          display:inline-flex; align-items:center; gap:5px;
          font-size:11px; font-weight:600;
          padding:5px 12px; border-radius:7px;
          background:#dcfce7; color:#16a34a;
        `
        addedBadge.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg> Added to Route`
        wrap.appendChild(addedBadge)
      } else {
        const btn = document.createElement("button")
        btn.type = "button"
        btn.style.cssText = `
          display:inline-flex; align-items:center; gap:5px;
          font-size:11px; font-weight:700;
          padding:6px 14px; border-radius:7px; border:none;
          background:#e63329; color:#fff; cursor:pointer;
          transition:opacity 0.15s;
          font-family:'DM Sans',sans-serif;
        `
        btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add to Route`
        btn.addEventListener("mouseenter", () => { btn.style.opacity = "0.85" })
        btn.addEventListener("mouseleave", () => { btn.style.opacity = "1" })
        btn.addEventListener("click", (e) => {
          e.stopPropagation()
          onAddWaypoint(poi.lng, poi.lat, poi.id)
        })
        wrap.appendChild(btn)
      }
    }

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      offset: 20,
      maxWidth: "280px",
      className: "poi-popup",
    }).setDOMContent(wrap)

    const onClick = (e: MouseEvent): void => {
      e.stopPropagation()
      onSelect(poi.id)
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }
    const onMouseEnter = (): void => {
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }
    const onMouseLeave = (): void => {
      if (!isSelected) popup.remove()
    }

    el.addEventListener("click", onClick)
    el.addEventListener("mouseenter", onMouseEnter)
    el.addEventListener("mouseleave", onMouseLeave)

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([poi.lng, poi.lat])
      .addTo(map)

    if (isSelected) {
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }

    return () => {
      el.removeEventListener("click", onClick)
      el.removeEventListener("mouseenter", onMouseEnter)
      el.removeEventListener("mouseleave", onMouseLeave)
      popup.remove()
      marker.remove()
    }
  }, [map, poi.category, poi.duration_suggested_minutes, poi.id, poi.lat, poi.lng, poi.name, poi.narration, index, onSelect, isSelected, onAddWaypoint, isAdded])

  return null
}
