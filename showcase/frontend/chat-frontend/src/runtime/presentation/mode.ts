export type PresentationMode = 'solve' | 'teach' | 'report'

export interface ParsedPresentationInput {
  problem: string
  presentationMode?: PresentationMode
}

const commandPattern = /^\/(solve|teach|report)(?:\s+([\s\S]*))?$/

export function parsePresentationInput(input: string): ParsedPresentationInput {
  const value = input.trim()
  const match = commandPattern.exec(value)
  if (!match) return { problem: value }
  return {
    problem: match[2]?.trim() ?? '',
    presentationMode: match[1] as PresentationMode,
  }
}
