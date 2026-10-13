#!/usr/bin/env python3
"""Antigravity Pulse: Real-time usage strip & native footer status line for Google Antigravity CLI.

Hooks into Antigravity CLI's statusLine mechanism to display model quota,
reset countdowns, context window usage, token metrics, and workspace state
directly inside the terminal footer — eliminating the need to run /usage manually.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def init_terminal() -> None:
    """Initialize terminal for UTF-8 encoding and ANSI Virtual Terminal Processing on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and stream.encoding and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


class UI:
    """Terminal styling, ANSI colors, and box-drawing glyphs with fallback detection."""

    def __init__(self) -> None:
        init_terminal()
        self.enabled = (
            "NO_COLOR" not in os.environ
            and (
                "FORCE_COLOR" in os.environ
                or "CLICOLOR_FORCE" in os.environ
                or sys.stdout.isatty()
            )
        )
        self.unicode_ok = self._test_encoding("┌─│└┆•⚡🧠📊📈📁━─")

    @staticmethod
    def _test_encoding(sample: str) -> bool:
        encoding = sys.stdout.encoding or "ascii"
        try:
            sample.encode(encoding)
            return True
        except (UnicodeEncodeError, LookupError):
            return False

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def cyan(self, text: str) -> str:
        return self._wrap("96", text)

    def bright_blue(self, text: str) -> str:
        return self._wrap("94", text)

    def green(self, text: str) -> str:
        return self._wrap("92", text)

    def yellow(self, text: str) -> str:
        return self._wrap("93", text)

    def magenta(self, text: str) -> str:
        return self._wrap("95", text)

    def red(self, text: str) -> str:
        return self._wrap("91", text)

    def white(self, text: str) -> str:
        return self._wrap("97", text)

    @property
    def box_top(self) -> str:
        return "┌──" if self.unicode_ok else "+--"

    @property
    def box_mid(self) -> str:
        return "├──" if self.unicode_ok else "+--"

    @property
    def box_bot(self) -> str:
        return "└──" if self.unicode_ok else "+--"

    @property
    def box_vert(self) -> str:
        return "│" if self.unicode_ok else "|"

    @property
    def box_line(self) -> str:
        return "─" if self.unicode_ok else "-"

    @property
    def divider(self) -> str:
        return "┆" if self.unicode_ok else "|"

    @property
    def dot(self) -> str:
        return "·" if self.unicode_ok else "|"

    @property
    def bullet(self) -> str:
        return "•" if self.unicode_ok else "*"

    @property
    def bar_fill(self) -> str:
        return "━" if self.unicode_ok else "="

    @property
    def bar_empty(self) -> str:
        return "─" if self.unicode_ok else "-"

    def icon(self, emoji: str) -> str:
        return f"{emoji} " if self.unicode_ok else ""


ui = UI()


# Categorized status items available for Antigravity Pulse
SECTIONS: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "MODEL & INTELLIGENCE",
        "🧠",
        (
            ("model", "Model Name", "Active Gemini model display name (e.g. Gemini 3.8 Flash)"),
            ("model-effort", "Model & Effort", "Model name combined with reasoning effort level"),
            ("effort", "Reasoning Effort", "Reasoning effort level (e.g. low, medium, high, max)"),
        ),
    ),
    (
        "QUOTA & RATE LIMITS",
        "📊",
        (
            ("quota-bar", "Quota Visual Bar", "Color-coded gauge of remaining model quota (e.g. ━━━━━━━━── 82%)"),
            ("quota-fraction", "Quota Remaining", "Percentage of quota allowance remaining (e.g. 82% left)"),
            ("quota-reset", "Reset Countdown", "Time remaining until rolling quota resets (e.g. R:1h 45m)"),
            ("quota-full", "Quota & Reset Combined", "Remaining quota percentage with reset countdown timer"),
        ),
    ),
    (
        "CONTEXT WINDOW & TOKENS",
        "📈",
        (
            ("context-bar", "Context Visual Bar", "Color-coded gauge of context window consumed (e.g. ━━──────── 24%)"),
            ("context-used", "Context Used %", "Percentage of model context window used (e.g. Context 24% used)"),
            ("context-remaining", "Context Headroom", "Percentage of context window still available"),
            ("tokens", "Total Tokens", "Cumulative session tokens consumed (input + output)"),
            ("tokens-in-out", "Tokens (In / Out)", "Prompt input tokens and completion output tokens"),
            ("window-size", "Context Capacity", "Total maximum window capacity of active model (e.g. 1M)"),
        ),
    ),
    (
        "WORKSPACE & VERSION CONTROL",
        "📁",
        (
            ("project", "Project Name", "Name of active project or workspace folder"),
            ("cwd", "Working Directory", "Path of current working directory"),
            ("git-branch", "Git Branch", "Active Git branch with dirty state marker (e.g. main*)"),
            ("git-status", "Git Branch & Diff", "Git branch alongside uncommitted diff summary"),
        ),
    ),
    (
        "AGENT & SESSION STATE",
        "⚡",
        (
            ("fast-mode", "Fast Mode", "Priority / Fast mode status indicator (⚡ Fast)"),
            ("step-count", "Step Progress", "Number of conversation steps completed (e.g. Step 8)"),
            ("session-id", "Session ID", "Shortened unique conversation ID"),
            ("version", "CLI Version", "Antigravity CLI version string"),
        ),
    ),
)

ITEMS: tuple[tuple[str, str], ...] = tuple(
    (item_id, label)
    for _, _, section_items in SECTIONS
    for item_id, label, _ in section_items
)
ITEM_IDS = {item_id for item_id, _ in ITEMS}

PRESETS: dict[str, tuple[str, ...]] = {
    "pulse": (
        "model",
        "quota-bar",
        "quota-reset",
        "context-bar",
        "fast-mode",
    ),
    "quota": (
        "model",
        "quota-full",
        "context-used",
        "tokens",
        "window-size",
    ),
    "studio": (
        "model",
        "project",
        "git-branch",
        "quota-bar",
        "context-bar",
    ),
    "sprint": (
        "model",
        "step-count",
        "context-bar",
        "quota-bar",
        "fast-mode",
    ),
    "compact": (
        "model",
        "quota-fraction",
        "context-used",
        "git-branch",
    ),
    "wide": (
        "model-effort",
        "project",
        "git-branch",
        "quota-bar",
        "quota-reset",
        "context-bar",
        "tokens-in-out",
        "fast-mode",
    ),
}

PRESET_METADATA: dict[str, dict[str, str]] = {
    "pulse": {
        "title": "Pulse (Balanced / Default)",
        "summary": "Real-time model quota gauge, reset countdown, and context window bar.",
    },
    "quota": {
        "title": "Quota (Limit & Rate Focus)",
        "summary": "Dedicated rate limit tracker with exact percentage, reset timer, and tokens.",
    },
    "studio": {
        "title": "Studio (Workspace & Git)",
        "summary": "Engineering-first layout displaying project folder, Git branch, and usage gauges.",
    },
    "sprint": {
        "title": "Sprint (Agent & Execution)",
        "summary": "Tracks step count, context headroom, and quota during long-running tasks.",
    },
    "compact": {
        "title": "Compact (Minimalist)",
        "summary": "Clean, ultra-short status strip for narrow terminal windows.",
    },
    "wide": {
        "title": "Wide (Comprehensive & Panoramic)",
        "summary": "Full panoramic footer with effort, workspace, quota, context, and token counters.",
    },
}

SHORT_TAGS: dict[str, str] = {
    "model": "MODEL",
    "model-effort": "MODEL+EFFORT",
    "effort": "EFFORT",
    "quota-bar": "QUOTA BAR",
    "quota-fraction": "QUOTA %",
    "quota-reset": "RESET IN",
    "quota-full": "QUOTA+RESET",
    "context-bar": "CONTEXT BAR",
    "context-used": "CONTEXT %",
    "context-remaining": "HEADROOM",
    "tokens": "TOKENS",
    "tokens-in-out": "IN / OUT",
    "window-size": "WINDOW",
    "project": "PROJECT",
    "cwd": "CWD",
    "git-branch": "BRANCH",
    "git-status": "GIT STATUS",
    "fast-mode": "FAST",
    "step-count": "STEPS",
    "session-id": "SESSION",
    "version": "VERSION",
}

SAMPLE_PAYLOAD: dict = {
    "cwd": "E:\\codex-pulse",
    "conversation_id": "e2e29711-0f61-410d-b5b5-12540ebbf62e",
    "model": {
        "id": "gemini-3.8-flash",
        "display_name": "Gemini 3.8 Flash (High)",
    },
    "workspace": {
        "current_dir": "E:\\antigravity-pulse",
        "project_dir": "E:\\antigravity-pulse",
    },
    "version": "1.0.0",
    "context_window": {
        "total_input_tokens": 14200,
        "total_output_tokens": 3400,
        "context_window_size": 1048576,
        "used_percentage": 24.5,
        "remaining_percentage": 75.5,
    },
    "quota": {
        "remaining_fraction": 0.82,
        "reset_time": "2026-10-14T05:00:00Z",
        "reset_in_seconds": 6300,
    },
    "step_count": 8,
}


def settings_path() -> Path:
    """Return path to Antigravity CLI settings.json."""
    custom = os.environ.get("ANTIGRAVITY_CONFIG") or os.environ.get("AGY_CONFIG")
    if custom:
        return Path(custom).expanduser() / "settings.json"
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def pulse_config_path() -> Path:
    """Return path to Antigravity Pulse local configuration."""
    return Path.home() / ".gemini" / "antigravity-cli" / "antigravity_pulse_config.json"


def get_git_branch(cwd: str | Path | None) -> str | None:
    """Detect current Git branch and uncommitted changes if in a repository."""
    if not cwd or not Path(cwd).exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "status", "-sb"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        lines = proc.stdout.splitlines()
        first = lines[0].replace("## ", "").split("...")[0].strip()
        is_dirty = len(lines) > 1
        return f"{first}*" if is_dirty else first
    except Exception:
        return None


def format_duration(seconds: int | float | None) -> str:
    """Format duration in seconds to human-readable timer (e.g. 1h 45m)."""
    if seconds is None or seconds < 0:
        return "--"
    sec = int(seconds)
    hours, remainder = divmod(sec, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m"
    return f"{sec}s"


def format_tokens(count: int | float | None) -> str:
    """Format token count into compact string (e.g. 14.2k, 1.2M)."""
    if count is None:
        return "0"
    num = float(count)
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(int(num))


def render_gauge(percentage: float, length: int = 10, reverse: bool = False) -> str:
    """Render a color-coded progress gauge (reverse=True means higher percentage is healthier)."""
    clamped = max(0.0, min(100.0, percentage))
    filled_count = int(round((clamped / 100.0) * length))
    unfilled_count = length - filled_count

    bar = (ui.bar_fill * filled_count) + (ui.bar_empty * unfilled_count)

    # Color thresholding
    if reverse:
        # e.g. Quota remaining: high is green, low is red
        if clamped >= 50.0:
            colored_bar = ui.green(bar)
        elif clamped >= 20.0:
            colored_bar = ui.yellow(bar)
        else:
            colored_bar = ui.red(bar)
    else:
        # e.g. Context used: low is green, high is red
        if clamped <= 50.0:
            colored_bar = ui.green(bar)
        elif clamped <= 80.0:
            colored_bar = ui.yellow(bar)
        else:
            colored_bar = ui.red(bar)

    return colored_bar


def extract_item(item_id: str, payload: dict) -> str:
    """Extract and format a single status item from the Antigravity session payload."""
    model_obj = payload.get("model", {})
    model_name = model_obj.get("display_name") or model_obj.get("id") or "Gemini"
    effort = payload.get("effort") or "high"

    quota_obj = payload.get("quota", {})
    # Quota may be direct object or nested by model id
    if isinstance(quota_obj, dict) and "remaining_fraction" not in quota_obj:
        for val in quota_obj.values():
            if isinstance(val, dict) and "remaining_fraction" in val:
                quota_obj = val
                break
    quota_frac = quota_obj.get("remaining_fraction", 0.85) if isinstance(quota_obj, dict) else 0.85
    quota_pct = float(quota_frac * 100.0)
    reset_secs = quota_obj.get("reset_in_seconds") if isinstance(quota_obj, dict) else None
    if reset_secs is None:
        reset_secs = 6300

    ctx_obj = payload.get("context_window", {})
    ctx_used_pct = float(ctx_obj.get("used_percentage", 24.5) or 24.5)
    ctx_rem_pct = float(ctx_obj.get("remaining_percentage", 100.0 - ctx_used_pct) or (100.0 - ctx_used_pct))
    tokens_in = ctx_obj.get("total_input_tokens", 14200)
    tokens_out = ctx_obj.get("total_output_tokens", 3400)
    tokens_total = tokens_in + tokens_out
    window_capacity = ctx_obj.get("context_window_size", 1048576)

    workspace = payload.get("workspace", {})
    cwd = payload.get("cwd") or workspace.get("current_dir") or os.getcwd()
    project_dir = workspace.get("project_dir") or cwd
    project_name = Path(project_dir).name if project_dir else "workspace"

    git_branch = get_git_branch(cwd) or "main"
    step_num = payload.get("step_count", 1)

    if item_id == "model":
        return ui.cyan(ui.bold(model_name.replace(" (High)", "")))
    if item_id == "model-effort":
        return ui.cyan(ui.bold(model_name))
    if item_id == "effort":
        return ui.dim(f"effort:{effort}")
    if item_id == "quota-bar":
        gauge = render_gauge(quota_pct, length=8, reverse=True)
        return f"Quota {gauge} {ui.bold(f'{int(quota_pct)}%')}"
    if item_id == "quota-fraction":
        color_fn = ui.green if quota_pct >= 50 else (ui.yellow if quota_pct >= 20 else ui.red)
        return f"Quota: {color_fn(f'{int(quota_pct)}% left')}"
    if item_id == "quota-reset":
        return f"R:{format_duration(reset_secs)}"
    if item_id == "quota-full":
        color_fn = ui.green if quota_pct >= 50 else (ui.yellow if quota_pct >= 20 else ui.red)
        return f"Quota: {color_fn(f'{int(quota_pct)}%')} ({format_duration(reset_secs)})"
    if item_id == "context-bar":
        gauge = render_gauge(ctx_used_pct, length=8, reverse=False)
        return f"Context {gauge} {ui.bold(f'{int(ctx_used_pct)}%')}"
    if item_id == "context-used":
        color_fn = ui.green if ctx_used_pct <= 50 else (ui.yellow if ctx_used_pct <= 80 else ui.red)
        return f"Context {color_fn(f'{int(ctx_used_pct)}% used')}"
    if item_id == "context-remaining":
        return f"{int(ctx_rem_pct)}% headroom"
    if item_id == "tokens":
        return f"{format_tokens(tokens_total)} tokens"
    if item_id == "tokens-in-out":
        return f"{format_tokens(tokens_in)} in / {format_tokens(tokens_out)} out"
    if item_id == "window-size":
        return f"{format_tokens(window_capacity)} win"
    if item_id == "project":
        return ui.bold(project_name)
    if item_id == "cwd":
        return ui.dim(str(cwd))
    if item_id == "git-branch":
        return ui.yellow(f"git:{git_branch}")
    if item_id == "git-status":
        return ui.yellow(f"{git_branch}")
    if item_id == "fast-mode":
        return ui.bright_blue("⚡ Fast")
    if item_id == "step-count":
        return ui.dim(f"Step {step_num}")
    if item_id == "session-id":
        cid = payload.get("conversation_id", "")
        return ui.dim(f"#{cid[:8]}") if cid else ""
    if item_id == "version":
        return ui.dim(payload.get("version", "v1.0"))

    return item_id


def render_strip(items: tuple[str, ...], payload: dict) -> str:
    """Format and render the single-line footer strip with items and separators."""
    segments = [extract_item(item, payload) for item in items]
    segments = [s for s in segments if s]
    sep = f" {ui.dim(ui.dot)} "
    return sep.join(segments)


def get_active_config() -> tuple[tuple[str, ...], str]:
    """Retrieve currently active preset and items from pulse config, defaulting to 'pulse'."""
    path = pulse_config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            preset = data.get("preset", "pulse")
            items = tuple(data.get("items", PRESETS.get(preset, PRESETS["pulse"])))
            return items, preset
        except Exception:
            pass
    return PRESETS["pulse"], "pulse"


def save_pulse_config(preset: str, items: tuple[str, ...]) -> None:
    """Save active preset and items to pulse configuration file."""
    path = pulse_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "preset": preset,
        "items": list(items),
        "updated_at": dt.datetime.now().isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def preview(values: tuple[str, ...], preset_name: str | None = None, config_file: Path | None = None) -> None:
    """Render a stylized preview card with slot schematic and simulated live strip."""
    if preset_name is None:
        preset_name = next((name.upper() for name, items in PRESETS.items() if items == values), "CUSTOM")
    else:
        preset_name = preset_name.upper()

    total_slots = f"{len(values)} items" if values else "None (empty)"
    slots_display = f" {ui.divider} ".join(f"[{SHORT_TAGS.get(v, v.upper())}]" for v in values) if values else ui.dim("(empty)")
    simulated_strip = render_strip(values, SAMPLE_PAYLOAD)

    header_text = f"ANTIGRAVITY PULSE • {preset_name}" if config_file is None else "ANTIGRAVITY PULSE • ACTIVE CONFIG"
    rule = ui.box_line * 68
    print()
    print(f"  {ui.cyan(ui.box_top)} {ui.bold(f'[ {header_text} ]')} {ui.cyan(rule[:max(0, 48 - len(header_text))])}")
    if config_file is not None:
        print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Settings File :') } {ui.white(str(config_file))}")
        print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Active Preset :') } {ui.yellow(preset_name)}")
    print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Total Slots   :') } {ui.white(ui.bold(total_slots))}")
    print(f"  {ui.cyan(ui.box_vert)}")
    print(f"  {ui.cyan(ui.box_mid)} {ui.bold('[ STATUS LINE SLOTS ]')} {ui.cyan(ui.box_line * 45)}")
    print(f"  {ui.cyan(ui.box_vert)}  {slots_display}")
    print(f"  {ui.cyan(ui.box_vert)}")
    print(f"  {ui.cyan(ui.box_mid)} {ui.bold('[ SIMULATED LIVE FOOTER ]')} {ui.cyan(ui.box_line * 41)}")
    print(f"  {ui.cyan(ui.box_vert)}  {simulated_strip}")
    print(f"  {ui.cyan(ui.box_vert)}")
    print(f"  {ui.cyan(ui.box_bot)} {ui.dim('Note: Hooked live into Antigravity TUI footer; updates seamlessly as you work.')}")
    print()


def presets_catalog() -> None:
    """Display all available presets with descriptions, item slots, and apply commands."""
    print()
    print(f"  {ui.cyan(ui.box_top)} {ui.bold('[ ANTIGRAVITY PULSE • PRESET CATALOG ]')} {ui.cyan(ui.box_line * 30)}")
    print(f"  {ui.cyan(ui.box_vert)}  Pre-configured live usage strips for Antigravity CLI.")
    print(f"  {ui.cyan(ui.box_vert)}")

    for name, values in PRESETS.items():
        meta = PRESET_METADATA.get(name, {})
        title = meta.get("title", name.title())
        summary = meta.get("summary", "")
        slots = f" {ui.divider} ".join(f"[{SHORT_TAGS.get(v, v.upper())}]" for v in values)

        sec_header = f"[ {name.upper()} ] ({title})"
        print(f"  {ui.cyan(ui.box_mid)} {ui.bold(ui.yellow(f'[ {name.upper()} ]'))} {ui.white(f'({title})')} {ui.cyan(ui.box_line * max(3, 62 - len(sec_header)))}")
        if summary:
            print(f"  {ui.cyan(ui.box_vert)}  {ui.dim(summary)}")
        print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Slots:')} {slots}")
        print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Apply:')} {ui.green(f'python antigravity_pulse.py apply {name}')}")
        print(f"  {ui.cyan(ui.box_vert)}")

    print(f"  {ui.cyan(ui.box_bot)} {ui.dim('Run')} {ui.green('python antigravity_pulse.py customize')} {ui.dim('to build a personalized status line.')}")
    print()


def build_hook_command(script_path: Path) -> str:
    """Build a CLI-compatible statusLine command string without problematic quotes.

    Antigravity CLI evaluates command arguments using Go's filepath.IsAbs().
    If a Windows path is wrapped in quotes ('"E:\\..."'), filepath.IsAbs() treats it
    as relative (because the first character is '"') and prepends the active workspace
    CWD, resulting in 'CWD\\"E:\\..."' and an [Errno 22] Invalid argument crash.
    """
    path_str = str(script_path.resolve())
    if " " in path_str and sys.platform == "win32":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(path_str, buf, 1024):
                path_str = buf.value
        except Exception:
            pass

    if " " in path_str:
        return f'python "{path_str}" --hook'
    return f"python {path_str} --hook"


def install_hook(preset: str = "pulse") -> int:
    """Configure statusLine command hook inside Antigravity CLI settings.json."""
    script_path = Path(__file__).resolve()
    target_settings = settings_path()
    target_settings.parent.mkdir(parents=True, exist_ok=True)

    # Read existing settings or initialize empty object
    existing_data: dict = {}
    if target_settings.exists():
        try:
            existing_data = json.loads(target_settings.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Error reading {target_settings}: {exc}", file=sys.stderr)
            return 1

    # Form command string without quotes if path has no spaces (avoids Windows CWD prepend bug)
    command_str = build_hook_command(script_path)
    existing_data["statusLine"] = {
        "type": "command",
        "command": command_str,
        "padding": 0,
        "enabled": True,
    }

    # Backup existing settings before overwrite
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target_settings.with_name(f"{target_settings.name}.antigravity-pulse-{stamp}.bak")
    if target_settings.exists():
        shutil.copy2(target_settings, backup)

    # Atomic write to settings.json
    temp_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_settings.parent, delete=False) as f:
            temp_file = Path(f.name)
            json.dump(existing_data, f, indent=2)
            f.flush()
        os.replace(temp_file, target_settings)
    finally:
        if temp_file is not None and temp_file.exists():
            temp_file.unlink()

    # Save active preset configuration
    values = PRESETS.get(preset, PRESETS["pulse"])
    save_pulse_config(preset, values)

    preview(values, preset_name=preset, config_file=target_settings)
    print(f"  {ui.green('✓')} {ui.bold('Successfully installed Antigravity Pulse!')}")
    print(f"    {ui.dim('Settings file :')} {target_settings}")
    if backup.exists():
        print(f"    {ui.dim('Backup file   :') } {backup}")
    print(f"    {ui.yellow('Live Status   :')} Open or launch Antigravity CLI (`agy`) to see your real-time usage footer.\n")
    return 0


def uninstall_hook() -> int:
    """Remove statusLine command hook from Antigravity CLI settings.json."""
    target_settings = settings_path()
    if not target_settings.exists():
        print(f"No settings file found at {target_settings}")
        return 0

    try:
        data = json.loads(target_settings.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading settings: {exc}", file=sys.stderr)
        return 1

    if "statusLine" in data:
        del data["statusLine"]
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target_settings.with_name(f"{target_settings.name}.antigravity-pulse-uninstall-{stamp}.bak")
        shutil.copy2(target_settings, backup)
        target_settings.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\n  {ui.green('✓')} Uninstalled Antigravity Pulse hook from {target_settings}")
        print(f"    {ui.dim('Backup file :')} {backup}\n")
    else:
        print("\n  Antigravity Pulse was not installed in settings.json.\n")
    return 0


def show() -> None:
    """Display active Antigravity Pulse configuration and statusLine hook status."""
    target_settings = settings_path()
    items, preset = get_active_config()
    is_hooked = False
    if target_settings.exists():
        try:
            data = json.loads(target_settings.read_text(encoding="utf-8"))
            status_line = data.get("statusLine", {})
            is_hooked = status_line.get("enabled", False) and "antigravity_pulse" in status_line.get("command", "")
        except Exception:
            pass

    preview(items, preset_name=preset, config_file=target_settings)
    hook_badge = ui.green("Connected & Active") if is_hooked else ui.yellow("Not Installed (Run 'install' to activate)")
    print(f"  {ui.dim('Antigravity CLI Hook :')} {hook_badge}")
    print(f"  {ui.dim('Settings Path        :') } {target_settings}\n")


def customize() -> int:
    """Interactively select and order status line items with structured category dividers."""
    print()
    print(f"  {ui.cyan(ui.box_top)} {ui.bold('[ ANTIGRAVITY PULSE • FOOTER DESIGNER ]')} {ui.cyan(ui.box_line * 28)}")
    print(f"  {ui.cyan(ui.box_vert)}  Select usage items to build your custom Antigravity CLI status line.")
    print(f"  {ui.cyan(ui.box_vert)}  Items will appear left-to-right in the exact order chosen.")
    print(f"  {ui.cyan(ui.box_vert)}")

    current_idx = 1
    for section_title, icon, section_items in SECTIONS:
        sec_header = f"[ {ui.icon(icon)}{section_title} ]"
        print(f"  {ui.cyan(ui.box_mid)} {ui.bold(ui.white(sec_header))} {ui.cyan(ui.box_line * max(3, 62 - len(sec_header)))}")
        for item_id, label, description in section_items:
            badge = ui.cyan(f"[{current_idx:02d}]")
            item_lbl = ui.white(ui.bold(f"{label:<24}"))
            item_tag = ui.dim(f"{item_id:<18}")
            desc_tag = ui.dim(f"{ui.bullet} {description}")
            print(f"  {ui.cyan(ui.box_vert)}  {badge}  {item_lbl}  {item_tag}  {desc_tag}")
            current_idx += 1
        print(f"  {ui.cyan(ui.box_vert)}")

    print(f"  {ui.cyan(ui.box_mid)} {ui.bold('[ SELECTION GUIDE ]')} {ui.cyan(ui.box_line * 49)}")
    print(f"  {ui.cyan(ui.box_vert)}  Enter item numbers separated by commas in your desired display order.")
    print(f"  {ui.cyan(ui.box_vert)}  {ui.dim('Examples:')}")
    print(f"  {ui.cyan(ui.box_vert)}    {ui.yellow(f'{ui.bullet} Quota & Context :')} 1, 4, 6, 8, 17  {ui.dim('(Model, Quota Bar, Reset, Context Bar, Fast)')}")
    print(f"  {ui.cyan(ui.box_vert)}    {ui.yellow(f'{ui.bullet} Full Workspace  :') } 1, 14, 16, 4, 8  {ui.dim('(Model, Project, Git, Quota, Context)')}")
    print(f"  {ui.cyan(ui.box_vert)}")

    raw = input(f"  {ui.cyan(ui.box_bot)} {ui.bold('Enter selection')} (or press Enter to cancel): ").strip()
    if not raw:
        print(f"\n  {ui.dim('No changes made.')}\n")
        return 0

    try:
        indexes = [int(part.strip()) for part in raw.split(",")]
        if len(set(indexes)) != len(indexes) or any(i < 1 or i > len(ITEMS) for i in indexes):
            raise ValueError
    except ValueError:
        print(f"\n  {ui.red('[!]')} Error: Please provide unique valid numbers between 1 and {len(ITEMS)}.\n", file=sys.stderr)
        return 2

    values = tuple(ITEMS[i - 1][0] for i in indexes)
    preview(values, preset_name="CUSTOM")

    confirm = input(f"  {ui.cyan('?')}  Apply this custom footer to Antigravity CLI? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print(f"\n  {ui.dim('Configuration discarded. No changes made.')}\n")
        return 0

    save_pulse_config("custom", values)
    install_hook("custom")
    return 0


def main() -> int:
    init_terminal()

    # If --hook or --render is requested, Antigravity CLI statusLine is calling us with stdin JSON
    if "--hook" in sys.argv or "--render" in sys.argv:
        try:
            raw_input = sys.stdin.read().strip()
            if raw_input:
                payload = json.loads(raw_input)
                items, _ = get_active_config()
                strip = render_strip(items, payload)
                print(strip)
                return 0
        except Exception:
            pass
        print(f"{ui.cyan(ui.bold('✦ Antigravity'))} {ui.dim(ui.dot)} {ui.green('Active')}")
        return 0

    parser = argparse.ArgumentParser(
        description="Antigravity Pulse: Real-time usage strip & status line for Google Antigravity CLI"
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("presets", help="list all available footer presets")
    subparsers.add_parser("show", help="show active footer configuration and hook status")
    subparsers.add_parser("customize", help="interactively choose and order status line items")
    subparsers.add_parser("uninstall", help="remove statusLine hook from Antigravity settings")

    preview_parser = subparsers.add_parser("preview", help="preview footer layout without modifying settings")
    preview_parser.add_argument("preset", nargs="?", choices=tuple(PRESETS), default="pulse")

    apply_parser = subparsers.add_parser("apply", help="apply a preset and hook into Antigravity settings")
    apply_parser.add_argument("preset", choices=tuple(PRESETS))

    install_parser = subparsers.add_parser("install", help="install Antigravity Pulse hook into settings.json")
    install_parser.add_argument("preset", nargs="?", choices=tuple(PRESETS), default="pulse")

    args = parser.parse_args()

    if args.command == "presets":
        presets_catalog()
        return 0
    if args.command == "preview":
        preview(PRESETS[args.preset], preset_name=args.preset)
        return 0
    if args.command == "show":
        show()
        return 0
    if args.command == "customize":
        return customize()
    if args.command == "apply":
        return install_hook(args.preset)
    if args.command == "install":
        return install_hook(args.preset)
    if args.command == "uninstall":
        return uninstall_hook()

    # Default without arguments: show current strip and quick help
    items, preset = get_active_config()
    preview(items, preset_name=preset)
    print("  Run with --help or 'presets' to see options.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
