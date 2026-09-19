import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

/**
 * 助手回答的渲染：Markdown + LaTeX。
 *
 * 模型回复里同时有标题、列表、强调与 `$...$` / `$$...$$` 公式，按纯文本展示会把
 * 标记符号原样露出来。这里用 react-markdown：它默认**不解析原始 HTML**，
 * 所以模型输出不会被当成 HTML 注入；公式交给 KaTeX 排版。
 *
 * KaTeX 的 throwOnError 关掉：模型偶尔会写出不合法或非标准的 LaTeX，
 * 那种情况应该把那一小段标红继续显示，而不是让整条回答渲染失败。
 */
export function Markdown({ children }: { children: string }) {
  return <ReactMarkdown
    remarkPlugins={[remarkGfm, remarkMath]}
    rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
    components={{
      // 模型给的链接一律新标签打开，且不带 referrer / 不交出 window.opener
      a: ({ children: text, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{text}</a>,
    }}
  >{children}</ReactMarkdown>
}
