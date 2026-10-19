import test from 'node:test'
import assert from 'node:assert/strict'
import { renderSafeMarkdown } from '../src/renderers/markdown-adapter.ts'

test('renders math with KaTeX and escapes html', () => {
  const output = renderSafeMarkdown('面积 $x^2$\n$$\\begin{pmatrix}1&2\\end{pmatrix}$$ <script>alert(1)</script>')
  assert.match(output, /katex/)
  assert.doesNotMatch(output, /<script>/)
})

test('renders readable markdown blocks without leaking markdown syntax', () => {
  const output = renderSafeMarkdown('## 答案\n\n**结论：** `x = 1`\n\n- 代入检验\n- 定义域有效')
  assert.match(output, /<h2>答案<\/h2>/)
  assert.match(output, /<strong>结论：<\/strong>/)
  assert.match(output, /<code>x = 1<\/code>/)
  assert.match(output, /<ul>[\s\S]*<li>代入检验<\/li>/)
  assert.doesNotMatch(output, /\*\*结论：\*\*/)
})
