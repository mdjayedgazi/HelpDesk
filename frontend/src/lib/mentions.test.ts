import { describe, expect, it } from 'vite-plus/test'

import {
  activeMention,
  highlightMatch,
  insertMention,
  matchesQuery,
  mentionHandle,
} from './mentions.ts'

/** Pure trigger/insertion rules for the @mention autocomplete. */

describe('activeMention', () => {
  it('detects a bare @ at the caret', () => {
    expect(activeMention('hello @', 7)).toEqual({ query: '', start: 6, end: 7 })
  })

  it('detects @ followed by a partial name', () => {
    expect(activeMention('hi @Ali', 7)).toEqual({ query: 'Ali', start: 3, end: 7 })
  })

  it('detects a mention at the start of the message', () => {
    expect(activeMention('@alice', 6)).toEqual({ query: 'alice', start: 0, end: 6 })
  })

  it('is case-preserving (case-insensitivity is the search layer)', () => {
    expect(activeMention('@ALICE', 6)?.query).toBe('ALICE')
    expect(activeMention('@alice', 6)?.query).toBe('alice')
  })

  it('does not trigger inside an email address', () => {
    // "name@host" — the @ is preceded by a word character.
    expect(activeMention('mail me at name@host', 20)).toBeNull()
  })

  it('does not trigger when the caret is far from the @', () => {
    // "@bob" completed, caret after more text before the panel should be gone.
    expect(activeMention('@bob hello world', 16)).toBeNull()
  })

  it('returns null when there is no @ before the caret', () => {
    expect(activeMention('just some text', 14)).toBeNull()
  })

  it('handles a null caret', () => {
    expect(activeMention('@a', null)).toBeNull()
    expect(activeMention('@a', undefined)).toBeNull()
  })
})

describe('insertMention', () => {
  it('replaces the token and appends a space', () => {
    const mention = activeMention('hi @Al', 6)!
    const result = insertMention('hi @Al', mention, 'alice')
    expect(result.value).toBe('hi @alice ')
    expect(result.caret).toBe('hi @alice '.length)
  })

  it('preserves text after the caret', () => {
    const value = 'hi @Al there'
    const mention = activeMention(value, 6)!
    const result = insertMention(value, mention, 'alice')
    expect(result.value).toBe('hi @alice there')
  })

  it('can insert two mentions in one message', () => {
    let value = '@a and @b'
    const first = activeMention(value, 2)!
    value = insertMention(value, first, 'alice').value
    const second = activeMention(value, value.length)!
    value = insertMention(value, second, 'bob').value
    expect(value).toBe('@alice and @bob ')
  })

  it('keeps caret after the trailing space', () => {
    const mention = activeMention('@Al', 3)!
    const result = insertMention('@Al', mention, 'alice')
    expect(result.value.slice(result.caret)).toBe('')
  })
})

describe('mentionHandle / matchesQuery', () => {
  it('uses the username as the handle', () => {
    expect(mentionHandle({ full_name: 'Alice Chen', username: 'alice' })).toBe('alice')
  })

  it('matches name and username case-insensitively', () => {
    const user = { full_name: 'Alice Chen', username: 'alice_c' }
    for (const query of ['a', 'A', 'ali', 'ALI', 'chen', 'CHEN', 'alice']) {
      expect(matchesQuery(query, user)).toBe(true)
    }
    expect(matchesQuery('zzz', user)).toBe(false)
  })

  it('an empty query matches everyone', () => {
    expect(matchesQuery('', { full_name: 'X', username: 'x' })).toBe(true)
  })
})

describe('highlightMatch', () => {
  it('splits around the first case-insensitive match', () => {
    expect(highlightMatch('Alice Chen', 'ali')).toEqual({
      before: '',
      match: 'Ali',
      after: 'ce Chen',
    })
  })

  it('returns the whole text when there is no match', () => {
    expect(highlightMatch('Alice', 'zz')).toEqual({ before: 'Alice', match: '', after: '' })
  })

  it('returns the whole text for an empty query', () => {
    expect(highlightMatch('Alice', '')).toEqual({ before: 'Alice', match: '', after: '' })
  })
})
