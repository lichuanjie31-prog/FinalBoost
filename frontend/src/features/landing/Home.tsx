import { Link } from 'react-router-dom'
import { ArrowRight, ScanLine, BookOpen, Target, FileText, CircleCheck, Sparkles, Check } from 'lucide-react'
import { Brand, Footer } from '../../components/Shared'
import { useAuth } from '../../app/auth'

export function Home() {
  const { user } = useAuth()
  return <>
    {/* Navbar */}
    <header className="home-nav">
      <div className="nav-inner">
        <Brand />
        <nav className="nav-links" aria-label="主导航">
          <a href="#how">备考路径</a>
          <a href="#faq">常见问题</a>
        </nav>
        <div className="nav-actions">
          <Link className="button button-small" to={user ? '/app' : '/login'}>{user ? '我的备考' : '开始使用'}<ArrowRight size={16} /></Link>
        </div>
      </div>
    </header>

    <main id="main" tabIndex={-1}>
      {/* Hero */}
      <section className="hero">
        <div className="hero-inner page-width">
          <div className="hero-content">
            <h1 className="hero-title" aria-label="把有限的时间，用在值得复习的地方。">把有限的时间，<br />用在<span className="hero-accent">值得复习</span><br />的地方。</h1>
            <p className="hero-desc">从一份试卷出发，看清薄弱知识点。<br />整理目标、逐步复习，让考前的每一天都有方向。</p>
            <div className="hero-actions">
              <Link className="button" to={user ? '/app' : '/login?next=%2Fapp'}>开始我的备考<ArrowRight size={18} /></Link>
              <a className="text-link" href="#preview">先看看诊断示例</a>
            </div>
          </div>
          <div className="hero-visual">
            <div className="preview-card" id="preview">
              <div className="preview-header">
                <div className="preview-tag"><span className="tag">示例诊断</span></div>
                <span className="eyebrow">FINALBOOST / REPORT</span>
              </div>
              <h2 className="preview-title">一次诊断，看清复习方向</h2>
              <div className="preview-score-row">
                <div>
                  <span className="preview-score-label">本次示例得分</span>
                  <div className="preview-score-num">63<small>/ 100</small></div>
                </div>
                <div className="preview-score-circle">
                  <ScanLine size={24} />
                  <span>诊断完成</span>
                </div>
              </div>
              <div className="preview-divider" />
              <div className="preview-col-labels">
                <span>知识点</span><span>得分率</span>
              </div>
              {([['链表', 100, 'teal'], ['二叉树遍历', 60, 'blue'], ['Dijkstra', 33.3, 'amber'], ['排序', 72, 'blue']] as [string, number, string][]).map(([name, score, color]) => (
                <div className="preview-row" key={name}>
                  <span>{name}</span>
                  <div className="progress-track"><span className={`fill-${color}`} style={{ width: `${score}%` }} /></div>
                  <strong>{score}%</strong>
                </div>
              ))}
              <div className="preview-insight">
                <Sparkles size={16} />
                <div>
                  <strong>下一步，先梳理最短路径</strong>
                  <p>从松弛操作开始，重走一次解题过程。</p>
                </div>
              </div>
              <div className="preview-disclaimer">人工构造的示例数据，不代表真实评估结果</div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="section-dark page-width">
        <div className="section-label">
          <span className="label-num">01</span>
          <span className="label-text">备考路径</span>
        </div>
        <h2 className="section-heading">从"该复习什么"，<br />走向"知道下一步"。</h2>
        <p className="section-desc">把备考拆成三个阶段。现在，从第一份试卷诊断开始。</p>
        <div className="steps-grid">
          <article className="step-card step-active">
            <span className="step-num">01</span>
            <h3>摸底诊断</h3>
            <p>上传答题照片，查看逐题结果，整理需要重新理解的知识点。</p>
            <div className="step-bottom">
              <span className="tag">当前可体验 · 模拟判卷</span>
              <ArrowRight size={18} />
            </div>
          </article>
          <article className="step-card">
            <span className="step-num">02</span>
            <h3>专项训练</h3>
            <p>围绕薄弱知识点逐步练习，在方法理解和具体题目之间建立联系。</p>
            <div className="step-bottom">
              <span className="tag tag-muted">规划中</span>
            </div>
          </article>
          <article className="step-card">
            <span className="step-num">03</span>
            <h3>最终模拟</h3>
            <p>通过完整模拟检验复习成果，在考前回看自己的掌握情况。</p>
            <div className="step-bottom">
              <span className="tag tag-muted">规划中</span>
            </div>
          </article>
        </div>
        <div className="section-tagline">
          KNOW YOUR WEAK POINTS. REVIEW WITH DIRECTION. IMPROVE WITH EVERY SESSION.
        </div>
      </section>

      {/* CTA */}
      <section className="cta-section page-width">
        <div className="section-label">
          <span className="label-num">02</span>
          <span className="label-text">开始备考</span>
        </div>
        <h2 className="section-heading">先给下一场考试，<br />定一个目标。</h2>
        <p className="section-desc">创建账号，保存你的备考计划与诊断记录。</p>
        <Link className="button" to={user ? '/app' : '/register'}>创建备考计划<ArrowRight size={18} /></Link>
      </section>

      {/* FAQ */}
      <section id="faq" className="section-dark page-width">
        <div className="section-label">
          <span className="label-num">03</span>
          <span className="label-text">常见问题</span>
        </div>
        <h2 className="section-heading">你可能想问</h2>
        <div className="faq-list">
          <details>
            <summary><span className="faq-num">01</span>现在可以使用哪些功能？</summary>
            <p>你可以注册账号、创建考试任务、上传答题图片，并体验模拟判卷与示例诊断。专项训练、AI 对话和最终模拟仍在规划中。</p>
          </details>
          <details>
            <summary><span className="faq-num">02</span>诊断分数是真实批改的结果吗？</summary>
            <p>当前判卷使用固定的四道示例题，只用于体验流程，不分析上传图片中的作答，也不代表你的真实成绩或掌握度。</p>
          </details>
          <details>
            <summary><span className="faq-num">03</span>我的备考记录会保存吗？</summary>
            <p>登录后创建的考试、上传文件和诊断记录会保存在当前部署的服务端。你只能访问自己账号下的记录。</p>
          </details>
        </div>
      </section>
    </main>
    <Footer />
  </>
}
