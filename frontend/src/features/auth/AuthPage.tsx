import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { Brand, ErrorMessage } from '../../components/Shared'
import { safeNext, useAuth } from '../../app/auth'
import type { AuthResult } from '../../api/study'
import { post } from '../../api/client'

export function AuthPage({ register = false }: { register?: boolean }) {
  const [params] = useSearchParams(), navigate = useNavigate(), auth = useAuth()
  const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('')
  const [show, setShow] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const next = safeNext(params.get('next'))
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (register && password !== confirmation) { setError('两次输入的密码不一致，请重新确认。'); return }
    setBusy(true)
    try {
      const result = await post<AuthResult>(register ? '/auth/register' : '/auth/login', { username, password })
      auth.accept(result.accessToken, result.user); navigate(next, { replace: true })
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <div className="auth-layout">
    <aside className="auth-story">
      <Brand />
      <div className="auth-story-copy">
        <span className="eyebrow">ONE STEP CLOSER</span>
        <h1>复习的方向，<br />从这里变清晰。</h1>
        <p>把目标写下来。<br />从一份试卷开始，找到下一步。</p>
        <div className="auth-path">
          <span>01 摸底诊断</span>
          <span>02 专项训练 · 规划中</span>
          <span>03 最终模拟 · 规划中</span>
        </div>
      </div>
      <small>FinalBoost · 期末备考助手</small>
    </aside>
    <main id="main" tabIndex={-1} className="auth-main">
      <Link to="/" className="text-link back-link"><ArrowLeft size={16} />返回首页</Link>
      <div className="auth-form-wrap">
        <div className="mobile-brand"><Brand /></div>
        <span className="eyebrow">{register ? '开始新的备考计划' : '接着上次的进度'}</span>
        <h2>{register ? '创建你的账号' : '欢迎回来'}</h2>
        <p className="muted">{register ? '保存目标与记录，让每次复习有所积累。' : '登录账号，继续你的备考计划。'}</p>
        <form onSubmit={submit} className="form-stack">
          <label>用户名<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_]+" placeholder="3 至 32 位字母、数字或下划线" /></label>
          <label>密码<div className="password-field"><input type={show ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} required minLength={10} maxLength={128} placeholder="至少 10 位字符" /><button type="button" className="icon-button" aria-label={show ? '隐藏密码' : '显示密码'} onClick={() => setShow(!show)}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>
          {register && <label>确认密码<input type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required minLength={10} maxLength={128} placeholder="再输入一次密码" /></label>}
          <ErrorMessage error={error} />
          <button className="button full-width" disabled={busy}>{busy ? '正在提交…' : register ? '创建账号' : '登录'}{!busy && <ArrowRight size={18} />}</button>
        </form>
        <p className="auth-switch">{register ? '已有账号？' : '还没有账号？'}<Link to={`${register ? '/login' : '/register'}?next=${encodeURIComponent(next)}`}>{register ? '去登录' : '创建账号'}</Link></p>
        <div className="privacy-note"><ShieldCheck size={15} />你的备考记录仅对自己的账号开放</div>
      </div>
    </main>
  </div>
}
