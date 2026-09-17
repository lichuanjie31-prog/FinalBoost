import { Link } from 'react-router-dom'
import { ArrowRight, Target } from 'lucide-react'
import { EmptyState, MockNotice } from '../../components/Shared'

export function Training() {
  return <>
    <div className="workspace-title">
      <div>
        <span className="eyebrow">02 / TRAINING</span>
        <h1>专项训练</h1>
        <p>按知识点拆分的针对性练习，针对诊断出的薄弱点反复刷题。</p>
      </div>
    </div>
    <MockNotice />
    <EmptyState>
      <Target size={36} />
      <h2>规划中</h2>
      <p>与最终模拟共用题库与判卷服务，预计下一个迭代上线。届时会根据「摸底诊断」与「最终模拟」的薄弱知识点自动生成训练计划。</p>
      <Link className="button button-quiet" to="/app/mock">先去最终模拟<ArrowRight size={17} /></Link>
    </EmptyState>
  </>
}