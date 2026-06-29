import { NextRequest, NextResponse } from 'next/server'
import Stripe from 'stripe'
import { readFileSync } from 'node:fs'
import { LicenseStore } from '@/lib/store'
import { sendFulfillmentEmail } from '@/lib/email'
import { handleStripeEvent } from '@/lib/webhook-handler'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)
const store = new LicenseStore(process.env.LICENSE_DB_PATH ?? 'data/licenses.db')

export async function POST(req: NextRequest) {
  const payload = await req.text()
  const sig = req.headers.get('stripe-signature') ?? ''

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(payload, sig, process.env.STRIPE_WEBHOOK_SECRET!)
  } catch {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  await handleStripeEvent(event, {
    store,
    sendEmail: sendFulfillmentEmail,
    readPrivKey: () => readFileSync(process.env.PRIVATE_KEY_PATH ?? '.pacekeeper-private.key'),
    expiresDays: parseInt(process.env.LICENSE_EXPIRES_DAYS ?? '365', 10),
  })

  return NextResponse.json({ received: true })
}
