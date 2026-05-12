import { createPrivateKey, sign, generateKeyPairSync, KeyObject } from 'node:crypto'

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
  // Export raw private key bytes by stripping the 16-byte PKCS#8 header from DER
  const privDer = privateKey.export({ format: 'der', type: 'pkcs8' }) as Buffer
  const privBytes = privDer.subarray(16)
  return { privBytes, pubKeyObject: publicKey }
}
