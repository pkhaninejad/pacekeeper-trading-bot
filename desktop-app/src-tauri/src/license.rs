use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

// Run `python scripts/keygen.py --generate` once, then paste the printed
// byte array here before shipping.
const PUBLIC_KEY: [u8; 32] = [0x4f, 0x0e, 0x3a, 0xef, 0x5e, 0xe8, 0x73, 0x8f, 0x94, 0xfc, 0x11, 0xbd, 0x3b, 0x7b, 0x37, 0x76, 0x2e, 0x01, 0x6f, 0x82, 0x23, 0x86, 0x7b, 0x21, 0x69, 0x41, 0xf3, 0x16, 0x51, 0xd6, 0x82, 0x95];

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LicenseInfo {
    pub email: String,
    #[serde(default)]
    pub expires: Option<String>,
}

pub fn validate(key: &str) -> Result<LicenseInfo, String> {
    let key = key.trim();
    let dot = key.find('.').ok_or("Invalid license key.")?;
    let payload_b64 = &key[..dot];
    let sig_b64 = &key[dot + 1..];

    let payload_bytes = URL_SAFE_NO_PAD
        .decode(payload_b64)
        .map_err(|_| "Malformed license key.".to_string())?;
    let sig_bytes = URL_SAFE_NO_PAD
        .decode(sig_b64)
        .map_err(|_| "Malformed license key.".to_string())?;

    let verifying_key = VerifyingKey::from_bytes(&PUBLIC_KEY)
        .map_err(|_| "Internal error: public key not configured. Contact support.".to_string())?;
    let signature = Signature::from_slice(&sig_bytes)
        .map_err(|_| "Malformed license key.".to_string())?;

    verifying_key
        .verify(&payload_bytes, &signature)
        .map_err(|_| "Invalid license key — contact khaninejad@gmail.com.".to_string())?;

    let info: LicenseInfo = serde_json::from_slice(&payload_bytes)
        .map_err(|_| "Malformed license payload.".to_string())?;

    if let Some(ref exp) = info.expires {
        if exp.as_str() < today_iso().as_str() {
            return Err(format!(
                "License expired on {exp}. Renew at khaninejad@gmail.com."
            ));
        }
    }

    Ok(info)
}

/// Returns today's date as YYYY-MM-DD using only std — no chrono needed.
fn today_iso() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let days = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        / 86400;

    // Howard Hinnant's civil-calendar algorithm
    let z = days as i64 + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };

    format!("{y:04}-{m:02}-{d:02}")
}
