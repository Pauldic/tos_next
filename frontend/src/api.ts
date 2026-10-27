// Thin wrapper over Frappe whitelisted methods. Reads use GET so they work on the dev server
// (no CSRF token there); writes use POST and send the token from the boot data.
const BASE = '/api/method/'

function csrf(): string {
  return (window as any).csrf_token || ''
}

export async function call<T = any>(
  method: string,
  params: Record<string, unknown> = {},
  opts: { post?: boolean } = {},
): Promise<T> {
  const clean: Record<string, string> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') clean[k] = typeof v === 'object' ? JSON.stringify(v) : String(v)
  }
  const qs = new URLSearchParams(clean).toString()
  const post = opts.post === true
  const res = await fetch(BASE + method + (!post && qs ? '?' + qs : ''), {
    method: post ? 'POST' : 'GET',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(post ? { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Frappe-CSRF-Token': csrf() } : {}),
    },
    body: post ? qs : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(extractMessage(data) || `Request failed (${res.status})`)
  return data.message as T
}

function extractMessage(data: any): string {
  try {
    if (data._server_messages) {
      const msgs = JSON.parse(data._server_messages).map((m: string) => JSON.parse(m).message)
      return msgs.join('\n').replace(/<[^>]+>/g, '')
    }
  } catch {}
  return data.exception || data.message || ''
}

type P = Record<string, unknown>
type O = { post?: boolean }
export const tos = (name: string, params: P = {}, opts: O = {}) => call(`tos_next.api.${name}`, params, opts)
export const gateApi = (name: string, params: P = {}, opts: O = {}) => call(`tos_next.api_gate.${name}`, params, opts)
// Writes: always POST.
export const act = (name: string, params: P = {}) => gateApi(name, params, { post: true })
export const opsApi = (name: string, params: P = {}, opts: O = {}) => call(`tos_next.api_ops.${name}`, params, opts)
export const opsAct = (name: string, params: P = {}) => opsApi(name, params, { post: true })
export const portalApi = (name: string, params: P = {}, opts: O = {}) => call(`tos_next.api_portal.${name}`, params, opts)
export const portalAct = (name: string, params: P = {}) => portalApi(name, params, { post: true })
