import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(new URL('../scripts/check-npm-audit.mjs', import.meta.url))
const advisory = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf'

test('only the approved development advisory can pass the high audit gate', t => {
  const dir = mkdtempSync(join(tmpdir(), 'mathagent-audit-'))
  t.after(() => rmSync(dir, { recursive: true, force: true }))
  const report = join(dir, 'audit.json')
  const inspect = (url: string, node: string, severity: string, time: string) => {
    writeFileSync(report, JSON.stringify({ auditReportVersion: 2, vulnerabilities: {
      picomatch: { severity, via: [{ url, severity }], nodes: [node] },
      vite: { severity, via: ['picomatch'] },
    } }))
    const clock = encodeURIComponent(`Date.now = () => Date.parse(${JSON.stringify(time)})`)
    return spawnSync(process.execPath, ['--import', `data:text/javascript,${clock}`, script, report, '1'],
      { encoding: 'utf8' })
  }
  const within = '2026-11-19T00:00:00+08:00'
  const dev = 'node_modules/picomatch'
  assert.equal(inspect(advisory, dev, 'high', within).status, 0)
  assert.equal(inspect(advisory, dev, 'critical', within).status, 1)
  assert.equal(inspect(advisory, 'node_modules/vue', 'high', within).status, 1)
  assert.equal(inspect('https://github.com/advisories/other', dev, 'high', within).status, 1)
  assert.equal(inspect(advisory, dev, 'high', '2026-12-03T00:00:00+08:00').status, 1)
  writeFileSync(report, '{}')
  assert.equal(spawnSync(process.execPath, [script, report, '0']).status, 1)
})
