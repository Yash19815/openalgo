import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { niftyKeys, readNifty, type SelectorRecord } from './api'
import { CodeList, Facts, Panel, text } from './parts'

export function SelectorPanel() {
  const [mode, setMode] = useState<'PAPER' | 'SHADOW'>('PAPER')
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'selector', mode],
    queryFn: () => readNifty<SelectorRecord | null>(`selector?mode=${mode}`),
    refetchInterval: 15_000,
  })
  const report = query.data?.payload
  return (
    <Panel title="Smart contract selector">
      <p className="nifty-muted">
        Recorded evidence only. Rank does not authorize an order. Sizing, costs and all entry gates
        still apply. Live execution stays blocked.
      </p>
      <label htmlFor="nifty-selector-mode">Selector evidence mode</label>
      <select
        id="nifty-selector-mode"
        value={mode}
        onChange={(event) => setMode(event.target.value === 'SHADOW' ? 'SHADOW' : 'PAPER')}
      >
        <option value="PAPER">Paper</option>
        <option value="SHADOW">Shadow</option>
      </select>
      {query.error ? (
        <>
          <p role="alert">{query.error.message}</p>
          <Button variant="outline" disabled={query.isFetching} onClick={() => query.refetch()}>
            Reload selector evidence
          </Button>
        </>
      ) : query.isPending ? (
        <output>Loading selector evidence...</output>
      ) : !query.data ? (
        <p className="nifty-empty">No recorded contract assessment for this mode.</p>
      ) : !report || !Array.isArray(report.candidates) ? (
        <p role="alert">Selector evidence unavailable.</p>
      ) : (
        <>
          <Facts
            rows={[
              [
                'Observed at',
                <time key="observed" dateTime={report.evaluated_at}>
                  {report.evaluated_at}
                </time>,
              ],
              ['Mode', report.mode],
              ['Policy', report.policy],
              ['Decision', report.decision_id],
              ['Configuration', report.configuration_id],
              ['Spot reference', text(report.spot_reference)],
              ['Listed ATM strike', text(report.atm_strike)],
              ['Expiry', text(report.expiry)],
            ]}
          />
          {report.reasons && report.reasons.length > 0 && (
            <CodeList codes={report.reasons} empty="" label="Selector refusals" />
          )}
          {report.quantity_ranking && (
            <div>
              <h3>Risk-approved weighted proposals</h3>
              <p className="nifty-muted">
                Scores range from 0 to 100. Missing Delta earns zero under its fixed weight.
              </p>
              <p>Validated at {report.quantity_ranking.evaluated_at}</p>
              {report.quantity_ranking.ranking.length === 0 && (
                <p>NO TRADE: no quantity passes risk approval.</p>
              )}
              {report.quantity_ranking.ranking.map((row, index) => (
                <Facts
                  key={`${row.token}:${row.lots}`}
                  rows={[
                    [
                      'Proposal',
                      `${index === 0 ? 'Selected' : 'Alternative'}: ${row.token}, ${row.lots} lots (${row.quantity})`,
                    ],
                    ['Total score', row.total],
                    ['Capital required (Rs)', row.capital_required],
                    ['Planned loss (Rs)', row.planned_loss],
                    ['Projected net reward (Rs)', row.projected_net_reward],
                    ['Delta coverage', row.coverage.delta ? 'Available' : 'Unavailable'],
                    [
                      'Open-interest coverage',
                      row.coverage.open_interest
                        ? 'Available: caps volume contribution'
                        : 'Unavailable: volume contribution earns zero',
                    ],
                    ['Recorded open interest', row.inputs?.open_interest ?? 'Unavailable'],
                    ['OI-capped volume', row.inputs?.oi_capped_volume ?? 'Unavailable'],
                    ...Object.entries(row.scores).map(([name, score]): [string, string] => [
                      name,
                      score,
                    ]),
                  ]}
                />
              ))}
              <ul aria-label="Quantity rejection reasons">
                {report.quantity_ranking.rejections.map((row) => (
                  <li key={`${row.token}:${row.lots}:${row.reason}`}>
                    {row.token ?? 'No contract'} / {row.lots} lots: {row.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.ranked_tokens.length === 0 && (
            <p className="nifty-empty">No contract passed selector gates.</p>
          )}
          <ul className="nifty-codes" aria-label="Contract candidate evidence">
            {report.candidates.map((candidate, index) => (
              <li key={`${candidate.instrument.token}:${index}`}>
                <h3 className="nifty-subhead">
                  {candidate.rank === null ? 'Rejected' : `Rank ${candidate.rank}`}:{' '}
                  {candidate.instrument.symbol}
                  {' / '}
                  {candidate.instrument.kind}
                  {' / '}
                  {candidate.moneyness}
                </h3>
                <Facts
                  rows={[
                    ['Token', candidate.instrument.token],
                    ['Exchange', candidate.instrument.exchange],
                    ['Strike', candidate.instrument.strike],
                    ['Contract expiry', candidate.instrument.expiry],
                    ['Lot size', candidate.instrument.lot_size],
                    ['Tick size', candidate.instrument.tick_size],
                  ]}
                />
                <CodeList
                  codes={candidate.reasons}
                  empty="Passed selector gates. Not an admission decision."
                  label={`Rejections for ${candidate.instrument.symbol}`}
                />
                {candidate.quote ? (
                  <Facts
                    rows={[
                      ['Bid / ask', `${text(candidate.quote.bid)} / ${text(candidate.quote.ask)}`],
                      [
                        'Bid / ask size',
                        `${candidate.quote.bid_size} / ${candidate.quote.ask_size}`,
                      ],
                      ['Volume', text(candidate.quote.volume)],
                      ['Quote source time', candidate.quote.source_time],
                      ['Provider', candidate.quote.provider],
                    ]}
                  />
                ) : (
                  <p className="nifty-muted">No quote recorded.</p>
                )}
              </li>
            ))}
          </ul>
          {report.omitted_candidates > 0 && (
            <p className="nifty-muted">
              {report.omitted_candidates} metadata rows omitted from bounded evidence.
            </p>
          )}
        </>
      )}
    </Panel>
  )
}
