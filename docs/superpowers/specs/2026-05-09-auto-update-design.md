# Auto-Update Feature Design — Pacekeeper Desktop

**Date:** 2026-05-09
**Issue:** [#82 P0: In-app automatic updates](https://github.com/pkhaninejad/Claude-trade-bot/issues/82)
**Milestone:** Sellable v1 (Desktop Binary)

---

## Summary

Deliver seamless, one-click updates to Pacekeeper desktop users. The app checks GitHub Releases for a newer version on startup, shows a non-blocking banner when one is available, and installs + restarts in one click. Update packages are signed with Tauri's Minisign-based keypair to guarantee integrity.

---

## Decisions

| Question | Decision | Rationale |
|---|---|---|
| Update server | GitHub Releases | Zero hosting cost; fits existing CI; `tauri-action` generates `latest.json` automatically |
| Release channels | Stable only | Beta channel deferred until there is a user base to test pre-releases |
| Signing | Tauri updater signing (Minisign) | Satisfies integrity requirement; no Apple/Windows certs needed for v1 |
| UX pattern | Check on startup, top banner | Non-blocking; satisfies "< 2 clicks" acceptance criterion |

---

## Architecture

### Components

#### 1. `tauri-plugin-updater` (Rust)
- Added to `Cargo.toml` and `tauri.conf.json`
- Called in `main.rs` on app startup (after the main window opens)
- Checks `https://github.com/pkhaninejad/Claude-trade-bot/releases/latest/download/latest.json`
- Verifies Minisign signature before any install
- Emits a Tauri event `update-available` with payload `{ version, body }` when a newer version is found
- Exposes a Tauri command `install_update` that the frontend calls to trigger download + install + restart

#### 2. `UpdateBanner.tsx` (React, new file)
- Listens for the `update-available` event via `@tauri-apps/api/event`
- When received: renders a top-of-page amber notification bar
- Displays new version number, expandable release notes (`body` field from the event)
- "Install & Restart" button → calls `install_update` command → shows download progress spinner
- "✕" dismiss button → hides for this session only (reappears on next launch)
- Error state: renders in `--crimson-soft` with error message and a manual download link

#### 3. Version Footer
- `App.tsx` footer displays the current app version using `getVersion()` from `@tauri-apps/api/app`
- Format: `Pacekeeper v0.1.0`

#### 4. `release.yml` (GitHub Actions, new file)
- Triggers on tags matching `v*.*.*`
- Builds signed macOS (`.dmg`, `.app.tar.gz`) and Windows (`.msi`, `.msi.zip`) bundles
- Uses `tauri-apps/tauri-action` to publish a GitHub Release with all artifacts and `latest.json`
- `TAURI_SIGNING_PRIVATE_KEY` injected from GitHub Actions secret

#### 5. Minisign Keypair
- Generated once with `pnpm tauri signer generate`
- Private key → stored in GitHub Actions secret `TAURI_SIGNING_PRIVATE_KEY`
- Public key → embedded in `tauri.conf.json` under `plugins.updater.pubkey`

---

## Startup Flow

```
App launches
  → plugin.check() polls latest.json
      → no update or network error: silent, nothing shown
      → update available:
          → Tauri emits update-available { version, body }
          → UpdateBanner renders at top of launcher
              → user clicks "Install & Restart"
              → download starts (spinner shown, button disabled)
              → signature verified ✓
              → installer runs, app restarts
              → (on error: banner turns crimson, shows retry + manual link)
```

---

## Release Workflow

1. Developer bumps `version` in `tauri.conf.json` and `package.json`
2. Commits and pushes a tag: `git tag v0.2.0 && git push origin v0.2.0`
3. `release.yml` triggers automatically:
   - Checks out code
   - Injects `TAURI_SIGNING_PRIVATE_KEY`
   - Builds for macOS + Windows (`tauri-action` matrix)
   - `tauri-action` generates `latest.json`, signs bundles, creates the GitHub Release, uploads all artifacts
4. App users see the banner on next launch

The existing `desktop-build.yml` (PR validation) remains unchanged.

---

## Rollback Strategy

Tauri's updater is atomic: it only replaces the running binary after the downloaded update passes signature verification and the installer runs successfully. If any step fails, the current version continues running.

- **Failed download:** banner shows "Download failed — try again" with retry button
- **Signature mismatch:** update is rejected, banner shows "Update signature invalid — download aborted"
- **Installer failure:** current version remains running; banner shows error + link to GitHub releases for manual install
- **No network on startup:** silent — app starts normally, no banner

Manual rollback: any prior release installer is permanently available on GitHub Releases.

---

## UI Specification

### `UpdateBanner` component

**Location:** Top of `<main className="app">`, above `<header>`, when update is available.

**Idle state (update found):**
```
┌─────────────────────────────────────────────────────────────────┐
│  Pacekeeper v0.2.0 is available  ▾ What's new  [Install & Restart]  ✕  │
└─────────────────────────────────────────────────────────────────┘
```
- Background: `--amber-soft`
- Border-left: 3px `--amber`
- Text: `--ink`
- Button: `--accent` (primary action style)
- "▾ What's new": expands inline release notes

**Downloading state:**
- Button replaced with: `⟳ Downloading… (42%)` (spinner + percentage)
- Dismiss `✕` hidden during active download

**Error state:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Update failed: [error message]  [Retry]  [Download manually ↗]  ✕ │
└─────────────────────────────────────────────────────────────────┘
```
- Background: `--crimson-soft`
- Border-left: 3px `--crimson`

### Version footer

Added to the existing `<footer className="status">` in `App.tsx`:
- Right-aligned: `v0.1.0`
- Font: `--mono`, color: `--ink-4`

---

## Files Changed

| File | Change |
|---|---|
| `desktop-app/src-tauri/Cargo.toml` | Add `tauri-plugin-updater` dependency |
| `desktop-app/src-tauri/tauri.conf.json` | Add `plugins.updater` block (endpoint + pubkey) |
| `desktop-app/src-tauri/src/main.rs` | Register updater plugin, add `install_update` command, emit `update-available` event |
| `desktop-app/package.json` | Add `@tauri-apps/plugin-updater` |
| `desktop-app/src/components/UpdateBanner.tsx` | New component |
| `desktop-app/src/App.tsx` | Mount `UpdateBanner`, add version to footer |
| `.github/workflows/release.yml` | New release workflow |

---

## Testing

### Unit tests
- `UpdateBanner.tsx`: renders with update info, "Install & Restart" triggers install command, dismiss hides banner, error state renders with retry + manual link

### Manual integration checklist
- [ ] Generate keypair with `pnpm tauri signer generate`
- [ ] Build a local release with a bumped version and the private key env var set
- [ ] Serve `latest.json` locally (or via a test GitHub release on a fork)
- [ ] Launch the older version, verify banner appears with correct version + notes
- [ ] Click "Install & Restart", verify new version launches
- [ ] Test with no network: verify app starts silently with no banner
- [ ] Test with a tampered bundle: verify signature rejection message appears

### E2E
Full update-install E2E (requires a live update server) is out of scope for v1 CI. Manual checklist above covers the acceptance criteria.

---

## Acceptance Criteria Mapping

| Criterion | How it's met |
|---|---|
| Update installable in < 2 clicks | Banner → "Install & Restart" = 1 click |
| App shows current version | Version displayed in footer via `getVersion()` |
| App shows release notes | Expandable "What's new" in the banner (from GitHub release body) |
| Failed update auto-recovers | Tauri updater atomic install; current version keeps running on failure |
| Signed update packages | Minisign keypair; public key baked into app; CI signs all bundles |
