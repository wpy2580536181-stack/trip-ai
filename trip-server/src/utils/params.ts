export function parseIntParam(value: string | string[] | undefined, fieldName: string): number | null {
  if (value == null) return null
  const raw = Array.isArray(value) ? value[0] : value
  if (raw == null) return null
  const n = Number(raw)
  if (!Number.isInteger(n) || n <= 0) {
    throw new InvalidParamError(`${fieldName} 必须是正整数`)
  }
  return n
}

export class InvalidParamError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'InvalidParamError'
  }
}

export function isInvalidParamError(e: unknown): e is InvalidParamError {
  return e instanceof InvalidParamError
}
