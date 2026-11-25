import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { DataRecord, RecordValue } from './api'
import { Facts } from './parts'

/** Contract selection the backend accepts. OTM is prohibited and never offered. */
export const SELECTION_OPTIONS = [
  ['ATM', 'ATM (at the money)'],
  ['ITM', 'ITM (in the money)'],
  ['DELTA', 'DELTA (nearest target delta, ATM/ITM only)'],
] as const

const SUPPORTED = new Set<string>(SELECTION_OPTIONS.map(([value]) => value))

function asText(value: RecordValue | undefined) {
  return value === null || value === undefined ? '' : String(value)
}

function amountError(
  value: string,
  { allowEmpty, positive }: { allowEmpty: boolean; positive: boolean }
) {
  if (!value) return allowEmpty ? '' : 'Required.'
  const number = Number(value)
  if (!Number.isFinite(number)) return 'Enter a number.'
  if (positive ? number <= 0 : number < 0)
    return positive ? 'Must be greater than zero.' : 'Must be zero or more.'
  return ''
}

/**
 * Structured editing of selected fields. Edits are written into the JSON draft,
 * so the backend validates and versions them exactly as a JSON edit.
 */
export function KeySettings({
  value,
  onChange,
}: {
  value: DataRecord | null
  onChange: (next: DataRecord) => void
}) {
  if (!value)
    return (
      <p className="nifty-muted">Key settings are unavailable while the JSON below is invalid.</p>
    )
  const selection = asText(value.selection)
  const lossLimit = asText(value.monthly_loss_limit)
  const profitTarget = asText(value.monthly_profit_target)
  const lossError = amountError(lossLimit, { allowEmpty: false, positive: false })
  const targetError = amountError(profitTarget, { allowEmpty: true, positive: true })
  const length = asText(value.atr_period)
  const factor = asText(value.atr_multiplier)
  const lengthValid =
    length !== '' &&
    Number.isInteger(Number(length)) &&
    Number(length) >= 2 &&
    Number(length) <= 100
  const factorValid =
    factor !== '' && Number.isFinite(Number(factor)) && Number(factor) > 0 && Number(factor) <= 10
  const set = (key: string, next: RecordValue) => onChange({ ...value, [key]: next })
  const feeFloors = { brokerage: 20, transaction_rate: 0.000355299, stt_sell_rate: 0.0015,
    gst_rate: 0.18, sebi_rate: 0.000001, stamp_buy_rate: 0.00003 }
  const feeNeedsReview = Object.entries(feeFloors).some(([key, minimum]) =>
    value[key] !== undefined && Number(value[key]) < minimum)
  return (
    <div className="nifty-key-settings">
      <div className="nifty-form">
        <Label htmlFor="nifty-supertrend-length">SuperTrend length</Label>
        <Input
          id="nifty-supertrend-length"
          type="number"
          min={2}
          max={100}
          step={1}
          value={length}
          aria-invalid={!lengthValid}
          onChange={(event) =>
            set('atr_period', event.target.value === '' ? '' : Number(event.target.value))
          }
        />
        {!lengthValid && <p role="alert">SuperTrend length: enter an integer from 2 to 100.</p>}
        <Label htmlFor="nifty-supertrend-factor">SuperTrend factor</Label>
        <Input
          id="nifty-supertrend-factor"
          type="number"
          min={0}
          max={10}
          step="any"
          value={factor}
          aria-invalid={!factorValid}
          onChange={(event) =>
            set('atr_multiplier', event.target.value === '' ? '' : Number(event.target.value))
          }
        />
        {!factorValid && (
          <p role="alert">SuperTrend factor: enter a number greater than 0 and at most 10.</p>
        )}
        <p className="nifty-muted">
          Approved defaults: length 20, factor 2 on completed 5-minute and 15-minute candles.
        </p>
        {value.strategy_version !== '3.3.0' && (
          <Button
            type="button"
            onClick={() =>
              onChange({
                ...value,
                strategy_version: '3.3.0',
                confidence_method: 'five-indicator-v2-pinned',
                atr_period: 20,
                atr_multiplier: 2,
                crossover_freshness: Math.min(Number(value.crossover_freshness ?? 2), 2),
              })
            }
          >
            Review approved 20/2 upgrade
          </Button>
        )}
        {feeNeedsReview && (
          <>
            <p role="alert">Stored charge inputs need review before new PAPER entries. Estimates are not broker contract-note charges.</p>
            <Button type="button" onClick={() => onChange({ ...value, ...Object.fromEntries(
              Object.entries(feeFloors).map(([key, minimum]) => [key, Math.max(Number(value[key] ?? minimum), minimum)])
            ) })}>Review published charge estimate</Button>
          </>
        )}
        {['Liquidity', 'Spread', 'Delta', 'Net reward-to-risk', 'Capital efficiency'].map(
          (factor, index) => (
            <div key={factor}>
              <Label htmlFor={`nifty-weight-${index}`}>{factor} weight (%)</Label>
              <Input
                id={`nifty-weight-${index}`}
                type="number"
                min="0"
                max="100"
                step="1"
                value={
                  Array.isArray(value.selector_weights)
                    ? String(value.selector_weights[index] ?? '')
                    : ['30', '25', '15', '20', '10'][index]
                }
                onChange={(event) => {
                  const weights = Array.isArray(value.selector_weights)
                    ? [...value.selector_weights]
                    : ['30', '25', '15', '20', '10']
                  weights[index] = event.target.value
                  set('selector_weights', weights)
                }}
              />
            </div>
          )
        )}
        <p className="nifty-muted">
          Weights must sum to 100. Risk limits remain enforced before ranking.
        </p>
        <Label htmlFor="nifty-selection">Contract moneyness</Label>
        <select
          id="nifty-selection"
          className="nifty-select"
          value={SUPPORTED.has(selection) ? selection : ''}
          onChange={(event) => set('selection', event.target.value)}
        >
          {!SUPPORTED.has(selection) && (
            <option value="" disabled>
              Choose a supported selection
            </option>
          )}
          {SELECTION_OPTIONS.map(([option, label]) => (
            <option key={option} value={option}>
              {label}
            </option>
          ))}
        </select>
        {!SUPPORTED.has(selection) && selection && (
          <p role="alert">
            Stored selection {selection} is not supported. Choose ATM, ITM or DELTA.
          </p>
        )}
        <Label htmlFor="nifty-monthly-loss">Monthly loss limit (Rs)</Label>
        <Input
          id="nifty-monthly-loss"
          inputMode="decimal"
          value={lossLimit}
          aria-invalid={Boolean(lossError)}
          onChange={(event) => set('monthly_loss_limit', event.target.value.trim())}
        />
        {lossError && <p role="alert">Monthly loss limit: {lossError}</p>}
        <Label htmlFor="nifty-monthly-target">Monthly profit target (Rs, optional)</Label>
        <Input
          id="nifty-monthly-target"
          inputMode="decimal"
          placeholder="No target"
          value={profitTarget}
          aria-invalid={Boolean(targetError)}
          onChange={(event) => {
            const next = event.target.value.trim()
            set('monthly_profit_target', next === '' ? null : next)
          }}
        />
        {targetError && <p role="alert">Monthly profit target: {targetError}</p>}
        <p className="nifty-muted">
          Leave the target empty for no monthly profit lock. Changing a target never clears a lock
          that has already latched this month.
        </p>
      </div>
      <Facts
        rows={[
          ['Strategy version', asText(value.strategy_version) || 'Unavailable'],
          ['Max lots', `${asText(value.max_lots) || 'Unavailable'} (sizing may choose 0)`],
          ['Planned loss ceiling (Rs)', asText(value.max_planned_loss) || 'Unavailable'],
          [
            'Minimum projected net reward (Rs)',
            asText(value.min_projected_net_reward) || 'Unavailable',
          ],
          [
            'Profit lock activation (Rs)',
            asText(value.profit_lock_activation_net) || 'Unavailable',
          ],
          ['Profit lock floor (Rs)', asText(value.profit_lock_floor_net) || 'Unavailable'],
          [
            'Trailing distance (premium points)',
            asText(value.trailing_distance_points) || 'Unavailable',
          ],
        ]}
      />
    </div>
  )
}
