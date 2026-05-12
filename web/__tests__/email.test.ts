import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock resend before importing the module under test
vi.mock('resend', () => ({
  Resend: vi.fn().mockImplementation(function () {
    return {
      emails: {
        send: vi.fn().mockResolvedValue({ data: { id: 'email_123' }, error: null }),
      },
    }
  }),
}))

import { sendFulfillmentEmail } from '@/lib/email'
import { Resend } from 'resend'

describe('sendFulfillmentEmail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Re-apply the constructor implementation after clearAllMocks resets it
    ;(Resend as unknown as ReturnType<typeof vi.fn>).mockImplementation(function () {
      return {
        emails: {
          send: vi.fn().mockResolvedValue({ data: { id: 'email_123' }, error: null }),
        },
      }
    })
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
    // Override the send to return an error for this test
    ;(ResendMock as unknown as ReturnType<typeof vi.fn>).mockImplementationOnce(function () {
      return {
        emails: {
          send: vi.fn().mockResolvedValue({ data: null, error: { message: 'invalid key' } }),
        },
      }
    })

    await expect(
      sendFulfillmentEmail({ to: 'x@y.com', licenseKey: 'K', expiresOn: '2027-01-01' })
    ).rejects.toThrow('invalid key')
  })
})
