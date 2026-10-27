import { ref, computed } from 'vue'
import { tos } from '../api'

export interface Terminal {
  name: string
  terminal_name: string
  max_tier: number
  require_appointment: 0 | 1
}

const STORE = 'tos_terminal'
const terminals = ref<Terminal[]>([])
const selected = ref<string>('')
const loaded = ref(false)
const error = ref('')

export function useTerminal() {
  async function load() {
    if (loaded.value) return
    try {
      terminals.value = (await tos('terminals')) as Terminal[]
      const saved = (() => { try { return localStorage.getItem(STORE) } catch { return null } })()
      selected.value = terminals.value.find((t) => t.name === saved)?.name || terminals.value[0]?.name || ''
      loaded.value = true
    } catch (e: any) {
      error.value = e.message
    }
  }
  function select(name: string) {
    selected.value = name
    try { localStorage.setItem(STORE, name) } catch {}
  }
  const current = computed(() => terminals.value.find((t) => t.name === selected.value))
  return { terminals, selected, current, loaded, error, load, select }
}
