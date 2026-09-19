import type { PublicationStatus } from '../../../api/questionBank'

const labels: Record<PublicationStatus, string> = { draft: '草稿', published: '已发布', unpublished: '已下架' }

export function PaperStatusBadge({ status }: { status: PublicationStatus }) {
  return <span className={`qb-status qb-status-${status}`}>{labels[status]}</span>
}
