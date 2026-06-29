use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

// Offline fallback signing key. Run `python scripts/keygen.py --generate` once,
// then paste the printed byte array here before shipping. Used only when the
// online license server is unreachable.
const PUBLIC_KEY: [u8; 32] = [0x4f, 0x0e, 0x3a, 0xef, 0x5e, 0xe8, 0x73, 0x8f, 0x94, 0xfc, 0x11, 0xbd, 0x3b, 0x7b, 0x37, 0x76, 0x2e, 0x01, 0x6f, 0x82, 0x23, 0x86, 0x7b, 0x21, 0x69, 0x41, 0xf3, 0x16, 0x51, 0xd6, 0x82, 0x95];

// Online license server (WordPress/WooCommerce). Overridable at runtime via the
// LICENSE_SERVER_URL env var. A desktop app has no domain, so we send a stable
// product identifier as the `domain` the server validates against.
const LICENSE_SERVER_URL: &str = "https://wallstrdev.com/wp-json/wds-license/v1/validate";
const PRODUCT_DOMAIN: &str = "pacekeeper-desktop";
// Product slug the license server validates against (must match the catalog
// entry created in wds-license-server). Mismatched products are rejected.
const PRODUCT_SLUG: &str = "pacekeeper";

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LicenseInfo {
    pub email: String,
    #[serde(default)]
    pub expires: Option<String>,
}

#[derive(Deserialize)]
struct ServerResponse {
    #[serde(default)]
    valid: bool,
    #[serde(default)]
    expires: Option<String>,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    reason: Option<String>,
}

enum OnlineError {
    /// The server explicitly rejected the key — final, do not fall back.
    Invalid(String),
    /// Could not reach or parse the server — fall back to offline verification.
    Unreachable,
}

/// Validate a license key. Tries the online license server first; on a network
/// error it falls back to offline signature verification so the app still works
/// without connectivity. A server *rejection* is final (no offline fallback).
pub fn validate(key: &str) -> Result<LicenseInfo, String> {
    let key = key.trim();
    if key.is_empty() {
        return Err("Enter your license key.".to_string());
    }
    match validate_online(key) {
        Ok(info) => Ok(info),
        Err(OnlineError::Invalid(msg)) => Err(msg),
        Err(OnlineError::Unreachable) => validate_offline(key),
    }
}

fn validate_online(key: &str) -> Result<LicenseInfo, OnlineError> {
    // Run the blocking HTTP call on a dedicated thread so it never collides with
    // Tauri's async runtime (reqwest::blocking panics inside a running runtime).
    let key = key.to_string();
    std::thread::spawn(move || validate_online_blocking(&key))
        .join()
        .unwrap_or(Err(OnlineError::Unreachable))
}

fn validate_online_blocking(key: &str) -> Result<LicenseInfo, OnlineError> {
    let url = std::env::var("LICENSE_SERVER_URL").unwrap_or_else(|_| LICENSE_SERVER_URL.to_string());
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|_| OnlineError::Unreachable)?;
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "key": key, "domain": PRODUCT_DOMAIN, "product": PRODUCT_SLUG }))
        .send()
        .map_err(|_| OnlineError::Unreachable)?;
    let body: ServerResponse = resp.json().map_err(|_| OnlineError::Unreachable)?;

    if !body.valid {
        return Err(OnlineError::Invalid(body.reason.unwrap_or_else(|| {
            "Invalid license key — contact khaninejad@gmail.com.".to_string()
        })));
    }
    if let Some(ref exp) = body.expires {
        if exp.as_str() < today_iso().as_str() {
            return Err(OnlineError::Invalid(format!(
                "License expired on {exp}. Renew at khaninejad@gmail.com."
            )));
        }
    }
    Ok(LicenseInfo {
        email: body.email.unwrap_or_else(|| "Licensed".to_string()),
        expires: body.expires,
    })
}

/// Offline fallback: verify a locally-signed (ed25519) key. Used only when the
/// license server is unreachable.
fn validate_offline(key: &str) -> Result<LicenseInfo, String> {
    let dot = key
        .find('.')
        .ok_or("Could not reach the license server. Check your connection and try again.")?;
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
