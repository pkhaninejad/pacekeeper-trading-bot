use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LicenseInfo {
    pub email: String,
    #[serde(default)]
    pub expires: Option<String>,
}

pub fn validate(_key: &str) -> Result<LicenseInfo, String> {
    Ok(LicenseInfo { email: "Free edition".to_string(), expires: None })
}
