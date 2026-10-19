import katex from 'katex'

/** Safe markdown boundary with KaTeX math and allowlisted links. */
export function renderSafeMarkdown(value: string): string {
  const math: string[] = []
  const protectedText = value.replace(/\$\$([\s\S]+?)\$\$|\$([^$\n]+)\$/g, (_match, block: string | undefined, inline: string | undefined) => {
    const source = block ?? inline ?? ''
    const displayMode = block !== undefined
    const rendered = renderMath(source, displayMode)
    const index = math.push(rendered) - 1
    return `\u0000MATH${index}\u0000`
  })
  const escaped = escapeHtml(protectedText)
  const withMath = escaped.replace(/\u0000MATH(\d+)\u0000/g, (_match, index: string) => math[Number(index)] ?? '')
  return renderBlocks(withMath)
}

function renderBlocks(value: string): string {
  const output: string[] = []
  let paragraph: string[] = []
  let list: string[] = []
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${paragraph.join('<br>')}</p>`)
    paragraph = []
  }
  const flushList = () => {
    if (list.length) output.push(`<ul>${list.map((item) => `<li>${renderInline(item)}</li>`).join('')}</ul>`)
    list = []
  }
  for (const line of value.split(/\r?\n/)) {
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    const item = line.match(/^\s*[-*]\s+(.+)$/)
    if (!line.trim()) {
      flushParagraph()
      flushList()
    } else if (heading) {
      flushParagraph()
      flushList()
      const level = heading[1]?.length ?? 1
      output.push(`<h${level}>${renderInline(heading[2] ?? '')}</h${level}>`)
    } else if (item) {
      flushParagraph()
      list.push(item[1] ?? '')
    } else {
      flushList()
      paragraph.push(renderInline(line))
    }
  }
  flushParagraph()
  flushList()
  return output.join('')
}

function renderInline(value: string): string {
  let rendered = value
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
  rendered = rendered.replace(/\[([^\]]+)\]\(((?:https?:|mailto:)[^)\s]+)\)/gi, (_match, label: string, url: string) => (
    `<a href="${url}" rel="noreferrer noopener">${label}</a>`
  ))
  return rendered
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character))
}

function renderMath(source: string, displayMode: boolean): string {
  try {
    return katex.renderToString(source, { displayMode, throwOnError: false, trust: false, strict: 'ignore' })
  } catch {
    return `<span class="math-fallback" role="math">${escapeHtml(source)}</span>`
  }
}
