# Auto-Update Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seamless one-click auto-update to the Pacekeeper Tauri desktop app, served via GitHub Releases with Minisign signature verification.

**Architecture:** `tauri-plugin-updater` checks a GitHub Releases `latest.json` endpoint on app startup. When an update is found, a top-of-page amber banner appears with version info and an "Install & Restart" button. The release workflow (`release.yml`) builds signed macOS + Windows bundles on `v*.*.*` tags and publishes the GitHub Release.

**Tech Stack:** Tauri 2.0, `tauri-plugin-updater 2`, `tauri-plugin-process 2`, `@tauri-apps/plugin-updater`, `@tauri-apps/plugin-process`, React 18, Vitest, `tauri-apps/tauri-action` GitHub Action.

**Spec:** `docs/superpowers/specs/2026-05-09-auto-update-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `desktop-app/src-tauri/Cargo.toml` | Modify | Add Rust plugin deps |
| `desktop-app/src-tauri/src/main.rs` | Modify | Register updater + process plugins |
| `desktop-app/src-tauri/tauri.conf.json` | Modify | Updater endpoint + pubkey |
| `desktop-app/src-tauri/capabilities/updater.json` | Create | Grant updater + process permissions to frontend |
| `desktop-app/package.json` | Modify | Add JS plugin packages |
| `desktop-app/src/components/UpdateBanner.tsx` | Create | Update notification banner |
| `desktop-app/src/__tests__/UpdateBanner.test.tsx` | Create | Unit tests for the banner |
| `desktop-app/src/App.tsx` | Modify | Mount banner, add version footer |
| `.github/workflows/release.yml` | Create | Tag-triggered signed release CI |

---

## Task 1: Create the feature branch

**Files:** none

- [ ] **Step 1: Create and switch to the feature branch**

```bash
git checkout -b feat/auto-update-issue-82
```

Expected: `Switched to a new branch 'feat/auto-update-issue-82'`

---

## Task 2: Generate the Minisign keypair

> This is a one-time step. The public key goes into `tauri.conf.json` (committed to the repo). The private key goes into a GitHub Actions secret — never commit it.

**Files:** `desktop-app/src-tauri/tauri.conf.json` (will be edited in Task 4)

- [ ] **Step 1: Generate the keypair**

```bash
cd desktop-app && pnpm tauri signer generate -w ~/.tauri/pacekeeper.key
```

Expected output (example — your values will differ):
```
Please enter a password to protect the secret key (optional):
Password:
Deriving a key from the password and generating keypair... done

Your keypair was generated successfully
Private: /Users/you/.tauri/pacekeeper.key (keep this secret!)
Public key: dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXkgNEE2NTc3RTdGRjU5MEI4MgpSWVNEQUFBQUJBQUFBQWJa...
```

- [ ] **Step 2: Copy the public key**

Copy the entire line that starts with `dW50` (the base64-encoded Minisign public key). You will paste this into `tauri.conf.json` in Task 4.

- [ ] **Step 3: Save the private key for CI**

Read the private key file content:
```bash
cat ~/.tauri/pacekeeper.key
```

Copy the entire output. In your GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
- Name: `TAURI_SIGNING_PRIVATE_KEY`
- Value: paste the private key file content

If you set a password in Step 1, also create:
- Name: `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
- Value: the password you chose (leave blank if you skipped the password)

---

## Task 3: Add Rust dependencies

**Files:**
- Modify: `desktop-app/src-tauri/Cargo.toml`

- [ ] **Step 1: Add plugin crates to `[dependencies]`**

Open `desktop-app/src-tauri/Cargo.toml`. In the `[dependencies]` section, after `serde_json = "1"`, add:

```toml
tauri-plugin-updater = "2"
tauri-plugin-process = "2"
```

The `[dependencies]` block should now look like:

```toml
[dependencies]
tauri = { version = "2.0", features = [] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tauri-plugin-updater = "2"
tauri-plugin-process = "2"
reqwest = { version = "0.12", features = ["json"] }
url = "2"
```

- [ ] **Step 2: Verify the crates resolve**

```bash
cd desktop-app && cargo fetch
```

Expected: downloads complete with no errors.

---

## Task 4: Register plugins in main.rs

**Files:**
- Modify: `desktop-app/src-tauri/src/main.rs` lines 209–216

- [ ] **Step 1: Add plugin registration before `.manage()`**

In `main()`, change:

```rust
    let app = tauri::Builder::default()
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
```

to:

```rust
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
```

- [ ] **Step 2: Verify compilation**

```bash
cd desktop-app && cargo check
```

Expected: `Finished` with no errors.

---

## Task 5: Configure tauri.conf.json

**Files:**
- Modify: `desktop-app/src-tauri/tauri.conf.json`
- Create: `desktop-app/src-tauri/capabilities/updater.json`

- [ ] **Step 1: Add the updater plugin block to `tauri.conf.json`**

Open `desktop-app/src-tauri/tauri.conf.json`. Add a top-level `"plugins"` key (after `"bundle"`):

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "Pacekeeper",
  "version": "0.1.0",
  "identifier": "de.wallstrdev.pacekeeper",
  "build": {
    "beforeDevCommand": "pnpm dev",
    "devUrl": "http://localhost:1420",
    "beforeBuildCommand": "pnpm build",
    "frontendDist": "../dist"
  },
  "app": {
    "windows": [
      {
        "title": "Pacekeeper",
        "width": 980,
        "height": 760,
        "minWidth": 820,
        "minHeight": 620,
        "resizable": true
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["app", "dmg", "msi"],
    "icon": []
  },
  "plugins": {
    "updater": {
      "pubkey": "PASTE_YOUR_PUBLIC_KEY_HERE",
      "endpoints": [
        "https://github.com/pkhaninejad/Claude-trade-bot/releases/latest/download/latest.json"
      ]
    }
  }
}
```

Replace `PASTE_YOUR_PUBLIC_KEY_HERE` with the public key you copied in Task 2, Step 2.

- [ ] **Step 2: Create the capabilities directory and grant permissions**

```bash
mkdir -p desktop-app/src-tauri/capabilities
```

Create `desktop-app/src-tauri/capabilities/updater.json`:

```json
{
  "$schema": "https://schema.tauri.app/config/2/capability.json",
  "identifier": "updater",
  "description": "Allow main window to check for and install updates",
  "windows": ["main"],
  "permissions": [
    "updater:default",
    "process:default"
  ]
}
```

- [ ] **Step 3: Verify the config is valid JSON**

```bash
node -e "JSON.parse(require('fs').readFileSync('desktop-app/src-tauri/tauri.conf.json', 'utf8')); console.log('valid')"
```

Expected: `valid`

---

## Task 6: Add frontend plugin packages

**Files:**
- Modify: `desktop-app/package.json`

- [ ] **Step 1: Add the JS plugin packages**

```bash
cd desktop-app && pnpm add @tauri-apps/plugin-updater @tauri-apps/plugin-process
```

Expected: both packages added to `dependencies` in `package.json`.

- [ ] **Step 2: Verify lockfile updates cleanly**

```bash
cd desktop-app && pnpm install --frozen-lockfile || pnpm install
```

Expected: no errors.

---

## Task 7: Write failing tests for UpdateBanner

**Files:**
- Create: `desktop-app/src/__tests__/UpdateBanner.test.tsx`

- [ ] **Step 1: Create the test file**

Create `desktop-app/src/__tests__/UpdateBanner.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: vi.fn(),
}));

import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import UpdateBanner from "../components/UpdateBanner";

const mockCheck = vi.mocked(check);
const mockRelaunch = vi.mocked(relaunch);

function makeUpdate(overrides: Record<string, unknown> = {}) {
  return {
    version: "0.2.0",
    body: "Bug fixes and improvements",
    downloadAndInstall: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockRelaunch.mockResolvedValue(undefined);
});

test("renders nothing when no update is available", async () => {
  mockCheck.mockResolvedValue(null);
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(mockCheck).toHaveBeenCalled());
  expect(container.firstChild).toBeNull();
});

test("renders nothing when check throws (network error)", async () => {
  mockCheck.mockRejectedValue(new Error("network error"));
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(mockCheck).toHaveBeenCalled());
  expect(container.firstChild).toBeNull();
});

test("renders banner when an update is available", async () => {
  mockCheck.mockResolvedValue(makeUpdate());
  render(<UpdateBanner />);
  await waitFor(() =>
    expect(screen.getByText(/Pacekeeper 0\.2\.0 is available/)).toBeInTheDocument()
  );
  expect(screen.getByText("Install & Restart")).toBeInTheDocument();
});

test("shows What's new toggle when update has body", async () => {
  mockCheck.mockResolvedValue(makeUpdate({ body: "New trading dashboard" }));
  render(<UpdateBanner />);
  await waitFor(() => expect(screen.getByText(/What's new/)).toBeInTheDocument());
});

test("clicking What's new expands release notes", async () => {
  mockCheck.mockResolvedValue(makeUpdate({ body: "New trading dashboard" }));
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText(/What's new/));
  fireEvent.click(screen.getByText(/What's new/));
  expect(screen.getByText("New trading dashboard")).toBeInTheDocument();
});

test("clicking Install & Restart calls downloadAndInstall then relaunch", async () => {
  const mockUpdate = makeUpdate();
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(mockUpdate.downloadAndInstall).toHaveBeenCalled());
  await waitFor(() => expect(mockRelaunch).toHaveBeenCalled());
});

test("clicking dismiss hides the banner", async () => {
  mockCheck.mockResolvedValue(makeUpdate());
  render(<UpdateBanner />);
  await waitFor(() => screen.getByLabelText("Dismiss"));
  fireEvent.click(screen.getByLabelText("Dismiss"));
  expect(screen.queryByText(/Pacekeeper 0\.2\.0 is available/)).not.toBeInTheDocument();
});

test("shows error state when install fails", async () => {
  const mockUpdate = makeUpdate({
    downloadAndInstall: vi.fn().mockRejectedValue(new Error("disk full")),
  });
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(screen.getByText(/Update failed/)).toBeInTheDocument());
  expect(screen.getByText("Retry")).toBeInTheDocument();
  expect(screen.getByText("Download manually ↗")).toBeInTheDocument();
});

test("dismiss is hidden while downloading", async () => {
  let resolveInstall!: () => void;
  const installPromise = new Promise<void>((resolve) => { resolveInstall = resolve; });
  const mockUpdate = makeUpdate({ downloadAndInstall: vi.fn().mockReturnValue(installPromise) });
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(screen.getByText(/Downloading/)).toBeInTheDocument());
  expect(screen.queryByLabelText("Dismiss")).not.toBeInTheDocument();
  resolveInstall();
});
```

- [ ] **Step 2: Run the tests — they must fail (component does not exist yet)**

```bash
cd desktop-app && pnpm vitest run src/__tests__/UpdateBanner.test.tsx
```

Expected: tests fail with `Cannot find module '../components/UpdateBanner'`

---

## Task 8: Implement UpdateBanner.tsx

**Files:**
- Create: `desktop-app/src/components/UpdateBanner.tsx`

- [ ] **Step 1: Create the component**

Create `desktop-app/src/components/UpdateBanner.tsx`:

```tsx
import { useState, useEffect, useRef } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

type BannerState = "idle" | "downloading" | "error";

export default function UpdateBanner() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [state, setState] = useState<BannerState>("idle");
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const totalRef = useRef(0);
  const downloadedRef = useRef(0);

  useEffect(() => {
    check()
      .then((u) => setUpdate(u))
      .catch(() => {});
  }, []);

  if (!update || dismissed) return null;

  async function handleInstall() {
    if (!update) return;
    setState("downloading");
    setProgress(0);
    totalRef.current = 0;
    downloadedRef.current = 0;
    try {
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") {
          totalRef.current = event.data.contentLength ?? 0;
        } else if (event.event === "Progress") {
          downloadedRef.current += event.data.chunkLength;
          if (totalRef.current > 0) {
            setProgress(Math.round((downloadedRef.current / totalRef.current) * 100));
          }
        }
      });
      await relaunch();
    } catch (err) {
      setState("error");
      setErrorMsg(String(err));
    }
  }

  const isError = state === "error";
  const isDownloading = state === "downloading";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--s-3)",
        padding: "var(--s-2) var(--s-4)",
        background: isError ? "var(--crimson-soft)" : "var(--amber-soft)",
        borderLeft: `3px solid ${isError ? "var(--crimson)" : "var(--amber)"}`,
        color: "var(--ink)",
        fontSize: "0.875rem",
        flexWrap: "wrap",
      }}
    >
      {isError ? (
        <>
          <span>Update failed: {errorMsg}</span>
          <button onClick={handleInstall}>Retry</button>
          <a
            href="https://github.com/pkhaninejad/Claude-trade-bot/releases"
            target="_blank"
            rel="noreferrer"
          >
            Download manually ↗
          </a>
          <button
            style={{ marginLeft: "auto" }}
            aria-label="Dismiss"
            onClick={() => setDismissed(true)}
          >
            ✕
          </button>
        </>
      ) : (
        <>
          <span>Pacekeeper {update.version} is available</span>
          {update.body && (
            <button
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink-2)" }}
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? "▴" : "▾"} What's new
            </button>
          )}
          {isDownloading ? (
            <span style={{ fontFamily: "var(--mono)" }}>
              ⟳ Downloading…{progress > 0 ? ` (${progress}%)` : ""}
            </span>
          ) : (
            <button onClick={handleInstall}>Install &amp; Restart</button>
          )}
          {!isDownloading && (
            <button
              style={{ marginLeft: "auto" }}
              aria-label="Dismiss"
              onClick={() => setDismissed(true)}
            >
              ✕
            </button>
          )}
        </>
      )}
      {expanded && update.body && (
        <div style={{ width: "100%", paddingTop: "var(--s-2)", whiteSpace: "pre-wrap" }}>
          {update.body}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Run the tests — all must pass**

```bash
cd desktop-app && pnpm vitest run src/__tests__/UpdateBanner.test.tsx
```

Expected: all 9 tests pass.

- [ ] **Step 3: Commit**

```bash
git add \
  desktop-app/src-tauri/Cargo.toml \
  desktop-app/src-tauri/src/main.rs \
  desktop-app/src-tauri/tauri.conf.json \
  desktop-app/src-tauri/capabilities/updater.json \
  desktop-app/package.json \
  desktop-app/pnpm-lock.yaml \
  desktop-app/src/components/UpdateBanner.tsx \
  desktop-app/src/__tests__/UpdateBanner.test.tsx
git commit -m "feat: add auto-update via tauri-plugin-updater and UpdateBanner component"
```

---

## Task 9: Integrate UpdateBanner and version footer into App.tsx

**Files:**
- Modify: `desktop-app/src/App.tsx`

- [ ] **Step 1: Add the import for UpdateBanner and getVersion**

At the top of `desktop-app/src/App.tsx`, after the existing imports, add:

```tsx
import { getVersion } from "@tauri-apps/api/app";
import UpdateBanner from "./components/UpdateBanner";
```

- [ ] **Step 2: Add version state**

Inside the `App` component function, after the existing `useState` declarations, add:

```tsx
const [appVersion, setAppVersion] = useState<string | null>(null);
```

- [ ] **Step 3: Load version on mount**

Add a new `useEffect` after the existing effects:

```tsx
useEffect(() => {
  if (tauriMode) {
    getVersion().then(setAppVersion).catch(() => {});
  }
}, [tauriMode]);
```

- [ ] **Step 4: Mount UpdateBanner and update the footer**

In the launcher return (the `return (<main className="app">...)` block), make two changes:

**Before the `<header>` tag**, add:
```tsx
<UpdateBanner />
```

**Replace** the footer line:
```tsx
<footer className="status">{message}</footer>
```
**With:**
```tsx
<footer className="status" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
  <span>{message}</span>
  {appVersion && (
    <span style={{ fontFamily: "var(--mono)", color: "var(--ink-4)", fontSize: "0.8rem" }}>
      v{appVersion}
    </span>
  )}
</footer>
```

- [ ] **Step 5: Run the full test suite**

```bash
cd desktop-app && pnpm vitest run
```

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add desktop-app/src/App.tsx
git commit -m "feat: mount UpdateBanner and show app version in launcher footer"
```

---

## Task 10: Create the release CI workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  release:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
          cache-dependency-path: desktop-app/pnpm-lock.yaml

      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 10

      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Install frontend deps
        working-directory: desktop-app
        run: pnpm install --frozen-lockfile

      - name: Publish release
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'Pacekeeper ${{ github.ref_name }}'
          releaseBody: 'See the [release notes](https://github.com/pkhaninejad/Claude-trade-bot/releases/tag/${{ github.ref_name }}) for details.'
          releaseDraft: false
          prerelease: false
          projectPath: desktop-app
          tauriScript: pnpm tauri
          updaterJsonKeepUniversal: true
```

- [ ] **Step 2: Commit the workflow**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add release workflow for signed Tauri auto-update bundles"
```

---

## Task 11: Post spec comment to GitHub issue and open the PR

**Files:** none

- [ ] **Step 1: Post the spec to GitHub issue #82**

```bash
gh issue comment 82 \
  --repo pkhaninejad/Claude-trade-bot \
  --body "$(cat <<'EOF'
## Implementation Plan

Spec: [`docs/superpowers/specs/2026-05-09-auto-update-design.md`](../blob/main/docs/superpowers/specs/2026-05-09-auto-update-design.md)

### Summary

- **Update server:** GitHub Releases — `tauri-action` publishes signed bundles + `latest.json` on `v*.*.*` tags
- **Signing:** Tauri Minisign keypair — private key in CI secrets, public key baked into `tauri.conf.json`
- **UX:** Amber banner on startup when update is available → "Install & Restart" (1 click) → download + verify + install + relaunch
- **Rollback:** Tauri updater is atomic — current version keeps running if download or signature verification fails

### Stack added
- Rust: `tauri-plugin-updater 2`, `tauri-plugin-process 2`
- JS: `@tauri-apps/plugin-updater`, `@tauri-apps/plugin-process`
- CI: `.github/workflows/release.yml` triggered by `v*.*.*` tags via `tauri-apps/tauri-action`

### Acceptance criteria
| Criterion | Implementation |
|---|---|
| < 2 clicks to install | Banner → "Install & Restart" = 1 click |
| Shows current version | `getVersion()` displayed in launcher footer |
| Shows release notes | Expandable "What's new" toggle in banner |
| Failed update auto-recovers | Atomic install; app keeps running on failure; error shown with retry |
| Signed packages | Minisign signature verified before install |

### Pre-flight for releasing
1. Generate keypair: `cd desktop-app && pnpm tauri signer generate -w ~/.tauri/pacekeeper.key`
2. Add `TAURI_SIGNING_PRIVATE_KEY` (+ optional `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) to GitHub Actions secrets
3. Bump `version` in `tauri.conf.json` + `package.json`, commit, push tag: `git tag v0.2.0 && git push origin v0.2.0`
EOF
)"
```

Expected: `Created comment on issue #82`

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/auto-update-issue-82
```

- [ ] **Step 3: Open the pull request**

```bash
gh pr create \
  --repo pkhaninejad/Claude-trade-bot \
  --title "feat: in-app auto-update via tauri-plugin-updater (issue #82)" \
  --body "$(cat <<'EOF'
## Summary

- Adds `tauri-plugin-updater` + `tauri-plugin-process` to the Tauri Rust backend
- Adds `@tauri-apps/plugin-updater` + `@tauri-apps/plugin-process` to the frontend
- Creates `UpdateBanner.tsx` — amber notification bar that appears on startup when a newer version is available on GitHub Releases
- Adds version display to the launcher footer via `getVersion()`
- Creates `.github/workflows/release.yml` — builds signed macOS + Windows bundles and publishes a GitHub Release on `v*.*.*` tags

## Closes

Closes #82

## Pre-flight (before merging)

- [ ] Generate Minisign keypair: `cd desktop-app && pnpm tauri signer generate -w ~/.tauri/pacekeeper.key`
- [ ] Add `TAURI_SIGNING_PRIVATE_KEY` to GitHub Actions secrets
- [ ] Replace `PASTE_YOUR_PUBLIC_KEY_HERE` in `tauri.conf.json` with the generated public key
- [ ] Optionally add `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` if you set a password

## Test plan

- [ ] `pnpm vitest run` — all tests pass (9 new UpdateBanner tests)
- [ ] `pnpm tauri build` — builds cleanly with the real pubkey set
- [ ] Manual: mock a `latest.json` pointing at a test version; verify banner appears and dismiss works
- [ ] Manual: push a `v*.*.*` tag; verify `release.yml` runs and artifacts + `latest.json` appear on the GitHub Release

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed — share it with the team.

---

## Release runbook (post-merge, for every future release)

1. Bump `version` in `desktop-app/src-tauri/tauri.conf.json` and `desktop-app/package.json`
2. Commit: `git commit -am "chore: bump version to v0.2.0"`
3. Tag and push: `git tag v0.2.0 && git push origin main --tags`
4. GitHub Actions `release.yml` runs automatically and publishes the signed release
5. Existing app users see the banner on next launch
