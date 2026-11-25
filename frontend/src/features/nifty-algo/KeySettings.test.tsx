import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { KeySettings } from './KeySettings'

const value = {
  confidence_method: 'five-indicator-v2-pinned',
  strategy_version: '3.3.0',
  atr_period: 20,
  atr_multiplier: 2,
  selection: 'ATM',
  monthly_loss_limit: '2000',
  monthly_profit_target: null,
}

describe('SuperTrend structured settings', () => {
  it('shows effective inputs and writes both numeric values into the configuration draft', () => {
    const onChange = vi.fn()
    render(<KeySettings value={value} onChange={onChange} />)
    expect(screen.getByLabelText('SuperTrend length')).toHaveValue(20)
    expect(screen.getByLabelText('SuperTrend factor')).toHaveValue(2)
    fireEvent.change(screen.getByLabelText('SuperTrend length'), { target: { value: '21' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...value, atr_period: 21 })
    fireEvent.change(screen.getByLabelText('SuperTrend factor'), { target: { value: '2.5' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...value, atr_multiplier: 2.5 })
  })

  it('marks invalid length and factor using backend limits', () => {
    render(
      <KeySettings value={{ ...value, atr_period: 1.5, atr_multiplier: 0 }} onChange={vi.fn()} />
    )
    expect(screen.getByLabelText('SuperTrend length')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('SuperTrend factor')).toHaveAttribute('aria-invalid', 'true')
  })

  it('requires an explicit upgrade action for legacy 10/3 and only changes the draft', () => {
    const onChange = vi.fn()
    const legacy = {
      ...value,
      strategy_version: '3.2.0',
      confidence_method: 'five-indicator-v1',
      atr_period: 10,
      atr_multiplier: 3,
    }
    render(<KeySettings value={legacy} onChange={onChange} />)
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Review approved 20/2 upgrade' }))
    expect(onChange).toHaveBeenCalledWith({ ...value, crossover_freshness: 2 })
    expect(legacy.atr_period).toBe(10)
  })

  it('requires charge review and preserves higher custom estimates in the draft', () => {
    const onChange = vi.fn()
    const stored = { ...value, brokerage: 25, stt_sell_rate: 0.000625 }
    render(<KeySettings value={stored} onChange={onChange} />)
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Review published charge estimate' }))
    expect(onChange).toHaveBeenCalledWith({ ...stored, brokerage: 25,
      transaction_rate: 0.000355299, stt_sell_rate: 0.0015, gst_rate: 0.18,
      sebi_rate: 0.000001, stamp_buy_rate: 0.00003 })
    expect(stored.stt_sell_rate).toBe(0.000625)
  })
})
