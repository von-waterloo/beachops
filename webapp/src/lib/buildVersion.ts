const STORAGE_KEY = 'beachops-build-id'

/** Reload when server build-id changed (Telegram WebView caches index.html). */
export async function ensureFreshWebappBuild(): Promise<void> {
  try {
    const res = await fetch('/build-id.txt', { cache: 'no-store' })
    if (!res.ok) return
    const id = (await res.text()).trim()
    if (!id) return
    const prev = localStorage.getItem(STORAGE_KEY)
    if (prev && prev !== id) {
      localStorage.setItem(STORAGE_KEY, id)
      window.location.reload()
      return
    }
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Dev / offline — skip.
  }
}
