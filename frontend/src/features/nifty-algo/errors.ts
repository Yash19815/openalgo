/** Structured view of a failed NIFTY API call. Only codes and messages, never request data. */
export interface NiftyApiError {
  status: number | null
  code: string | null
  message: string
  reasons: string[]
}

export function describeError(error: unknown): NiftyApiError {
  const response =
    error && typeof error === 'object' && 'response' in error
      ? (error as { response?: { status?: number; data?: unknown } }).response
      : undefined
  const data =
    response?.data && typeof response.data === 'object'
      ? (response.data as { code?: unknown; reasons?: unknown; message?: unknown })
      : {}
  const reasons = Array.isArray(data.reasons)
    ? data.reasons.filter((item): item is string => typeof item === 'string')
    : []
  const fallback = error instanceof Error ? error.message : 'Request failed'
  return {
    status: typeof response?.status === 'number' ? response.status : null,
    code: typeof data.code === 'string' ? data.code : null,
    message: typeof data.message === 'string' ? data.message : fallback,
    reasons,
  }
}
