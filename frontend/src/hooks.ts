import { useCallback, useEffect, useState } from 'react'

/** Minimal data-loading hook: returns data, loading state, error, and a reload function. */
export function useLoad<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    loader()
      .then(setData)
      .catch((loadError: Error) => setError(loadError.message))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies)

  useEffect(() => {
    reload()
  }, [reload])

  return { data, error, loading, reload, setData }
}
