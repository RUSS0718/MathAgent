/** Fail closed on duplicate UI stacks or unlocked direct dependencies. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'))
const approved = ['@lucide/vue', 'katex', 'pinia', 'vue', 'zod']
assert.deepEqual(Object.keys(pkg.dependencies).sort(), approved.sort(), 'Runtime dependency change requires updating the design/dependency decision and this allowlist')
for (const [name, version] of Object.entries({ ...pkg.dependencies, ...pkg.devDependencies })) {
  assert.match(version, /^\d+\.\d+\.\d+$/, `${name} must use an exact version`)
  assert.equal(lock.packages[`node_modules/${name}`]?.version, version, `${name} differs from lockfile`)
}
for (const name of approved) {
  const copies = Object.keys(lock.packages).filter(path => path === `node_modules/${name}` || path.endsWith(`/node_modules/${name}`))
  assert.equal(copies.length, 1, `Duplicate runtime dependency: ${name}`)
}
console.log('Dependency contract passed: one framework, store, validator, math renderer, icon library.')
