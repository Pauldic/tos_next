import { onMounted, onUnmounted, watch, type Ref } from 'vue'

/** Run `fn` now, whenever `source` changes, and every `ms` while the tab is visible. */
export function usePolling(fn: () => Promise<void> | void, source: Ref<unknown>, ms = 15000) {
  let timer: ReturnType<typeof setInterval> | undefined
  const run = () => { if (source.value && !document.hidden) fn() }
  onMounted(() => { run(); timer = setInterval(run, ms) })
  onUnmounted(() => timer && clearInterval(timer))
  watch(source, run)
}
