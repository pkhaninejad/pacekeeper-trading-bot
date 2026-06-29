import { describe, it, expect } from 'vitest'
import { generateKeyPair, issueKey } from '@/lib/keygen'
import { verify } from 'node:crypto'

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
    const ok = verify(null, payload, pubKeyObject, sig)
    expect(ok).toBe(true)
  })
})
