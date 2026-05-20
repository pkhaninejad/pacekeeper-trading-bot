# Payment & Fulfillment Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `web/` Next.js app that receives Stripe webhooks, issues Ed25519 license keys, sends Resend emails, and stores records in SQLite — all within 2 minutes of purchase. The same app will expand into the landing page / storefront later.

**Architecture:** Next.js App Router API routes handle Stripe events synchronously: verify signature → issue Ed25519 key via Node.js built-in `crypto` → write to SQLite via `better-sqlite3` → send email via `resend` SDK. Handler logic lives in `src/lib/` and is tested independently of the route layer. The trading bot (`src/`) and desktop app (`desktop-app/`) are untouched.

**Tech Stack:** Next.js 15, TypeScript, `stripe`, `resend`, `better-sqlite3`, Node.js `crypto` (built-in, no extra dep for Ed25519), Vitest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `web/` | create | Next.js app root (scaffolded) |
| `web/next.config.ts` | modify | add `serverExternalPackages: ['better-sqlite3']` |
| `web/vitest.config.ts` | create | Vitest config with `@` alias and node environment |
| `web/src/lib/keygen.ts` | create | Ed25519 key issuance using Node built-in `crypto` |
| `web/src/lib/store.ts` | create | `LicenseStore` class using `better-sqlite3` |
| `web/src/lib/email-template.ts` | create | HTML email template string function |
| `web/src/lib/email.ts` | create | `sendFulfillmentEmail()` via `resend` SDK |
| `web/src/lib/webhook-handler.ts` | create | Pure handler logic (injectable deps, fully testable) |
| `web/src/app/api/health/route.ts` | create | `GET /api/health` → `{ status: "ok" }` |
| `web/src/app/api/webhooks/stripe/route.ts` | create | `POST /api/webhooks/stripe` — wires real deps to handler |
| `web/src/app/page.tsx` | modify | Landing page placeholder |
| `web/__tests__/keygen.test.ts` | create | Key issuance + signature round-trip |
| `web/__tests__/store.test.ts` | create | CRUD + revoke lifecycle |
| `web/__tests__/email.test.ts` | create | Email send + error path |
| `web/__tests__/webhook.test.ts` | create | Handler logic for all Stripe event types |

---

## Task 1: Scaffold Next.js App

**Files:**
- Create: `web/` (via `create-next-app`)
- Modify: `web/next.config.ts`
- Create: `web/vitest.config.ts`
- Modify: `web/package.json` (add deps)

- [ ] **Step 1: Scaffold the app**

Run from the repo root:
```bash
pnpm dlx create-next-app@latest web --typescript --no-tailwind --eslint --app --src-dir --import-alias "@/*" --no-git
```
When prompted, accept all defaults.

- [ ] **Step 2: Install runtime deps**

```bash
cd web
pnpm add stripe resend better-sqlite3
```

- [ ] **Step 3: Install test deps**

```bash
pnpm add -D vitest @vitejs/plugin-react jsdom @types/better-sqlite3
```

- [ ] **Step 4: Add test script to package.json**

Open `web/package.json` and add `"test": "vitest run"` and `"test:watch": "vitest"` to the `scripts` block:
```json
"scripts": {
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "next lint",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 5: Create vitest.config.ts**

`web/vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

- [ ] **Step 6: Patch next.config.ts for better-sqlite3**

Open `web/next.config.ts` and replace its contents with:
```typescript
import type { NextConfig } from 'next'

const config: NextConfig = {
  serverExternalPackages: ['better-sqlite3'],
}

export default config
```

- [ ] **Step 7: Create __tests__ directory and smoke-test Vitest**

```bash
mkdir web/__tests__
echo 'import { expect, test } from "vitest"; test("true", () => expect(true).toBe(true))' > web/__tests__/smoke.test.ts
cd web && pnpm test
```
Expected: `1 passed`

Remove the smoke test file:
```bash
rm web/__tests__/smoke.test.ts
```

- [ ] **Step 8: Commit**

From repo root:
```bash
git add web/
git commit -m "feat(web): scaffold Next.js app for fulfillment and landing page"
```

---

## Task 2: Keygen Utility

**Files:**
- Create: `web/src/lib/keygen.ts`
- Create: `web/__tests__/keygen.test.ts`

The Ed25519 private key on disk is 32 raw bytes (written by `scripts/keygen.py`). Node.js `crypto.createPrivateKey` requires PKCS#8 DER format, so we prepend a fixed 16-byte ASN.1 header. The resulting key format is identical to what Python's `cryptography` library produces.

- [ ] **Step 1: Write the failing tests**

`web/__tests__/keygen.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { generateKeyPair, issueKey } from '@/lib/keygen'
import { createPublicKey, verify } from 'node:crypto'

describe('issueKey', () => {
  it('returns a dot-separated base64url string', () => {
    const { privBytes } = generateKeyPair()
    const key = issueKey('buyer@example.com', privBytes)
    const parts = key.split('.')
    expect(parts).toHaveLength(2)
    expect(parts[0].length).toBeGreaterThan(0)
    expect(parts[1].length).toBeGreaterThan(0)
  })

  it('payload contains email and expiry', () => {
    const { privBytes } = generateKeyPair()
    const key = issueKey('buyer@example.com', privBytes, 30)
    const payloadJson = JSON.parse(
      Buffer.from(key.split('.')[0], 'base64url').toString('utf8')
    )
    expect(payloadJson.email).toBe('buyer@example.com')
    const expected = new Date()
    expected.setDate(expected.getDate() + 30)
    expect(payloadJson.expires).toBe(expected.toISOString().split('T')[0])
  })

  it('signature is verifiable with the corresponding public key', () => {
    const { privBytes, pubKeyObject } = generateKeyPair()
    const key = issueKey('buyer@example.com', privBytes)
    const [payloadB64, sigB64] = key.split('.')
    const payload = Buffer.from(payloadB64, 'base64url')
    const sig = Buffer.from(sigB64, 'base64url')
    // verify() returns true/false; throws on bad sig — we assert it doesn't throw
    const ok = verify(null, payload, pubKeyObject, sig)
    expect(ok).toBe(true)
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd web && pnpm test __tests__/keygen.test.ts
```
Expected: `Cannot find module '@/lib/keygen'`

- [ ] **Step 3: Implement**

`web/src/lib/keygen.ts`:
```typescript
import { createPrivateKey, createPublicKey, sign, generateKeyPairSync, KeyObject } from 'node:crypto'

// Fixed ASN.1 PKCS#8 header for Ed25519 raw private key (32 bytes → 48 bytes DER)
const PKCS8_HEADER = Buffer.from('302e020100300506032b657004220420', 'hex')

function wrapPrivKey(rawBytes: Buffer): KeyObject {
  return createPrivateKey({
    key: Buffer.concat([PKCS8_HEADER, rawBytes]),
    format: 'der',
    type: 'pkcs8',
  })
}

export function issueKey(
  email: string,
  rawPrivBytes: Buffer,
  expiresDays = 365
): string {
  const expires = new Date()
  expires.setDate(expires.getDate() + expiresDays)
  const expiresStr = expires.toISOString().split('T')[0]

  const payload = Buffer.from(JSON.stringify({ email, expires: expiresStr }))
  const privKey = wrapPrivKey(rawPrivBytes)
  const sig = sign(null, payload, privKey)

  return payload.toString('base64url') + '.' + sig.toString('base64url')
}

/** Test helper: generate a fresh Ed25519 key pair. Not used in production. */
export function generateKeyPair(): { privBytes: Buffer; pubKeyObject: KeyObject } {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519')
  // Export private key raw bytes (stripped from DER)
  const privDer = privateKey.export({ format: 'der', type: 'pkcs8' }) as Buffer
  const privBytes = privDer.subarray(16) // skip the 16-byte PKCS#8 header
  return { privBytes, pubKeyObject: publicKey }
}
```

- [ ] **Step 4: Run to verify passing**

```bash
cd web && pnpm test __tests__/keygen.test.ts
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/keygen.ts web/__tests__/keygen.test.ts
git commit -m "feat(web): add issueKey utility using Node.js built-in Ed25519"
```

---

## Task 3: License Store

**Files:**
- Create: `web/src/lib/store.ts`
- Create: `web/__tests__/store.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/__tests__/store.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { LicenseStore } from '@/lib/store'

function makeTmpStore() {
  const dbPath = join(tmpdir(), `test-${randomUUID()}.db`)
  return new LicenseStore(dbPath)
}

describe('LicenseStore', () => {
  it('saves and retrieves a license record', () => {
    const store = makeTmpStore()
    store.save({
      stripeSession: 'cs_1',
      stripePaymentIntent: 'pi_1',
      email: 'buyer@example.com',
      licenseKey: 'PAYLOAD.SIG',
      expiresOn: '2027-01-01',
    })
    const rec = store.findBySession('cs_1')
    expect(rec?.email).toBe('buyer@example.com')
    expect(rec?.license_key).toBe('PAYLOAD.SIG')
    expect(rec?.status).toBe('active')
  })

  it('revokes a license by payment intent', () => {
    const store = makeTmpStore()
    store.save({
      stripeSession: 'cs_2',
      stripePaymentIntent: 'pi_2',
      email: 'buyer@example.com',
      licenseKey: 'PAYLOAD.SIG',
      expiresOn: '2027-01-01',
    })
    store.revokeByPaymentIntent('pi_2')
    const rec = store.findBySession('cs_2')
    expect(rec?.status).toBe('revoked')
  })

  it('duplicate session is idempotent (INSERT OR IGNORE)', () => {
    const store = makeTmpStore()
    const params = {
      stripeSession: 'cs_3',
      stripePaymentIntent: 'pi_3',
      email: 'buyer@example.com',
      licenseKey: 'PAYLOAD.SIG',
      expiresOn: '2027-01-01',
    }
    store.save(params)
    expect(() => store.save(params)).not.toThrow()
    const rec = store.findBySession('cs_3')
    expect(rec).not.toBeNull()
  })

  it('findBySession returns undefined for unknown session', () => {
    const store = makeTmpStore()
    expect(store.findBySession('cs_unknown')).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd web && pnpm test __tests__/store.test.ts
```
Expected: `Cannot find module '@/lib/store'`

- [ ] **Step 3: Implement**

`web/src/lib/store.ts`:
```typescript
import Database from 'better-sqlite3'
import { mkdirSync, existsSync } from 'node:fs'
import { dirname } from 'node:path'

const CREATE_SCHEMA = `
CREATE TABLE IF NOT EXISTS licenses (
  id                    INTEGER PRIMARY KEY,
  stripe_session        TEXT UNIQUE NOT NULL,
  stripe_payment_intent TEXT,
  email                 TEXT NOT NULL,
  license_key           TEXT NOT NULL,
  issued_at             TEXT NOT NULL,
  expires_on            TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_licenses_email ON licenses(email);
CREATE INDEX IF NOT EXISTS idx_licenses_pi ON licenses(stripe_payment_intent);
`

export interface LicenseRecord {
  id: number
  stripe_session: string
  stripe_payment_intent: string | null
  email: string
  license_key: string
  issued_at: string
  expires_on: string
  status: 'active' | 'revoked'
}

export class LicenseStore {
  private db: Database.Database

  constructor(dbPath: string) {
    mkdirSync(dirname(dbPath), { recursive: true })
    this.db = new Database(dbPath)
    this.db.exec(CREATE_SCHEMA)
  }

  save(params: {
    stripeSession: string
    stripePaymentIntent: string | null
    email: string
    licenseKey: string
    expiresOn: string
  }): void {
    this.db
      .prepare(
        `INSERT OR IGNORE INTO licenses
           (stripe_session, stripe_payment_intent, email, license_key, issued_at, expires_on)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .run(
        params.stripeSession,
        params.stripePaymentIntent,
        params.email,
        params.licenseKey,
        new Date().toISOString(),
        params.expiresOn,
      )
  }

  findBySession(stripeSession: string): LicenseRecord | undefined {
    return this.db
      .prepare('SELECT * FROM licenses WHERE stripe_session = ?')
      .get(stripeSession) as LicenseRecord | undefined
  }

  revokeByPaymentIntent(paymentIntent: string): void {
    this.db
      .prepare("UPDATE licenses SET status = 'revoked' WHERE stripe_payment_intent = ?")
      .run(paymentIntent)
  }
}
```

- [ ] **Step 4: Run to verify passing**

```bash
cd web && pnpm test __tests__/store.test.ts
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/store.ts web/__tests__/store.test.ts
git commit -m "feat(web): add LicenseStore using better-sqlite3"
```

---

## Task 4: Email Client

**Files:**
- Create: `web/src/lib/email-template.ts`
- Create: `web/src/lib/email.ts`
- Create: `web/__tests__/email.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/__tests__/email.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock resend before importing the module under test
vi.mock('resend', () => ({
  Resend: vi.fn().mockImplementation(() => ({
    emails: {
      send: vi.fn().mockResolvedValue({ data: { id: 'email_123' }, error: null }),
    },
  })),
}))

import { sendFulfillmentEmail } from '@/lib/email'
import { Resend } from 'resend'

describe('sendFulfillmentEmail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    process.env.RESEND_API_KEY = 're_test'
    process.env.DOWNLOAD_URL_MACOS = 'https://example.com/mac.dmg'
    process.env.DOWNLOAD_URL_WINDOWS = 'https://example.com/win.exe'
  })

  it('calls resend.emails.send with correct recipient and license key in body', async () => {
    await sendFulfillmentEmail({
      to: 'buyer@example.com',
      licenseKey: 'PAYLOAD.SIG',
      expiresOn: '2027-01-01',
    })

    const instance = (Resend as unknown as ReturnType<typeof vi.fn>).mock.results[0].value
    expect(instance.emails.send).toHaveBeenCalledOnce()
    const [payload] = instance.emails.send.mock.calls[0]
    expect(payload.to).toEqual(['buyer@example.com'])
    expect(payload.html).toContain('PAYLOAD.SIG')
    expect(payload.subject).toContain('Pacekeeper')
  })

  it('propagates Resend errors', async () => {
    const { Resend: ResendMock } = await import('resend')
    const instance = (ResendMock as unknown as ReturnType<typeof vi.fn>).mock.results[0].value
    instance.emails.send.mockResolvedValueOnce({ data: null, error: { message: 'invalid key' } })

    await expect(
      sendFulfillmentEmail({ to: 'x@y.com', licenseKey: 'K', expiresOn: '2027-01-01' })
    ).rejects.toThrow('invalid key')
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd web && pnpm test __tests__/email.test.ts
```
Expected: `Cannot find module '@/lib/email'`

- [ ] **Step 3: Implement the template**

`web/src/lib/email-template.ts`:
```typescript
export function fulfillmentHtml(params: {
  licenseKey: string
  downloadUrlMacos: string
  downloadUrlWindows: string
  expiresOn: string
}): string {
  const { licenseKey, downloadUrlMacos, downloadUrlWindows, expiresOn } = params
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h1 style="color:#1E5BFF">Your Pacekeeper License</h1>
  <p>Thanks for your purchase! Your license key is below.</p>
  <pre style="background:#f4f4f4;padding:16px;border-radius:4px;word-break:break-all;font-size:13px">${licenseKey}</pre>
  <h2>Download</h2>
  <p>
    <a href="${downloadUrlMacos}" style="background:#1E5BFF;color:#fff;padding:10px 20px;text-decoration:none;border-radius:4px;margin-right:8px">macOS</a>
    <a href="${downloadUrlWindows}" style="background:#1E5BFF;color:#fff;padding:10px 20px;text-decoration:none;border-radius:4px">Windows</a>
  </p>
  <h2>Getting Started</h2>
  <ol>
    <li>Download and install Pacekeeper for your platform.</li>
    <li>On first launch, paste your license key when prompted.</li>
    <li>Add your Trading212 API key and Anthropic API key in Settings.</li>
  </ol>
  <p style="color:#888;font-size:12px">Questions? Email khaninejad@gmail.com — License expires ${expiresOn}.</p>
</body>
</html>`
}
```

- [ ] **Step 4: Implement the email client**

`web/src/lib/email.ts`:
```typescript
import { Resend } from 'resend'
import { fulfillmentHtml } from './email-template'

export async function sendFulfillmentEmail(params: {
  to: string
  licenseKey: string
  expiresOn: string
}): Promise<void> {
  const resend = new Resend(process.env.RESEND_API_KEY)
  const html = fulfillmentHtml({
    licenseKey: params.licenseKey,
    downloadUrlMacos: process.env.DOWNLOAD_URL_MACOS ?? '',
    downloadUrlWindows: process.env.DOWNLOAD_URL_WINDOWS ?? '',
    expiresOn: params.expiresOn,
  })

  const { error } = await resend.emails.send({
    from: process.env.FROM_EMAIL ?? 'Pacekeeper <noreply@pacekeeper.app>',
    to: [params.to],
    subject: 'Your Pacekeeper License & Download',
    html,
  })

  if (error) {
    throw new Error(error.message)
  }
}
```

- [ ] **Step 5: Run to verify passing**

```bash
cd web && pnpm test __tests__/email.test.ts
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/email-template.ts web/src/lib/email.ts web/__tests__/email.test.ts
git commit -m "feat(web): add Resend email client and HTML template"
```

---

## Task 5: Webhook Handler

**Files:**
- Create: `web/src/lib/webhook-handler.ts`
- Create: `web/__tests__/webhook.test.ts`

The handler is a pure async function that receives a `Stripe.Event` plus injected `store` and `email` deps. This keeps it fully testable without touching Next.js route machinery.

- [ ] **Step 1: Write the failing tests**

`web/__tests__/webhook.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
```

- [ ] **Step 2: Run to verify failure**

```bash
cd web && pnpm test __tests__/webhook.test.ts
```
Expected: `Cannot find module '@/lib/webhook-handler'`

- [ ] **Step 3: Implement**

`web/src/lib/webhook-handler.ts`:
```typescript
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
```

- [ ] **Step 4: Run to verify passing**

```bash
cd web && pnpm test __tests__/webhook.test.ts
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/webhook-handler.ts web/__tests__/webhook.test.ts
git commit -m "feat(web): add handleStripeEvent with injectable deps"
```

---

## Task 6: API Routes + Landing Page Placeholder

**Files:**
- Create: `web/src/app/api/health/route.ts`
- Create: `web/src/app/api/webhooks/stripe/route.ts`
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Health route**

`web/src/app/api/health/route.ts`:
```typescript
import { NextResponse } from 'next/server'

export function GET() {
  return NextResponse.json({ status: 'ok' })
}
```

- [ ] **Step 2: Stripe webhook route**

`web/src/app/api/webhooks/stripe/route.ts`:
```typescript
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
```

- [ ] **Step 3: Landing page placeholder**

Replace `web/src/app/page.tsx` contents with:
```tsx
export default function Home() {
  return (
    <main style={{ fontFamily: 'Inter, sans-serif', maxWidth: 640, margin: '80px auto', padding: '0 24px' }}>
      <h1 style={{ color: '#1E5BFF', fontSize: 32, fontWeight: 700 }}>Pacekeeper</h1>
      <p style={{ color: '#444', fontSize: 18, marginTop: 16 }}>
        AI-powered trading automation. Coming soon.
      </p>
    </main>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add web/src/app/api/ web/src/app/page.tsx
git commit -m "feat(web): add Stripe webhook route, health endpoint, landing placeholder"
```

---

## Task 7: Add .env.local.example + Full Suite Check

**Files:**
- Create: `web/.env.local.example`

- [ ] **Step 1: Create env example file**

`web/.env.local.example`:
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
DOWNLOAD_URL_MACOS=https://github.com/.../releases/download/v1.0.0/Pacekeeper_1.0.0_aarch64.dmg
DOWNLOAD_URL_WINDOWS=https://github.com/.../releases/download/v1.0.0/Pacekeeper_1.0.0_x64-setup.exe
FROM_EMAIL=Pacekeeper <noreply@pacekeeper.app>
PRIVATE_KEY_PATH=../.pacekeeper-private.key
LICENSE_DB_PATH=../data/licenses.db
LICENSE_EXPIRES_DAYS=365
```

- [ ] **Step 2: Run the full web test suite**

```bash
cd web && pnpm test
```
Expected: `12 passed` (3 keygen + 4 store + 2 email + 3 webhook)

- [ ] **Step 3: Run Python tests to confirm no regressions in the trading bot**

From repo root:
```bash
.venv/bin/python -m pytest tests/ -v
```
Expected: all pre-existing tests still pass

- [ ] **Step 4: Commit**

```bash
git add web/.env.local.example
git commit -m "chore(web): add .env.local.example for fulfillment config"
```

---

## Task 8: Open PR

- [ ] **Step 1: Create branch if not already on one**

```bash
git checkout -b feat/payment-fulfillment
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/payment-fulfillment
gh pr create \
  --title "feat(web): payment and fulfillment integration (#87)" \
  --body "$(cat <<'EOF'
## Summary
- New `web/` Next.js app: Stripe webhook → Ed25519 key issuance → Resend email → SQLite record
- `POST /api/webhooks/stripe` handles `checkout.session.completed` (issue + email) and `charge.refunded` (revoke)
- Handler logic in `src/lib/webhook-handler.ts` is fully injectable and covered by unit tests
- Landing page placeholder at `/` — ready to expand into storefront
- Does not touch trading bot (`src/`) or desktop app (`desktop-app/`)

## Test Plan
- [ ] `cd web && pnpm test` — all pass
- [ ] `pytest tests/ -v` — no regressions in trading bot
- [ ] Manual: `stripe listen --forward-to localhost:3000/api/webhooks/stripe` then `stripe trigger checkout.session.completed`
- [ ] Verify email received with license key, download links, expiry date

Closes #87
EOF
)"
```
