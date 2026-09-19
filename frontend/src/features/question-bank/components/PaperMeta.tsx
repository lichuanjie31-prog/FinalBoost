import { Building2, CalendarDays, FileSpreadsheet } from 'lucide-react'

export function PaperMeta({ college, year, semester, fileSize }: { college: string; year: number; semester: string; fileSize?: number }) {
  return <div className="qb-paper-meta">
    <span><Building2 size={14} />{college}</span>
    <span><CalendarDays size={14} />{year} · {semester}</span>
    {fileSize !== undefined && <span><FileSpreadsheet size={14} />{formatSize(fileSize)}</span>}
  </div>
}

export function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`
  return `${(size / 1024 / 1024).toFixed(1)} MiB`
}
