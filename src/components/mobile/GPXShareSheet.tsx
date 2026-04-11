import { X, Download, Share2 } from "lucide-react"

interface GPXShareSheetProps {
  blob: Blob
  filename: string
  onClose: () => void
}

// Apps that support GPX import on iOS/Android.
// Each entry supplies a URL scheme — tapping opens the app (if installed)
// after the file has been downloaded to the device.
const APPS = [
  { name: "OsmAnd", desc: "Offline maps & navigation", scheme: "osmandmaps://", emoji: "🗺️" },
  { name: "Organic Maps", desc: "Free offline hiking & cycling", scheme: "organicmaps://", emoji: "🌿" },
  { name: "Komoot", desc: "Outdoor route planning", scheme: "komoot://", emoji: "🚵" },
  { name: "AllTrails", desc: "Trail maps & navigation", scheme: "alltrails://", emoji: "🥾" },
  { name: "Gaia GPS", desc: "Backcountry navigation", scheme: "gaiagps://", emoji: "🧭" },
]

export function GPXShareSheet({ blob, filename, onClose }: GPXShareSheetProps): JSX.Element {
  const downloadBlob = () => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleAppTap = (scheme: string) => {
    // Download the file first, then open the app after a short delay so iOS
    // has time to save the file to Files before the app switch.
    downloadBlob()
    setTimeout(() => { window.location.href = scheme }, 700)
    onClose()
  }

  const handleSystemShare = async () => {
    const file = new File([blob], filename, { type: "application/gpx+xml" })
    try {
      await navigator.share({ files: [file], title: filename })
    } catch (e) {
      if ((e as DOMException).name !== "AbortError") downloadBlob()
    }
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60"
        onClick={onClose}
      />

      {/* Sheet */}
      <div
        className="fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl"
        style={{ background: "var(--surface)", paddingBottom: "env(safe-area-inset-bottom, 16px)" }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <p className="text-sm font-semibold" style={{ color: "var(--fg)" }}>Open GPX with…</p>
          <button onClick={onClose} className="p-1 rounded-lg" style={{ color: "var(--fg-muted)" }}>
            <X size={18} />
          </button>
        </div>

        <p className="px-5 pt-3 pb-1 text-xs" style={{ color: "var(--fg-muted)" }}>
          GPX downloads to your device. Open the app and import from Files.
        </p>

        {/* App list */}
        <div className="px-3 pt-1 pb-2 flex flex-col">
          {APPS.map((app) => (
            <button
              key={app.name}
              onClick={() => handleAppTap(app.scheme)}
              className="flex items-center gap-3 px-3 py-3 rounded-xl text-left active:opacity-70 transition-opacity"
            >
              <span className="text-2xl w-9 text-center leading-none">{app.emoji}</span>
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--fg)" }}>{app.name}</p>
                <p className="text-xs" style={{ color: "var(--fg-muted)" }}>{app.desc}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Divider + fallbacks */}
        <div className="px-3 pt-1 pb-3 flex flex-col" style={{ borderTop: "1px solid var(--border)" }}>
          {typeof navigator.share === "function" && (
            <button
              onClick={() => void handleSystemShare()}
              className="flex items-center gap-3 px-3 py-3 rounded-xl text-left active:opacity-70 transition-opacity"
            >
              <span
                className="flex w-9 h-9 items-center justify-center rounded-full shrink-0"
                style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
              >
                <Share2 size={16} />
              </span>
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--fg)" }}>More apps…</p>
                <p className="text-xs" style={{ color: "var(--fg-muted)" }}>Open system share sheet</p>
              </div>
            </button>
          )}

          <button
            onClick={() => { downloadBlob(); onClose() }}
            className="flex items-center gap-3 px-3 py-3 rounded-xl text-left active:opacity-70 transition-opacity"
          >
            <span
              className="flex w-9 h-9 items-center justify-center rounded-full shrink-0"
              style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
            >
              <Download size={16} />
            </span>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--fg)" }}>Download GPX</p>
              <p className="text-xs" style={{ color: "var(--fg-muted)" }}>Save file to device</p>
            </div>
          </button>
        </div>
      </div>
    </>
  )
}
