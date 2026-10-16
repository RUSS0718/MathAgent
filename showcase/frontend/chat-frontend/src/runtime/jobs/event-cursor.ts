export function acceptEventId(cursor: number, id: number): boolean { return Number.isSafeInteger(id) && id > cursor }
