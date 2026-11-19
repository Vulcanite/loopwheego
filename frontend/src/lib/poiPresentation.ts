const CATEGORY_COLORS: Record<string, string> = {
  parks: "#22c55e",
  waterfront: "#06b6d4",
  neighbourhoods: "#f59e0b",
  monuments: "#f97316",
  museums: "#8b5cf6",
  viewpoints: "#3b82f6",
  cafes: "#ec4899",
  markets: "#eab308",
  "tourism:attraction": "#f59e0b",
  "tourism:museum": "#8b5cf6",
  "tourism:viewpoint": "#06b6d4",
  "leisure:park": "#22c55e",
  "amenity:cafe": "#ec4899",
  poi: "#6b7280",
}

const CATEGORY_LABELS: Record<string, string> = {
  parks: "Parks",
  waterfront: "Waterfront",
  neighbourhoods: "Neighbourhoods",
  monuments: "Monuments",
  museums: "Museums",
  viewpoints: "Viewpoints",
  cafes: "Cafes",
  markets: "Markets",
}

export function getPOICategoryColor(category: string): string {
  if (CATEGORY_COLORS[category]) return CATEGORY_COLORS[category]
  for (const [key, color] of Object.entries(CATEGORY_COLORS)) {
    if (category.includes(key)) return color
  }
  return "#6b7280"
}

export function formatPOICategory(category: string): string {
  if (CATEGORY_LABELS[category]) return CATEGORY_LABELS[category]
  return category
    .replace(/^(tourism:|historic:|leisure:|amenity:|natural:)/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
}
