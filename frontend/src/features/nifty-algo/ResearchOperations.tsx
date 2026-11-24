import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  defineExecutionComparison,
  niftyKeys,
  type RecordingList,
  type ResearchRecording,
  readNifty,
  recordingRetention,
} from './api'

export function ResearchOperations() {
  const cache = useQueryClient()
  const [pinned, setPinned] = useState<ResearchRecording[]>([])
  const [train, setTrain] = useState('')
  const [validation, setValidation] = useState('')
  const [overrides, setOverrides] = useState('{}')
  const [approve, setApprove] = useState(false)
  const recordings = useQuery({
    queryKey: [...niftyKeys.all, 'research/recordings'],
    queryFn: () => readNifty<RecordingList>('research/recordings'),
    retry: false,
  })
  const archives = useQuery({
    queryKey: [...niftyKeys.all, 'research/recordings/archives'],
    queryFn: () => readNifty<{ items: ResearchRecording[] }>('research/recordings/archives'),
    retry: false,
  })
  const choices =
    !recordings.isError && Array.isArray(recordings.data?.items)
      ? recordings.data.items.filter((r) => r.status === 'SEALED')
      : []
  const refresh = async () => {
    const results = await Promise.all([recordings.refetch(), archives.refetch()])
    return results.every((r) => !r.isError)
  }
  const retention = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'archive' | 'restore' }) =>
      recordingRetention(id, action),
    retry: false,
    onSuccess: async () => {
      await refresh()
    },
  })
  let edited: Record<string, unknown> | null = null
  try {
    const parsed = JSON.parse(overrides)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) edited = parsed
  } catch {
    /* Invalid JSON disables submission; no repair or substitution. */
  }
  const changed = pinned.some(
    (p) =>
      !choices.some(
        (c) => c.id === p.id && c.count === p.count && c.content_sha256 === p.content_sha256
      )
  )
  const creation = useMutation({
    mutationFn: () =>
      defineExecutionComparison({
        sources: pinned.map((p) => ({
          id: p.id,
          count: p.count,
          content_sha256: p.content_sha256,
        })),
        configuration: { ...pinned[0]?.configuration, ...edited },
        train_end: `${train}Z`,
        validation_end: `${validation}Z`,
      }),
    retry: false,
    onSuccess: async () => {
      setApprove(false)
      await cache.invalidateQueries({ queryKey: [...niftyKeys.all, 'research/experiments'] })
    },
  })
  const canDefine =
    pinned.length > 0 &&
    pinned.length <= 20 &&
    !!pinned[0]?.configuration &&
    !!edited &&
    approve &&
    !changed &&
    Number.isFinite(Date.parse(`${train}Z`)) &&
    Date.parse(`${train}Z`) < Date.parse(`${validation}Z`) &&
    !creation.isPending &&
    !creation.isError &&
    !recordings.isError
  return (
    <section aria-label="Research evidence operations">
      <details>
        <summary>Define a multi-session research comparison</summary>
        <p>
          Select up to 20 immutable recordings sharing the same baseline configuration. Definitions
          are research only and never change active settings.
        </p>
        {choices.map((r) => (
          <label key={r.id} style={{ display: 'block' }}>
            <input
              type="checkbox"
              checked={pinned.some((p) => p.id === r.id)}
              disabled={creation.isPending}
              onChange={(e) => {
                setPinned(
                  e.target.checked
                    ? [...pinned, structuredClone(r)]
                    : pinned.filter((p) => p.id !== r.id)
                )
                setApprove(false)
              }}
            />
            Recording {r.id}: {r.count} observations
          </label>
        ))}
        {changed && <p role="alert">Pinned source changed. Refresh and select evidence again.</p>}
        <label htmlFor="comparison-train">Training end (UTC)</label>
        <Input
          id="comparison-train"
          type="datetime-local"
          value={train}
          onChange={(e) => setTrain(e.target.value)}
        />
        <label htmlFor="comparison-validation">Validation end (UTC)</label>
        <Input
          id="comparison-validation"
          type="datetime-local"
          value={validation}
          onChange={(e) => setValidation(e.target.value)}
        />
        <label htmlFor="comparison-overrides">Experimental research overrides (JSON)</label>
        <p>
          Only indicator parameters are allowed. Risk limits, costs and execution assumptions must
          match the pinned baseline.
        </p>
        <textarea
          id="comparison-overrides"
          value={overrides}
          maxLength={65536}
          onChange={(e) => {
            setOverrides(e.target.value)
            setApprove(false)
          }}
        />
        <label>
          <input type="checkbox" checked={approve} onChange={(e) => setApprove(e.target.checked)} />
          I approve this research definition only; active trading settings remain unchanged.
        </label>
        <Button variant="outline" disabled={!canDefine} onClick={() => creation.mutate()}>
          Define pinned comparison
        </Button>
        {creation.isSuccess && (
          <output>
            Immutable comparison defined. Select it in the experiment list to queue replay.
          </output>
        )}
        {creation.isError && (
          <p role="alert">
            Definition outcome unknown. Inspect the experiment list before retrying.
          </p>
        )}
      </details>
      <details>
        <summary>Archive and restore sealed evidence</summary>
        <p>
          Archive preserves verified immutable evidence on disk and frees active recording slots.
          Trading and safety history stay intact. Keep archives with database backups.
        </p>
        {recordings.isError || archives.isError ? (
          <p role="alert">Recording catalogue unavailable. Retention actions are blocked.</p>
        ) : (
          <>
            {choices.map((r) => (
              <p key={r.id}>
                {r.id}{' '}
                <Button
                  variant="outline"
                  disabled={retention.isPending || retention.isError}
                  onClick={() => retention.mutate({ id: r.id, action: 'archive' })}
                >
                  Archive sealed recording {r.id}
                </Button>
              </p>
            ))}
            {Array.isArray(archives.data?.items) &&
              archives.data.items.map((r) => (
                <p key={r.id}>
                  {r.id}: archived
                  <Button
                    variant="outline"
                    disabled={retention.isPending || retention.isError}
                    onClick={() => retention.mutate({ id: r.id, action: 'restore' })}
                  >
                    Restore recording {r.id}
                  </Button>
                  <a
                    href={`/api/nifty-algo/research/recordings/${encodeURIComponent(r.id)}/archive`}
                    download
                  >
                    Download verified archive {r.id}
                  </a>
                </p>
              ))}
          </>
        )}
        {retention.isError && (
          <p role="alert">
            Retention outcome unavailable. Refresh both catalogues before any retry.
          </p>
        )}
      </details>
      <Button
        variant="outline"
        disabled={creation.isPending || retention.isPending}
        onClick={async () => {
          if (await refresh()) {
            creation.reset()
            retention.reset()
            setPinned([])
            setApprove(false)
          }
        }}
      >
        Refresh research catalogues
      </Button>
    </section>
  )
}
