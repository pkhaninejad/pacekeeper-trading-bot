import type { Stripe } from 'stripe'
import type { LicenseStore } from './store'
import { issueKey } from './keygen'

export interface HandlerDeps {
  store: Pick<LicenseStore, 'save' | 'findBySession' | 'revokeByPaymentIntent'>
  sendEmail: (params: { to: string; licenseKey: string; expiresOn: string }) => Promise<void>
  readPrivKey: () => Buffer
  expiresDays: number
}

export async function handleStripeEvent(
  event: Stripe.Event,
  deps: HandlerDeps
): Promise<void> {
  const { store, sendEmail, readPrivKey, expiresDays } = deps

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session
    const email = session.customer_details?.email
    if (!email) return

    const expires = new Date()
    expires.setDate(expires.getDate() + expiresDays)
    const expiresOn = expires.toISOString().split('T')[0]

    const licenseKey = issueKey(email, readPrivKey(), expiresDays)

    store.save({
      stripeSession: session.id,
      stripePaymentIntent: (session.payment_intent as string) ?? null,
      email,
      licenseKey,
      expiresOn,
    })

    await sendEmail({ to: email, licenseKey, expiresOn })
    return
  }

  if (event.type === 'charge.refunded') {
    const charge = event.data.object as Stripe.Charge
    const pi = charge.payment_intent as string | undefined
    if (pi) store.revokeByPaymentIntent(pi)
  }
}
