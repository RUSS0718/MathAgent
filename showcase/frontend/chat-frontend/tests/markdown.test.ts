import test from 'node:test'
import assert from 'node:assert/strict'
import { renderSafeMarkdown } from '../src/renderers/markdown-adapter.ts'

test('renders math with KaTeX and escapes html', () => {
  const output = renderSafeMarkdown('面积 $x^2$\n$$\\begin{pmatrix}1&2\\end{pmatrix}$$ <script>alert(1)</script>')
  assert.match(output, /katex/)
  assert.doesNotMatch(output, /<script>/)
})
