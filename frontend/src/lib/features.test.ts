import { describe, expect, it } from 'vite-plus/test'

import { resolveAttachmentsEnabled } from './features.ts'

describe('resolveAttachmentsEnabled', () => {
  it('defaults to enabled when the build variable is absent', () => {
    expect(resolveAttachmentsEnabled(undefined)).toBe(true)
    expect(resolveAttachmentsEnabled('')).toBe(true)
  })

  it('disables attachments only for an explicit false value', () => {
    expect(resolveAttachmentsEnabled('false')).toBe(false)
    expect(resolveAttachmentsEnabled(' FALSE ')).toBe(false)
  })

  it('keeps attachments enabled for true and unknown values', () => {
    expect(resolveAttachmentsEnabled('true')).toBe(true)
    expect(resolveAttachmentsEnabled('1')).toBe(true)
  })
})
