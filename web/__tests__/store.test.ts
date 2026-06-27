import { describe, it, expect } from 'vitest'
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
