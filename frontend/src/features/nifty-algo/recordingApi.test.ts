import { beforeEach, expect, it, vi } from 'vitest'
import { createRecording, sealRecording } from './api'

const web = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/api/client', () => ({ webClient: { post: web.post } }))

beforeEach(() => {
  vi.resetAllMocks()
})

it('uses the signed-session client and strips market evidence and trading authority', async () => {
  const manifest = { id: 'recording-1', execution_eligible: false }
  web.post.mockResolvedValue({ data: { status: 'success', data: manifest } })
  const request = {
    duration_minutes: 60,
    max_observations: 500,
    native_capture: true,
    source: 'BROKER_VERIFIED',
    broker: 'caller-choice',
    execution_eligible: true,
    observations: [{ price: 1 }],
  }
  expect(await createRecording(request)).toEqual(manifest)
  expect(web.post).toHaveBeenCalledExactlyOnceWith('/api/nifty-algo/research/recordings', {
    duration_minutes: 60,
    max_observations: 500,
    native_capture: true,
    confirm: 'RESEARCH_ONLY',
  })
})

it('keeps capture opt-in false rather than implicitly adopting a recording', async () => {
  web.post.mockResolvedValue({ data: { data: { capture: null } } })
  await createRecording({ duration_minutes: 1, max_observations: 1, native_capture: false })
  expect(web.post.mock.calls[0][1].native_capture).toBe(false)
})

it('seals only the reviewed count and encodes the owned recording path', async () => {
  web.post.mockResolvedValue({ data: { data: { status: 'SEALED' } } })
  expect(await sealRecording({ id: 'id/with?path', expected_count: 7 })).toEqual({
    status: 'SEALED',
  })
  expect(web.post).toHaveBeenCalledExactlyOnceWith(
    '/api/nifty-algo/research/recordings/id%2Fwith%3Fpath/seal',
    { expected_count: 7, confirm: 'SEAL_ONLY' }
  )
})

it('propagates stale-count conflicts without retrying or substituting another count', async () => {
  const conflict = new Error('Recording changed; reload before sealing')
  web.post.mockRejectedValue(conflict)
  await expect(sealRecording({ id: 'recording-1', expected_count: 7 })).rejects.toBe(conflict)
  expect(web.post).toHaveBeenCalledTimes(1)
})
