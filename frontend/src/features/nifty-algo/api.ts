import { webClient } from '@/api/client'

export type RecordValue =
  | string
  | number
  | boolean
  | null
  | RecordValue[]
  | { [key: string]: RecordValue }
export type DataRecord = { [key: string]: RecordValue }
export interface NiftyStatus {
  mode: 'PAPER_ONLY'
  state: string
  revision: number
  ready: boolean
  readiness: (string | { code: string; ready: boolean; detail?: string })[]
  [key: string]: unknown
}

export const niftyKeys = { all: ['nifty-algo'] as const }
const base = '/api/nifty-algo'

export async function readNifty<T>(resource: string): Promise<T> {
  const response = await webClient.get<{ status: string; data: T }>(`${base}/${resource}`)
  return response.data.data
}

export interface ConfigurationResponse {
  configuration: DataRecord
  revision: number
  configuration_id: string
}

export async function controlNifty({
  action,
  revision,
}: {
  action: 'start' | 'pause' | 'stop' | 'kill-switch'
  revision: number
}) {
  const response = await webClient.post(`${base}/strategy/${action}`, { revision })
  return response.data
}

export async function saveConfiguration(configuration: ConfigurationResponse) {
  const response = await webClient.put(`${base}/configuration`, {
    configuration: configuration.configuration,
    revision: configuration.revision,
  })
  return response.data
}

export async function assessNativeHistory() {
  const response = await webClient.post(`${base}/assessment`, {})
  return response.data
}

export async function preparePaperMonitor() {
  const response = await webClient.post(`${base}/runner`, {})
  return response.data
}
