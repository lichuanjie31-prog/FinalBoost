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
        <h2>下一次考试，<br />从这里开始</h2>
        <p>从一份试卷出发，找到复习的方向。</p>
        <Link className="button" to="/register">开始使用 FinalBoost<ArrowUpRight size={17} /></Link>
      </div>
      <div className="footer-bottom">
        <Brand />
        <span className="footer-copy">把每一步复习，变得更有方向</span>
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
