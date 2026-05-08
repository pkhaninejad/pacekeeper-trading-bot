# Desktop Productization v1 — Design Spec

**Issue:** [#80](https://github.com/pkhaninejad/Claude-trade-bot/issues/80)  
**Date:** 2026-05-08  
**Status:** Approved for implementation

## Problem

Current setup requires Python, virtualenv, and terminal usage. This blocks non-technical buyers and makes distribution hard.

## Goal

Ship a one-click desktop binary that starts both bot dashboards and basic bot controls without command line usage.

## Scope (v1)

- Add a desktop launcher app (`desktop/launcher.py`) with:
  - Start/stop stock bot
  - Start/stop prediction bot
  - Open each dashboard in browser
  - Start/stop all
  - Live process status (running/stopped)
- Add local build scripts:
  - `scripts/build_desktop_macos.sh`
  - `scripts/build_desktop_windows.ps1`
- Add CI build workflow for macOS + Windows artifacts:
  - `.github/workflows/desktop-build.yml`
- Document productization approach and run/build flow

## Out of Scope (future issues)

- Native embedded webview tabs (this v1 opens system browser)
- Auto-updater
- License activation
- Code signing and notarization
- Installer branding and onboarding wizard

## Architecture

- Launcher is a Tkinter GUI (stdlib, no extra heavy UI runtime)
- Launcher starts backend processes via subprocess:
  - Stock bot: `python stock_bot.py` on port `4000`
  - Prediction bot: `python -m prediction_bot.main` on port `4001`
- Launcher monitors process state and provides one-click controls
- Process logs are suppressed in launcher mode to keep UX clean

## Acceptance Criteria

- User can launch a single desktop app and start either bot with one click
- User can open both dashboards without terminal commands
- Build artifacts can be generated for macOS and Windows via CI
- Build scripts run locally for developer packaging

## Risks and Mitigations

- Risk: `prediction_bot` module import path issues
  - Mitigation: run as module (`python -m prediction_bot.main`)
- Risk: large binary size with bundled Python
  - Mitigation: keep first release focused on reliability; optimize later
- Risk: antivirus/OS trust warnings
  - Mitigation: handled in separate signing/notarization issue

## Validation Plan

- Manual:
  - Launch desktop app
  - Start stock bot -> open dashboard
  - Start prediction bot -> open dashboard
  - Stop both cleanly
- CI:
  - GitHub Actions produces `dist/` artifacts on macOS and Windows

## Future Extensions

- Replace browser-open flow with embedded native tabs
- Add onboarding wizard and settings management
- Add update/rollback framework
- Add licensing and activation
