export const modes = { solve: '求解', explore: '探索', report: '报告', teach: '教学' } as const
export type OutputMode = keyof typeof modes
export const modeKeys = Object.keys(modes) as OutputMode[]

export function parseOutput(input: string): { mode: OutputMode; question: string } {
  const text = input.trim()
  const match = /^\/(solve|explore|exlpore|report|teach)(?:\s+|$)/.exec(text)
  if (!match) return { mode: 'solve', question: text }
  const mode = match[1] === 'exlpore' ? 'explore' : match[1] as OutputMode
  return { mode, question: text.slice(match[0].length).trim() }
}

export function withMode(mode: OutputMode, question: string) {
  return mode === 'solve' ? question : '/' + mode + ' ' + question
}
