import Database from 'better-sqlite3'
import { mkdirSync } from 'node:fs'
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
