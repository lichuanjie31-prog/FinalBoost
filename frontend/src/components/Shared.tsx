import { ArrowUpRight, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

export function Brand() {
  return <Link to="/" className="brand" aria-label="FinalBoost 首页">
    <span className="brand-icon"><Zap size={16} fill="currentColor" /></span>
    Final<span>Boost</span>
  </Link>
}

export function Footer() {
  return <footer className="home-footer">
    <div className="footer-inner page-width">
      <div className="footer-cta">
        <span className="eyebrow">YOUR NEXT STEP, CLEARER</span>
        <h2>从正在备考的那门课，<br />开始了解自己的学习。</h2>
        <p>记下考试目标，带上你的第一份作答。</p>
        <Link className="button" to="/register">开始使用 FinalBoost<ArrowUpRight size={17} /></Link>
      </div>
      <div className="footer-bottom">
        <Brand />
        <span className="footer-copy">把时间留给理解与内化</span>
        <small>FinalBoost · 期末备考助手</small>
      </div>
    </div>
  </footer>
}

export function ErrorMessage({ error }: { error: string }) {
  return error ? <div role="alert" className="error-message">{error}</div> : null
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>
}

export function Arrow() {
  return <ArrowUpRight size={17} aria-hidden="true" />
}

export function MockNotice() {
  return <div className="mock-notice">模拟数据，仅用于流程联调</div>
}
