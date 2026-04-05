export function debounce<T extends (...args: any[]) => any>(fn: T, ms: number): T & { cancel: () => void } {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  const debounced = function (this: any, ...args: any[]) {
    if (timeoutId !== null) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => { timeoutId = null; fn.apply(this, args) }, ms)
  } as T & { cancel: () => void }
  debounced.cancel = () => { if (timeoutId !== null) { clearTimeout(timeoutId); timeoutId = null } }
  return debounced
}
