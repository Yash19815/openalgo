import { beforeEach, expect, it, vi } from 'vitest'
import { defineExperiment } from './api'

const web = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/api/client', () => ({ webClient: { post: web.post } }))

beforeEach(() => vi.resetAllMocks())

it('pins the reviewed source and strips caller authority using the signed-session client', async () => {
  const result = { id: 'definition', status: 'DEFINED', execution_eligible: false }
  web.post.mockResolvedValue({ data: { data: result } })
  const payload = {
    recording_id: 'source',
    expected_count: 17,
    expected_sha256: 'a'.repeat(64),
    train_end: '2026-01-01T04:10:00Z',
    validation_end: '2026-01-01T04:20:00Z',
    configuration_overrides: { adx_min: 30, atr_period: 20 },
    user: 'someone-else',
    execution_eligible: true,
    provenance: 'VERIFIED',
    confirm: 'RUN',
  }
  expect(await defineExperiment(payload)).toEqual(result)
  expect(web.post).toHaveBeenCalledExactlyOnceWith('/api/nifty-algo/research/experiments', {
    recording_id: 'source',
    expected_count: 17,
    expected_sha256: 'a'.repeat(64),
    train_end: payload.train_end,
    validation_end: payload.validation_end,
    configuration_overrides: { adx_min: 30, atr_period: 20 },
    confirm: 'DEFINE_ONLY',
  })
})

it('propagates an uncertain write without automatically retrying it', async () => {
  const failure = new Error('Connection lost')
  web.post.mockRejectedValue(failure)
  await expect(
    defineExperiment({
      recording_id: 'source',
      expected_count: 17,
      expected_sha256: 'a'.repeat(64),
      train_end: '2026-01-01T04:10:00Z',
      validation_end: '2026-01-01T04:20:00Z',
      configuration_overrides: {},
    })
  ).rejects.toBe(failure)
  expect(web.post).toHaveBeenCalledTimes(1)
})
