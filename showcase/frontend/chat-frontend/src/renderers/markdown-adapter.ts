/** Minimal safe markdown boundary: raw HTML and dangerous links are escaped. */
export function renderSafeMarkdown(value: string): string {
  const escaped = value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character))
  const withMath = escaped.replace(/\$\$([\s\S]+?)\$\$/g, '<div class="math-block" role="math">$1</div>').replace(/\$([^$\n]+)\$/g, '<span class="math-inline" role="math">$1</span>')
  return withMath.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, url: string) => {
    if (!/^(https?:|mailto:)/i.test(url)) return label
    return `<a href="${url}" rel="noreferrer noopener">${label}</a>`
  }).replace(/\n/g, '<br>')
}
