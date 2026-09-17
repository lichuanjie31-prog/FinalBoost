import { Link } from 'react-router-dom'
import { ArrowDown, ArrowRight, BookOpen, Check, FileText, Sparkles } from 'lucide-react'
import { Brand, Footer } from '../../components/Shared'
import { useAuth } from '../../app/auth'

const steps = [
  { title: '用一份真题摸底', text: '从自己的课程出发，完成一份试卷。让具体的作答成为了解学习状态的起点。', note: '起点 · 真题测试' },
  { title: '找到卡住的知识点', text: '结合批改结果看清错在哪里，继续追问解题过程，把没有理解的那一步弄明白。', note: '理解 · 批改与答疑' },
  { title: '针对薄弱处再练一次', text: '根据错题筛选同类练习，组成个人专项训练卷。计划支持 PDF 下载，方便打印后作答。', note: '巩固 · 个性化训练' },
  { title: '检验这次是否真的学会', text: '再次提交作答，回看变化，再用完整模拟检验复习效果，让下一轮复习有据可依。', note: '回看 · 检测与模拟' },
]

export function Home() {
  const { user } = useAuth()
  const start = user ? '/app' : '/login?next=%2Fapp'
  return <div className="landing-page">
    <header className="home-nav"><div className="nav-inner">
      <Brand />
      <nav className="nav-links" aria-label="主导航"><a href="#story">为什么做</a><a href="#how">学习路径</a><a href="#agent">AI 学习伙伴</a><a href="#faq">常见问题</a></nav>
      <div className="nav-actions"><Link className="button button-small" to={start}>{user ? '我的备考' : '开始使用'}<ArrowRight size={16} /></Link></div>
    </div></header>
    <main id="main" tabIndex={-1}>
      <section className="learning-hero">
        <div className="hero-paper paper-left" aria-hidden="true">
          <span className="paper-kicker">我的备考 / 高等数学</span><BookOpen size={22} />
          <strong>把零散的知识，<br />重新串起来。</strong><div className="paper-rule" /><div className="paper-rule short" />
          <span className="paper-foot">课程 · 真题 · 学习记录</span>
        </div>
        <div className="hero-paper paper-right" aria-hidden="true">
          <span className="paper-kicker">下一步 / 专项训练</span><span className="paper-formula">∫ f(x) dx</span>
          <strong>这一次，练明白<br />还没掌握的部分。</strong><span className="paper-foot">理解 → 练习 → 再次检测</span>
        </div>
        <div className="learning-hero-copy page-width">
          <span className="hero-kicker"><span />从期末备考开始的 AI 学习 Agent</span>
          <h1 aria-label="把时间留给真正学懂的那一刻。">把时间留给<br /><span>真正学懂的那一刻。</span></h1>
          <p>找真题、对答案、整理错题，已经占去了太多复习时间。<br className="desktop-break" />我们希望让 AI 接住这些重复工作，陪你发现薄弱点，把知识学扎实。</p>
          <div className="hero-actions"><Link className="button" to={start}>开始我的备考<ArrowRight size={18} /></Link><a className="text-link" href="#how">了解学习路径<ArrowDown size={16} /></a></div>
          <span className="hero-availability">我的备考已开放体验 · 个性化 Agent 能力持续建设中</span>
        </div>
        <a className="hero-scroll" href="#story">一个来自真实备考经历的想法<ArrowDown size={16} /></a>
      </section>

      <section id="story" className="landing-section page-width story-section">
        <div>
          <div className="section-label"><span className="label-text">项目缘起</span><span className="eyebrow">WHY FINALBOOST</span></div>
          <h2 className="section-heading">复习的时间，<br />有多少花在了学习上？</h2>
          <p className="section-desc">一学期听过的课、记过的笔记，到了期末需要重新串起来。可真正开始复习之前，往往还有一长串准备工作。</p>
          <div className="study-fragments" aria-label="复习中的重复工作"><span>到处找真题</span><span>翻答案、自己批改</span><span>整理错题</span><span>逐题拍照问 AI</span><span>再找同类练习</span></div>
        </div>
        <aside className="founder-note">
          <span className="eyebrow">来自发起人的高数复习经历</span>
          <p>平时跟着老师上课、做笔记，大部分知识点都有印象。到了期末，才发现大量时间花在了找卷、找答案、整理错题，再一道一道问 AI 上。</p>
          <p>集中练真题、针对薄弱点复习，帮助我取得了更好的成绩。也正是这段经历，让我想把这些分散的步骤接起来。</p>
          <div className="founder-note-end">少一些重复操作，多一些理解与内化。<span>FinalBoost 的起点</span></div>
        </aside>
      </section>

      <section id="how" className="learning-path-band"><div className="landing-section page-width">
        <div className="section-label"><span className="label-text">我们正在连接的学习路径</span><span className="tag tag-muted">产品规划</span></div>
        <h2 className="section-heading">每次练习之后，<br />都知道下一步该做什么。</h2>
        <p className="section-desc">从一份真题开始，逐步看清薄弱点。把讲解、训练和再次检测接在一起，让每一轮复习都有反馈。</p>
        <ol className="learning-steps">{steps.map((step, index) => <li key={step.title}><span className="learning-step-number">0{index + 1}</span><h3>{step.title}</h3><p>{step.text}</p><span className="learning-step-note">{step.note}</span></li>)}</ol>
        <p className="path-status">当前可体验创建考试、上传答题图片与诊断流程。真题库、AI 答疑、专项训练及最终模拟正在建设中。</p>
      </div></section>

      <section id="agent" className="landing-section page-width agent-section">
        <div className="agent-intro">
          <div className="section-label"><span className="label-text">AI 学习伙伴</span><span className="tag tag-muted">规划中</span></div>
          <h2 className="section-heading">带着你的学习记录，<br />一起想下一步。</h2>
          <p className="section-desc">我们希望，你每次提问时，都不必重新解释自己在学什么、哪里容易错。Agent 能结合你的课程、作答和交流记录，给出有依据的建议。</p>
          <ul className="agent-values">
            <li><Check size={17} /><span><strong>记得你练过什么</strong>课程、历史作答与错题共同构成学习上下文。</span></li>
            <li><Check size={17} /><span><strong>说明为什么这样安排</strong>把建议对应到具体错题和待巩固的知识点。</span></li>
            <li><Check size={17} /><span><strong>把建议接到下一次练习</strong>检索相关题目，生成专项训练，再根据新作答调整。</span></li>
          </ul>
        </div>
        <div className="agent-preview" id="preview">
          <div className="agent-preview-top"><span><Sparkles size={16} />FinalBoost AI</span><span className="tag tag-muted">交互示意</span></div>
          <div className="agent-context"><BookOpen size={14} />高等数学 / 我的备考</div>
          <div className="example-message">定积分还是不太熟，接下来该怎么练？</div>
          <div className="example-reply"><span className="agent-avatar"><Sparkles size={16} /></span><p>可以先回看定积分的错题，找出具体卡住的步骤，再选同类题巩固。每一组练习，都围绕还没理解的部分展开。</p></div>
          <div className="agent-example-steps"><span><i />回看作答记录</span><span><i />定位薄弱知识点</span><span><i />筛选对应练习</span></div>
          <div className="training-example"><FileText size={24} /><div><strong>定积分专项训练</strong><span>目标产出 · 可打印的个人练习卷</span></div><ArrowRight size={17} /></div>
          <p className="example-caption">规划体验示意，展示内容为人工编写。</p>
        </div>
      </section>

      <section className="learning-belief-band"><div className="landing-section page-width belief-content">
        <span className="eyebrow">FINAL + BOOST</span>
        <h2>从一场期末考试，<br />走向更了解自己的学习。</h2>
        <p>期末备考是我们的起点。更长远的目标，是让每次练习和每次提问逐渐汇成个人的知识掌握画像，帮助你形成自主复习、针对训练的习惯。</p>
        <span className="belief-footnote">让 AI 分担重复工作，让理解发生在你自己身上。</span>
      </div></section>

      <section id="faq" className="landing-section page-width landing-faq">
        <div><div className="section-label"><span className="label-text">开始之前</span></div><h2 className="section-heading">你可能想问</h2></div>
        <div className="faq-list">
          <details><summary>现在可以体验哪些功能？</summary><p>目前已开放账号注册登录、我的备考、考试目标与答题图片上传，以及判卷和诊断流程。独立 AI 对话、真题库、个性化专项训练、PDF 导出和最终模拟仍在建设中。</p></details>
          <details><summary>诊断结果可以怎样使用？</summary><p>请先留意结果页面的数据来源。标注为模拟的数据仅用于体验流程，不代表你的实际成绩。AI 分析也可能出错，复习时应结合原题、标准答案和老师的讲解核对。</p></details>
          <details><summary>可以继续用纸笔做题吗？</summary><p>可以，当前流程支持上传纸面作答的图片。我们也计划让专项训练卷支持 PDF 下载和打印，保留熟悉的纸笔练习方式。</p></details>
          <details><summary>可以上传哪些学习资料？</summary><p>请仅上传自己有权使用的资料。公共题库将以获得授权、学校或教师许可使用，以及符合开放许可的资源为建设原则，保留相应来源信息。</p></details>
          <details><summary>我们怎样看待 AI 与学习？</summary><p>AI 可以辅助分析、答疑和安排练习，理解知识仍需要你亲自思考和作答。FinalBoost 面向日常学习与考前复习，请遵守学校的考试和学术诚信要求。</p></details>
        </div>
      </section>
    </main>
    <Footer />
  </div>
}
