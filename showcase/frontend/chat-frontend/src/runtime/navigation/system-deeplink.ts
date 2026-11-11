/** Stable URL encoding for the public, read-only F7 system view. */
export type SystemPresentationMode = 'solve' | 'teach' | 'report'

export type SystemDeepLinkState = {
  runId: string
  mode?: SystemPresentationMode
  outputId?: string
  artifactId?: string
  graphVersion?: number
  nodeId?: string
  paragraphId?: string
}

export type SystemDeepLinkResult =
  | { kind: 'list' }
  | { kind: 'not_system' }
  | { kind: 'invalid'; reason: string }
  | { kind: 'valid'; state: SystemDeepLinkState; unavailableReason?: string }

const PATH = '/dashboard/system'
const SCHEME = 'f7-deeplink-v1'
const RUN_ID = /^[A-Za-z0-9._-]{1,128}$/
const OPAQUE_ID = /^[A-Za-z0-9._:-]{1,256}$/
const PARAGRAPH_ID = /^paragraph:[1-9][0-9]*$/

function validOpaqueId(value: string): boolean {
  return OPAQUE_ID.test(value)
}

export function buildSystemDeepLink(state: SystemDeepLinkState): string {
  if (!RUN_ID.test(state.runId)) throw new TypeError('run_id_invalid')
  if (Boolean(state.outputId) !== Boolean(state.artifactId)) {
    throw new TypeError('presentation_identity_incomplete')
  }
  const params = new URLSearchParams()
  params.set('scheme', SCHEME)
  params.set('run', state.runId)
  if (state.outputId !== undefined) {
    if (!validOpaqueId(state.outputId)) throw new TypeError('output_id_invalid')
    params.set('output', state.outputId)
  }
  if (state.artifactId !== undefined) {
    if (!validOpaqueId(state.artifactId)) throw new TypeError('artifact_id_invalid')
    params.set('artifact', state.artifactId)
  }
  if (state.graphVersion !== undefined) {
    if (!Number.isSafeInteger(state.graphVersion) || state.graphVersion < 0) {
      throw new TypeError('graph_version_invalid')
    }
    params.set('graph', String(state.graphVersion))
  }
  if (state.nodeId !== undefined) {
    if (!validOpaqueId(state.nodeId) || state.graphVersion === undefined) {
      throw new TypeError('node_identity_invalid')
    }
    params.set('node', state.nodeId)
  }
  if (state.paragraphId !== undefined) {
    if (!PARAGRAPH_ID.test(state.paragraphId) || !state.artifactId) {
      throw new TypeError('paragraph_identity_invalid')
    }
    params.set('paragraph', state.paragraphId)
  }
  if (state.mode !== undefined) {
    if (!['solve', 'teach', 'report'].includes(state.mode)) throw new TypeError('presentation_mode_invalid')
    params.set('mode', state.mode)
  }
  return `${PATH}?${params.toString()}`
}

export function parseSystemDeepLink(pathname: string, search: string): SystemDeepLinkResult {
  if (pathname !== PATH) return { kind: 'not_system' }
  if (!search || search === '?') return { kind: 'list' }
  const params = new URLSearchParams(search)
  for (const key of ['scheme', 'run', 'output', 'artifact', 'graph', 'node', 'paragraph', 'mode']) {
    if (params.getAll(key).length > 1) return { kind: 'invalid', reason: 'query_parameter_duplicated' }
  }
  if (params.get('scheme') !== SCHEME) return { kind: 'invalid', reason: 'scheme_unsupported' }
  const runId = params.get('run') ?? ''
  if (!RUN_ID.test(runId)) return { kind: 'invalid', reason: 'run_id_invalid' }

  const state: SystemDeepLinkState = { runId }
  const mode = params.get('mode')
  if (mode !== null) {
    if (!['solve', 'teach', 'report'].includes(mode)) return { kind: 'invalid', reason: 'presentation_mode_invalid' }
    state.mode = mode as SystemPresentationMode
  }
  const outputId = params.get('output')
  if (outputId !== null) {
    if (!validOpaqueId(outputId)) return { kind: 'invalid', reason: 'output_id_invalid' }
    state.outputId = outputId
  }
  const artifactId = params.get('artifact')
  if (artifactId !== null) {
    if (!validOpaqueId(artifactId)) return { kind: 'invalid', reason: 'artifact_id_invalid' }
    state.artifactId = artifactId
  }
  let unavailableReason: string | undefined
  if (Boolean(outputId) !== Boolean(artifactId)) unavailableReason = 'presentation_identity_incomplete'
  const graph = params.get('graph')
  if (graph !== null) {
    if (!/^(0|[1-9][0-9]*)$/.test(graph) || !Number.isSafeInteger(Number(graph))) {
      return { kind: 'invalid', reason: 'graph_version_invalid' }
    }
    state.graphVersion = Number(graph)
  }
  const nodeId = params.get('node')
  if (nodeId !== null) {
    if (!validOpaqueId(nodeId) || state.graphVersion === undefined) {
      return { kind: 'invalid', reason: 'node_identity_invalid' }
    }
    state.nodeId = nodeId
  }
  const paragraphId = params.get('paragraph')
  if (paragraphId !== null) {
    if (!PARAGRAPH_ID.test(paragraphId)) {
      return { kind: 'invalid', reason: 'paragraph_identity_invalid' }
    }
    if (!state.artifactId) unavailableReason ??= 'paragraph_identity_incomplete'
    else state.paragraphId = paragraphId
  }
  if (unavailableReason) {
    delete state.outputId
    delete state.artifactId
    delete state.paragraphId
    return { kind: 'valid', state, unavailableReason }
  }
  return { kind: 'valid', state }
}
