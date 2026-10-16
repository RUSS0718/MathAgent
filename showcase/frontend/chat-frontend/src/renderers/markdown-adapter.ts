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
  return withMath.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, url: string) => {
    if (!/^(https?:|mailto:)/i.test(url)) return label
    return `<a href="${url}" rel="noreferrer noopener">${label}</a>`
  }).replace(/\n/g, '<br>')
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
