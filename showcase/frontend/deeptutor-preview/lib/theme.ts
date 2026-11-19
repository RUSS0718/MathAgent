export const themeKey = 'mathagent-preview-theme'

// Restore the saved palette before the first paint of the statically rendered page.
export const restoreTheme = "try { if (localStorage.getItem('" + themeKey + "') === 'dark') document.documentElement.classList.replace('theme-snow','dark') } catch {}"
