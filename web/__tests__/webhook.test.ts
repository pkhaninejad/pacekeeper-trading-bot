import { describe, it, expect, vi } from 'vitest'
import type { Stripe } from 'stripe'
import { handleStripeEvent, type HandlerDeps } from '@/lib/webhook-handler'

function makeDeps(overrides: Partial<HandlerDeps> = {}): HandlerDeps {
  return {
    store: {
      save: vi.fn(),
      findBySession: vi.fn(),
      revokeByPaymentIntent: vi.fn(),
    } as unknown as HandlerDeps['store'],
    sendEmail: vi.fn().mockResolvedValue(undefined),
    readPrivKey: vi.fn().mockReturnValue(Buffer.alloc(32)),
    expiresDays: 365,
    ...overrides,
  }
}

const checkoutEvent = {
  type: 'checkout.session.completed',
  data: {
    object: {
      id: 'cs_test_abc',
      payment_intent: 'pi_abc',
      customer_details: { email: 'buyer@example.com' },
    },
  },
} as unknown as Stripe.Event

const refundEvent = {
  type: 'charge.refunded',
  data: { object: { payment_intent: 'pi_abc' } },
} as unknown as Stripe.Event

describe('handleStripeEvent', () => {
  it('checkout.session.completed: saves record and sends email', async () => {
    const deps = makeDeps()
    await handleStripeEvent(checkoutEvent, deps)

    expect(deps.store.save).toHaveBeenCalledOnce()
    const saveArg = (deps.store.save as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(saveArg.stripeSession).toBe('cs_test_abc')
    expect(saveArg.stripePaymentIntent).toBe('pi_abc')
    expect(saveArg.email).toBe('buyer@example.com')
    expect(saveArg.licenseKey).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/)

    expect(deps.sendEmail).toHaveBeenCalledOnce()
    const emailArg = (deps.sendEmail as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(emailArg.to).toBe('buyer@example.com')
    expect(emailArg.licenseKey).toBe(saveArg.licenseKey)
  })

  it('charge.refunded: revokes license by payment intent', async () => {
    const deps = makeDeps()
    await handleStripeEvent(refundEvent, deps)

    expect(deps.store.revokeByPaymentIntent).toHaveBeenCalledWith('pi_abc')
    expect(deps.sendEmail).not.toHaveBeenCalled()
  })

  it('unknown event type: no-op', async () => {
    const deps = makeDeps()
    const unknownEvent = { type: 'payment_method.attached', data: { object: {} } } as unknown as Stripe.Event
    await handleStripeEvent(unknownEvent, deps)

    expect(deps.store.save).not.toHaveBeenCalled()
    expect(deps.sendEmail).not.toHaveBeenCalled()
  })
})
