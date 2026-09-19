import { useEffect, useState } from 'react'
import { questionBank, type Subject } from '../../../api/questionBank'

export function useSubjects() {
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    async function load() {
      const all: Subject[] = []; let cursor: string | null = null
      do {
        const page = await questionBank.subjects('', cursor, controller.signal)
        all.push(...page.items); cursor = page.nextCursor || null
      } while (cursor && !controller.signal.aborted)
      if (!controller.signal.aborted) setSubjects(all)
    }
    load().catch(error => { if (!controller.signal.aborted) setError(error.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [version])
  return { subjects, setSubjects, loading, error, reload: () => setVersion(value => value + 1) }
}
