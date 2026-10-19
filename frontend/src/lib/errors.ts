import { ApiError } from './api.ts'

/**
 * Convert an unknown thrown value into a human-readable message.
 *
 * Never surface raw tokens, stack traces or opaque server payloads.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

/** Field-level validation messages keyed by form field name. */
export function errorFieldMap(error: unknown): Record<string, string> {
  if (error instanceof ApiError) {
    const map: Record<string, string> = {}
    for (const { field, message } of error.fieldErrors) {
      if (field && !map[field]) map[field] = message
    }
    return map
  }
  return {}
}

export function isEmptyObject(value: Record<string, unknown>): boolean {
  return Object.keys(value).length === 0
}
