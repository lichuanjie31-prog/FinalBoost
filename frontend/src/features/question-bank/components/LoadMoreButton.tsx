export function LoadMoreButton({ hasMore, loading, onClick }: { hasMore: boolean; loading: boolean; onClick: () => void }) {
  if (!hasMore) return null
  return <div className="qb-load-more"><button className="button button-secondary button-small" disabled={loading} onClick={onClick}>{loading ? '正在加载…' : '加载更多'}</button></div>
}
