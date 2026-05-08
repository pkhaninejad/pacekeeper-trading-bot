"""Simple desktop launcher for Claude Trade Bot.

This app provides a non-technical control surface to start/stop both local bot servers
and open their dashboards, without requiring users to run terminal commands.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
STOCK_PORT = 4000
PREDICTION_PORT = 4001


class BotProcess:
    def __init__(self, name: str, command: list[str], cwd: Path, url: str):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.url = url
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        if self.is_running:
            return
        self.process = subprocess.Popen(
            self.command,
            cwd=str(self.cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=False,
        )

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class LauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Claude Trade Bot Launcher")
        self.root.geometry("620x420")
        self.root.configure(bg="#0f141a")

        python = sys.executable
        self.stock_bot = BotProcess(
            name="Stock Bot",
            command=[python, "stock_bot.py"],
            cwd=ROOT,
            url=f"http://localhost:{STOCK_PORT}",
        )
        self.prediction_bot = BotProcess(
            name="Prediction Bot",
            command=[python, "-m", "prediction_bot.main"],
            cwd=ROOT,
            url=f"http://localhost:{PREDICTION_PORT}",
        )

        self.status_var = tk.StringVar(value="Ready. Start a bot to continue.")
        self.stock_state = tk.StringVar(value="Stopped")
        self.pred_state = tk.StringVar(value="Stopped")

        self._build_ui()
        self._start_poller()

    def _build_ui(self) -> None:
        title = tk.Label(
            self.root,
            text="Claude Trade Bot",
            font=("Helvetica", 20, "bold"),
            fg="#dce8f2",
            bg="#0f141a",
        )
        title.pack(pady=(18, 4))

        subtitle = tk.Label(
            self.root,
            text="One-click launcher for stock and prediction dashboards",
            font=("Helvetica", 11),
            fg="#9fb3c8",
            bg="#0f141a",
        )
        subtitle.pack(pady=(0, 18))

        panel = tk.Frame(self.root, bg="#1a232d", padx=14, pady=14)
        panel.pack(fill="x", padx=18, pady=10)

        self._build_bot_row(panel, self.stock_bot, self.stock_state, 0)
        self._build_bot_row(panel, self.prediction_bot, self.pred_state, 1)

        controls = tk.Frame(self.root, bg="#0f141a")
        controls.pack(fill="x", padx=18, pady=12)

        tk.Button(
            controls,
            text="Start All",
            command=self.start_all,
            bg="#2f7d32",
            fg="white",
            relief="flat",
            padx=18,
            pady=8,
        ).pack(side="left")

        tk.Button(
            controls,
            text="Stop All",
            command=self.stop_all,
            bg="#9e2d2d",
            fg="white",
            relief="flat",
            padx=18,
            pady=8,
        ).pack(side="left", padx=10)

        tk.Button(
            controls,
            text="Open Both Dashboards",
            command=self.open_all,
            bg="#245b8f",
            fg="white",
            relief="flat",
            padx=18,
            pady=8,
        ).pack(side="left")

        status = tk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=580,
            font=("Helvetica", 10),
            fg="#c4d7ea",
            bg="#0f141a",
        )
        status.pack(fill="x", padx=18, pady=(8, 12))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_bot_row(self, parent: tk.Frame, bot: BotProcess, state_var: tk.StringVar, row: int) -> None:
        frame = tk.Frame(parent, bg="#1a232d")
        frame.grid(row=row, column=0, sticky="ew", pady=8)
        parent.grid_columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text=bot.name,
            font=("Helvetica", 12, "bold"),
            fg="#f2f7fc",
            bg="#1a232d",
            width=16,
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 8))

        tk.Label(
            frame,
            textvariable=state_var,
            font=("Helvetica", 10),
            fg="#8fd3a4",
            bg="#1a232d",
            width=10,
            anchor="w",
        ).grid(row=0, column=1, padx=(0, 8))

        tk.Button(
            frame,
            text="Start",
            command=lambda b=bot: self.start_bot(b),
            bg="#2f7d32",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
        ).grid(row=0, column=2, padx=4)

        tk.Button(
            frame,
            text="Stop",
            command=lambda b=bot: self.stop_bot(b),
            bg="#9e2d2d",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
        ).grid(row=0, column=3, padx=4)

        tk.Button(
            frame,
            text="Open Dashboard",
            command=lambda b=bot: self.open_dashboard(b),
            bg="#245b8f",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
        ).grid(row=0, column=4, padx=4)

    def start_bot(self, bot: BotProcess) -> None:
        try:
            bot.start()
            self.status_var.set(f"Started {bot.name}. Opening dashboard in your browser...")
            # Give uvicorn a moment to bind port before opening.
            self.root.after(1200, lambda: webbrowser.open(bot.url))
        except Exception as exc:  # pragma: no cover - UI path
            messagebox.showerror("Start failed", f"Could not start {bot.name}: {exc}")

    def stop_bot(self, bot: BotProcess) -> None:
        bot.stop()
        self.status_var.set(f"Stopped {bot.name}.")

    def open_dashboard(self, bot: BotProcess) -> None:
        webbrowser.open(bot.url)
        self.status_var.set(f"Opened {bot.name} dashboard.")

    def start_all(self) -> None:
        self.start_bot(self.stock_bot)
        self.start_bot(self.prediction_bot)

    def stop_all(self) -> None:
        self.stop_bot(self.stock_bot)
        self.stop_bot(self.prediction_bot)

    def open_all(self) -> None:
        self.open_dashboard(self.stock_bot)
        self.open_dashboard(self.prediction_bot)

    def _refresh_state(self) -> None:
        self.stock_state.set("Running" if self.stock_bot.is_running else "Stopped")
        self.pred_state.set("Running" if self.prediction_bot.is_running else "Stopped")

    def _start_poller(self) -> None:
        def poll() -> None:
            while True:
                time.sleep(1.0)
                self.root.after(0, self._refresh_state)

        thread = threading.Thread(target=poll, daemon=True)
        thread.start()

    def _on_close(self) -> None:
        self.stop_all()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    LauncherUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
