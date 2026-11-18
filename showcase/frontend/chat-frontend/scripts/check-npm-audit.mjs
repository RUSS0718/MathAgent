// Keep the approved exception bound to one advisory, one dev version and an expiry.
import { readFileSync } from 'node:fs'

const advisory = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf'
const expires = Date.parse('2026-12-03T00:00:00+08:00')
const level = new Set(['high', 'critical'])
const report = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'))
const findings = report.vulnerabilities
if (report.error || report.auditReportVersion !== 2 || !findings || Array.isArray(findings) ||
    typeof findings !== 'object' || ![0, 1].includes(Number(process.argv[3]))) {
  throw new Error('npm audit did not produce a usable report')
}

function permitted(name, path = new Set()) {
  const entry = findings[name]
  if (path.has(name) || !Array.isArray(entry?.via) || entry.via.length === 0) return false
  return entry.via.every(cause => {
    if (typeof cause === 'string') return permitted(cause, new Set([...path, name]))
    return name === 'picomatch' && cause?.url === advisory && cause.severity === 'high' &&
      Date.now() < expires && Array.isArray(entry.nodes) && entry.nodes.length > 0 &&
      entry.nodes.every(node => lock.packages[node]?.version === '4.0.7' && lock.packages[node]?.dev === true)
  })
}

const severe = Object.entries(findings).filter(([, entry]) => level.has(entry.severity))
if ((severe.length > 0) !== (Number(process.argv[3]) === 1)) {
  throw new Error('npm audit status disagrees with its findings')
}
const blocked = severe.filter(([name, entry]) => entry.severity === 'critical' || !permitted(name))
if (blocked.length) {
  console.error('Blocking high or critical npm findings:', blocked.map(([name]) => name).join(', '))
  process.exitCode = 1
} else if (severe.length) {
  console.warn(`Approved dev-only exception through 2026-12-02 Beijing time: ${advisory}`)
}
