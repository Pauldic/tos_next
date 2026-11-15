import { call } from './api'
type P = Record<string, unknown>
export const slotApi = (name: string, params: P = {}) => call(`tos_next.api_slots.${name}`, params)
export const slotAct = (name: string, params: P = {}) => call(`tos_next.api_slots.${name}`, params, { post: true })
