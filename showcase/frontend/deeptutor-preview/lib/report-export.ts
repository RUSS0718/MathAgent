export function downloadReport(title: string, markdown: string) {
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = title + '.md'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
