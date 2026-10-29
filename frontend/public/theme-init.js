// Apply the persisted theme before the bundle loads to avoid a flash of the
// wrong theme. Must stay in sync with src/theme/colorMode.tsx.
;(function () {
  try {
    var stored = window.localStorage.getItem('helpdesk-theme')
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    var dark = stored === 'dark' || (stored !== 'light' && prefersDark)
    var root = document.documentElement
    if (dark) root.classList.add('dark')
    root.dataset.theme = dark ? 'dark' : 'light'
    root.style.colorScheme = dark ? 'dark' : 'light'
  } catch {
    /* Storage or matchMedia unavailable - fall back to the light theme. */
  }
})()
