export interface Job { move_type: string; container: string; container_length: number | ''; booking_ref: string }
export interface TxType { name: string; direction: 'In' | 'Out'; cargo: string; category?: string; counterparty?: string; requires_container: number; requires_booking: number; description?: string }
export const blankJob = (move_type = ''): Job => ({ move_type, container: '', container_length: '', booking_ref: '' })
export const dirOf = (types: TxType[], name: string) => types.find((t) => t.name === name)?.direction
export const firstOf = (types: TxType[], direction: 'In' | 'Out') => types.find((t) => t.direction === direction)?.name || types[0]?.name || ''
