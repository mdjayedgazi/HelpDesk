import { describe, expect, it } from 'vite-plus/test'

import { resolveApiBase } from './apiBase.ts'

describe('resolveApiBase', () => {
  it('falls back to the local API during development', () => {
    expect(resolveApiBase(undefined, false)).toBe('http://127.0.0.1:8000')
  })

  it('normalizes a configured development origin', () => {
    expect(resolveApiBase('http://localhost:8000/', false)).toBe('http://localhost:8000')
  })

  it('accepts an absolute HTTPS origin in production', () => {
    expect(resolveApiBase('https://api.helpdesk.example/', true)).toBe(
      'https://api.helpdesk.example',
    )
  })

  it('rejects a missing production URL', () => {
    expect(() => resolveApiBase(undefined, true)).toThrow('VITE_API_URL is required')
  })

  it('rejects HTTP in production', () => {
    expect(() => resolveApiBase('http://api.helpdesk.example', true)).toThrow('HTTPS')
  })

  it('rejects localhost in production', () => {
    expect(() => resolveApiBase('https://localhost:8000', true)).toThrow('localhost')
  })

  it('rejects a path in the API origin', () => {
    expect(() => resolveApiBase('https://api.helpdesk.example/api', true)).toThrow('origin')
  })
})
