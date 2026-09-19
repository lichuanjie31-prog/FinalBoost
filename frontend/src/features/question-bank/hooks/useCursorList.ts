import { useCallback, useEffect, useRef, useState } from 'react'
import type { Page } from '../../../api/questionBank'

export function useCursorList<T>(loader: (cursor: string | null, signal: AbortSignal) => Promise<Page<T>>) {
  const [items, setItems] = useState<T[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const moreController = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    moreController.current?.abort()
    setLoading(true); setError(''); setItems([]); setNextCursor(null)
    loader(null, controller.signal)
      .then(page => { if (!controller.signal.aborted) { setItems(page.items); setNextCursor(page.nextCursor || null) } })
      .catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [loader, version])

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return
    const controller = new AbortController(); moreController.current = controller
    setLoadingMore(true); setError('')
    try {
      const page = await loader(nextCursor, controller.signal)
      if (!controller.signal.aborted) {
        setItems(current => [...current, ...page.items])
        setNextCursor(page.nextCursor || null)
      }
    } catch (error) {
      if (!controller.signal.aborted) setError((error as Error).message)
    } finally {
      if (!controller.signal.aborted) setLoadingMore(false)
    }
  }, [loader, loadingMore, nextCursor])

  return { items, setItems, nextCursor, loading, loadingMore, error, reload: () => setVersion(value => value + 1), loadMore }
}
