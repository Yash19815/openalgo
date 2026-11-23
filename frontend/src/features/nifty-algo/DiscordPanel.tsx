import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  type DiscordCenter,
  type DiscordConfiguration,
  discordChannels,
  discordSetupAction,
  niftyKeys,
  readNifty,
  saveDiscordSettings,
} from './api'
import { Facts, Panel } from './parts'

const blank = (): DiscordConfiguration => ({
  enabled: false,
  application_id: '',
  guild_id: '',
  public_key: '',
  channels: Object.fromEntries(discordChannels.map((name) => [name, ''])),
  authorized_users: [],
  authorized_roles: [],
  critical_role: null,
  preferences: {},
  reminder_interval_seconds: 900,
})

export function DiscordPanel() {
  const [draft, setDraft] = useState<DiscordConfiguration | null>(null)
  const [revision, setRevision] = useState<number | null>(null)
  const [token, setToken] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'discord'],
    queryFn: () => readNifty<DiscordCenter>('discord'),
    retry: false,
    refetchInterval: 30_000,
  })
  const settings = !query.isError ? query.data?.settings : undefined
  const save = useMutation({
    mutationFn: () => {
      if (!draft || revision === null) throw new Error('Reload configuration before saving')
      const secret = token
      setToken('')
      return saveDiscordSettings(revision, draft, secret)
    },
    retry: false,
    onSuccess: async () => {
      setDraft(null)
      setRevision(null)
      await query.refetch()
    },
    onError: () => setUncertain(true),
  })
  const action = useMutation({
    mutationFn: (name: 'validate' | 'register-commands' | 'test') =>
      discordSetupAction(name, settings?.revision ?? 0),
    retry: false,
    onSuccess: () => query.refetch(),
    onError: () => setUncertain(true),
  })
  const busy = save.isPending || action.isPending
  const available = !query.isError && !query.isPending && !!query.data
  const stale = revision !== null && revision !== (settings?.revision ?? 0)
  const edit = () => {
    setDraft(settings ? structuredClone(settings.configuration) : blank())
    setRevision(settings?.revision ?? 0)
    setToken('')
  }
  const ids = (value: string) =>
    value
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean)
  return (
    <Panel title="Discord Notification Center">
      <p className="nifty-muted">
        Read-only monitoring and incident acknowledgement. Discord cannot trade, resume, change
        stops or change risk limits.
      </p>
      {query.isPending && <output>Loading Discord configuration...</output>}
      {query.isError && (
        <p role="alert">
          Discord configuration unavailable. Cached settings cannot authorize changes.
        </p>
      )}
      <Button
        variant="outline"
        disabled={busy || query.isFetching}
        onClick={async () => {
          const fresh = await query.refetch()
          if (!fresh.isError) {
            setUncertain(false)
            setDraft(null)
            setRevision(null)
            setToken('')
            save.reset()
            action.reset()
          }
        }}
      >
        Refresh Discord status
      </Button>
      {available && (
        <>
          <Facts
            rows={[
              ['Mode', 'PAPER / SHADOW / RESEARCH; Live execution unavailable'],
              [
                'Bot token',
                settings?.token_configured ? 'Configured server-side' : 'Not configured',
              ],
              ['Guild ID', settings?.configuration.guild_id ?? 'Unavailable'],
              [
                'Delivery permissions',
                settings?.verified ? 'Verified at last setup check' : 'Unverified',
              ],
              ['Settings updated', settings?.updated_at ?? 'Unavailable'],
              ['Rate-limit deadline', settings?.rate_limit_until ?? 'No recorded cooldown'],
              [
                'Critical incident policy',
                'Always enabled; acknowledgement never resolves exposure',
              ],
              [
                'Worker',
                'Separate notification process required; queue acceptance is not delivery',
              ],
            ]}
          />
          {settings?.verification?.errors.map((error) => (
            <p role="alert" key={error}>
              {error}
            </p>
          ))}
          <Button variant="outline" disabled={busy || uncertain} onClick={edit}>
            Edit Discord settings
          </Button>
          {draft && (
            <form
              className="nifty-form"
              onSubmit={(event) => {
                event.preventDefault()
                save.mutate()
              }}
            >
              <label>
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}
                />
                Enable Discord delivery
              </label>
              {(['application_id', 'guild_id', 'public_key'] as const).map((key) => (
                <div key={key}>
                  <label htmlFor={`discord-${key}`}>{key.replaceAll('_', ' ')}</label>
                  <Input
                    id={`discord-${key}`}
                    required
                    value={draft[key]}
                    onChange={(event) => setDraft({ ...draft, [key]: event.target.value.trim() })}
                  />
                </div>
              ))}
              <label htmlFor="discord-token">
                Bot token (leave blank to preserve; enter replacement to rotate)
              </label>
              <Input
                id="discord-token"
                type="password"
                autoComplete="new-password"
                maxLength={256}
                value={token}
                onChange={(event) => setToken(event.target.value)}
                required={!settings?.token_configured}
              />
              {discordChannels.map((name) => (
                <div key={name}>
                  <label htmlFor={`discord-${name}`}>{name} channel ID</label>
                  <Input
                    id={`discord-${name}`}
                    required
                    inputMode="numeric"
                    value={draft.channels[name] ?? ''}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        channels: { ...draft.channels, [name]: event.target.value.trim() },
                      })
                    }
                  />
                </div>
              ))}
              <label htmlFor="discord-users">Authorized user IDs (comma separated)</label>
              <Input
                id="discord-users"
                value={draft.authorized_users.join(',')}
                onChange={(event) =>
                  setDraft({ ...draft, authorized_users: ids(event.target.value) })
                }
              />
              <label htmlFor="discord-roles">Authorized command role IDs (comma separated)</label>
              <Input
                id="discord-roles"
                value={draft.authorized_roles.join(',')}
                onChange={(event) =>
                  setDraft({ ...draft, authorized_roles: ids(event.target.value) })
                }
              />
              <label htmlFor="discord-critical-role">Critical alert role ID (optional)</label>
              <Input
                id="discord-critical-role"
                value={draft.critical_role ?? ''}
                onChange={(event) =>
                  setDraft({ ...draft, critical_role: event.target.value.trim() || null })
                }
              />
              {['WARNING', 'TRADE', 'RISK', 'STATUS', 'REPORT', 'RESEARCH'].map((category) => (
                <label key={category}>
                  <input
                    type="checkbox"
                    checked={draft.preferences[category] !== false}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        preferences: { ...draft.preferences, [category]: event.target.checked },
                      })
                    }
                  />
                  {category} notifications
                </label>
              ))}
              <p className="nifty-muted">
                Saving or rotating credentials invalidates permission verification. Critical
                notifications cannot be disabled here.
              </p>
              {stale && <p role="alert">Settings changed. Refresh before saving.</p>}
              <Button type="submit" disabled={busy || uncertain || stale || !available}>
                Save Discord settings
              </Button>
            </form>
          )}
          <div className="nifty-actions">
            <Button
              variant="outline"
              disabled={busy || uncertain || !settings || !!draft}
              onClick={() => action.mutate('validate')}
            >
              Verify bot permissions
            </Button>
            <Button
              variant="outline"
              disabled={busy || uncertain || !settings?.verified || !!draft}
              onClick={() => action.mutate('register-commands')}
            >
              Register read-only commands
            </Button>
            <Button
              variant="outline"
              disabled={
                busy ||
                uncertain ||
                !settings?.verified ||
                !settings?.configuration.enabled ||
                !!draft
              }
              onClick={() => action.mutate('test')}
            >
              Queue test message
            </Button>
          </div>
          {action.isSuccess && (
            <output>
              Setup request accepted. Inspect refreshed status and delivery queue for completion.
            </output>
          )}
          <h3>Delivery queue</h3>
          <Facts
            rows={Object.entries(query.data?.health?.counts ?? {}).map(([key, value]) => [
              key,
              value,
            ])}
          />
          {!Object.keys(query.data?.health?.counts ?? {}).length && (
            <p className="nifty-empty">No queued notifications.</p>
          )}
          <ul aria-label="Recent notification attempts">
            {query.data?.health?.attempts?.map((row) => (
              <li key={`${row.delivery_id}:${row.attempt}`}>
                {row.at}: {row.result.outcome} / {row.result.code}
              </li>
            ))}
          </ul>
          <h3>Unresolved critical incidents</h3>
          <ul>
            {query.data?.incidents
              ?.filter((row) => row.severity === 'CRITICAL' && row.status !== 'RESOLVED')
              .map((row) => (
                <li key={row.id}>
                  #{row.id} {row.mode}: {row.code} / {row.status}
                </li>
              ))}
          </ul>
        </>
      )}
      {(save.isError || action.isError || uncertain) && (
        <p role="alert">
          Write outcome unavailable. Refresh and inspect state before any further action. No
          automatic retry occurs.
        </p>
      )}
    </Panel>
  )
}
