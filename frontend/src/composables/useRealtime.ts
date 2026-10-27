import { onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * Subscribe to a terminal's realtime room. `live` is true while the socket is connected, so a page can
 * poll only when it is false. Any failure just leaves `live` false; nothing here may break the page.
 * Check the room and namespace mechanism against Frappe v16 if events do not arrive.
 */
export function useRealtime(terminal: Ref<string>, events: string[], onEvent: (event: string, data: any) => void) {
  const live = ref(false)
  let socket: any = null

  function url() {
    const w = window as any
    if (!w.site_name) return '' // dev server: no boot data, so poll instead
    const port = location.port
    const host = ['', '80', '443'].includes(port) ? location.origin : `${location.protocol}//${location.hostname}:${w.socketio_port || 9000}`
    return `${host}/${w.site_name}`
  }

  async function connect() {
    const u = url()
    if (!u || socket) return
    try {
      const { io } = await import('socket.io-client')
      socket = io(u, { withCredentials: true, reconnectionAttempts: Infinity })
      socket.on('connect', () => { live.value = true; subscribe() })
      socket.on('disconnect', () => { live.value = false })
      socket.on('connect_error', () => { live.value = false })
      for (const e of events) socket.on(e, (data: any) => onEvent(e, data))
    } catch {
      live.value = false
    }
  }
  function subscribe() {
    if (socket?.connected && terminal.value) socket.emit('doc_subscribe', 'Terminal', terminal.value)
  }
  watch(terminal, (t, old) => {
    if (socket?.connected && old) socket.emit('doc_unsubscribe', 'Terminal', old)
    subscribe()
  })
  connect()
  onUnmounted(() => { try { socket?.disconnect() } catch {} socket = null })
  return { live }
}
