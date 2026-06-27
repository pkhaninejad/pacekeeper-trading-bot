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
