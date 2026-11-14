import { call } from './api'
type P = Record<string, unknown>
export const containerApi = (name: string, params: P = {}) => call(`tos_next.api_container.${name}`, params)
