/**
 * Pure helpers for the @mention autocomplete.
 *
 * Kept free of React and the DOM so the trigger detection and insertion rules
 * can be unit-tested. The composer owns the textarea caret; these functions
 * operate on a plain `{ value, caret }` snapshot.
 */

/**
 * The active mention query at the caret, or `null` when the caret is not inside
 * a mention token.
 *
 * A mention token starts at an `@` that is at the beginning of the text or
 * preceded by whitespace/open punctuation, and runs to the caret over
 * characters that can appear in a name/username. This deliberately does not
 * trigger inside an email address (``name@host``): the character before the
 * `@` must not be a word character.
 */
export interface MentionQuery {
  /** Text typed after the `@`, up to the caret. */
  query: string
  /** Index of the `@` in the value. */
  start: number
  /** Caret index (=== end of the query). */
  end: number
}

const MENTION_CHAR = /[A-Za-z0-9._-]/

export function activeMention(
  value: string,
  caret: number | null | undefined,
): MentionQuery | null {
  if (caret == null || caret < 1 || caret > value.length) return null

  // Walk backwards from the caret to find the nearest '@' in the current token.
  let index = caret - 1
  while (index >= 0) {
    const char = value[index]!
    if (char === '@') break
    // A space or punctuation that is not valid in a mention ends the search:
    // the caret is not inside a mention token.
    if (char === ' ' || char === '\n' || char === '\t') return null
    if (!MENTION_CHAR.test(char)) return null
    index -= 1
  }
  if (index < 0) return null

  // The character before the '@' must not be a word character (so emails do
  // not trigger). Start of text is allowed.
  const before = index > 0 ? value[index - 1]! : ''
  if (before && MENTION_CHAR.test(before)) return null
  if (before === '@') return null

  const query = value.slice(index + 1, caret)
  return { query, start: index, end: caret }
}

export interface MentionInsertion {
  value: string
  /** Caret position after insertion (just past the trailing space). */
  caret: number
}

/**
 * Replace the active mention token with the selected employee's handle and a
 * trailing space, preserving the text before and after it.
 */
export function insertMention(
  value: string,
  mention: MentionQuery,
  handle: string,
): MentionInsertion {
  const before = value.slice(0, mention.start)
  const after = value.slice(mention.end)
  const token = `@${handle} `
  return {
    value: `${before}${token}${after.replace(/^\s+/, '')}`,
    caret: before.length + token.length,
  }
}

/** The handle used in the message text for a selected employee. */
export function mentionHandle(user: { full_name: string; username: string }): string {
  // Usernames are unique and stable, so they are the safest handle to embed in
  // the body; the structured id is what actually drives the mention.
  return user.username
}

/** Whether a display name (or username) contains the query, case-insensitively. */
export function matchesQuery(
  query: string,
  user: { full_name: string; username: string },
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return (
    user.full_name.toLowerCase().includes(needle) ||
    user.username.toLowerCase().includes(needle)
  )
}

export interface Highlight {
  before: string
  match: string
  after: string
}

/**
 * Split a label into before/match/after around the first case-insensitive
 * occurrence of the query, so the match can be visually highlighted.
 */
export function highlightMatch(text: string, query: string): Highlight {
  const needle = query.trim().toLowerCase()
  if (!needle) return { before: text, match: '', after: '' }
  const index = text.toLowerCase().indexOf(needle)
  if (index < 0) return { before: text, match: '', after: '' }
  return {
    before: text.slice(0, index),
    match: text.slice(index, index + needle.length),
    after: text.slice(index + needle.length),
  }
}
