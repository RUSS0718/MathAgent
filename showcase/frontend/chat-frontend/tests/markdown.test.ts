import test from 'node:test'
import assert from 'node:assert/strict'
import { renderSafeMarkdown } from '../src/renderers/markdown-adapter.ts'

test('renders math delimiters as safe readable spans and escapes html', () => {
  const output = renderSafeMarkdown('面积 $x^2$\n$$\\begin{pmatrix}1&2\\end{pmatrix}$$ <script>alert(1)</script>')
  assert.match(output, /math-inline/)
  assert.match(output, /math-block/)
  assert.doesNotMatch(output, /<script>/)
})
