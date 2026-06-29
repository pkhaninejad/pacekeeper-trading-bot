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
