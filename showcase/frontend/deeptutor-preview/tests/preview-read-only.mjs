import assert from 'node:assert/strict'
import config from '../next.config.js'

const rewrites = await config.rewrites?.() ?? []
assert.deepEqual(rewrites, [], 'The standalone Next preview must never proxy requests to a live service')
