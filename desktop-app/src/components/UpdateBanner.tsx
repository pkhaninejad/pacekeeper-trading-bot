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
