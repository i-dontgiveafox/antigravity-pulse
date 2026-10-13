# Antigravity Pulse

**A real-time, customizable usage strip & status line for Google Antigravity CLI (`agy`).**

Antigravity Pulse replaces the need to run `/usage` or `/quota` manually. It hooks directly into Antigravity CLI's native `statusLine` renderer to display model quotas, countdown reset timers, context window usage, token metrics, and Git state right in your terminal footer.

```text
Gemini 3.8 Flash · Quota ━━━━━━━─ 82% · R:1h 45m · Context ━━────── 24% · ⚡ Fast
```

---

## Features

- **No More `/usage` Spam**: Real-time quota allowance, reset countdown timers, and context headroom update automatically as you code.
- **Native Status Line Hook**: Uses Antigravity CLI's built-in `statusLine` command mechanism (`settings.json`). Zero external proxies or patches.
- **Color-Coded Visual Gauges**: Smooth progress bars (`━━━───────`) that automatically transition green → yellow → red as limits approach.
- **Workflow Presets**: Pre-configured layouts for general coding, rate-limit monitoring, multi-repo dev, long agent runs, and compact screens.
- **Zero Third-Party Dependencies**: Pure Python 3.10+ standard library. Works out-of-the-box on Windows, macOS, and Linux.
- **Full Windows Terminal & ANSI VT Support**: Safe UTF-8 reconfiguration and automatic ASCII fallbacks for legacy shells.

---

## Quick Start

### 1. Preview Layouts
```powershell
python .\antigravity_pulse.py presets
python .\antigravity_pulse.py preview pulse
```

### 2. Install Hook
Install the status line hook into your Antigravity CLI configuration:
```powershell
python .\antigravity_pulse.py install pulse
```
*Your `settings.json` is safely backed up to `.bak` automatically before installation.*

Launch or switch to Antigravity CLI (`agy`) — your footer will now render your live usage strip!

---

## Presets

| Preset | Contents | Best For |
|---|---|---|
| `pulse` *(Default)* | Model, Quota Bar, Reset Timer, Context Bar, Fast Mode | Daily coding & balanced tracking |
| `quota` | Model, Quota %, Reset Countdown, Context %, Token Counts, Window Capacity | Strict rate-limit monitoring |
| `studio` | Model, Project Name, Git Branch, Quota Bar, Context Bar | Multi-repository engineering |
| `sprint` | Model, Step Progress, Context Bar, Quota Bar, Fast Mode | Long autonomous agent tasks |
| `compact` | Model, Quota %, Context %, Git Branch | Narrow terminal panes |
| `wide` | Model & Effort, Project, Branch, Quota Bar, Reset Timer, Context Bar, In/Out Tokens, Fast Mode | Panoramic monitors & deep diagnostics |

Switch presets at any time:
```powershell
python .\antigravity_pulse.py apply studio
python .\antigravity_pulse.py apply quota
```

---

## Customizing Your Footer

Build a custom status line selecting exactly what you want to see:

```powershell
python .\antigravity_pulse.py customize
```

### What You Can Display

- **Model & Intelligence**: Active Gemini model (`Gemini 3.8 Flash`, `Gemini Pro`, `Gemini Next`), reasoning effort (`low`, `medium`, `high`, `max`).
- **Quota & Rate Limits**: Remaining quota visual bar, exact percentage remaining, rolling reset countdown timer (`R:1h 45m`).
- **Context Window & Tokens**: Context gauge (`Context ━━──────── 24%`), context used %, remaining headroom %, input/output token counts, total window size (`1M`).
- **Workspace & Version Control**: Project folder name, working directory, Git branch with dirty state (`main*`), diff summary.
- **Agent State**: Step count (`Step 8`), session ID, Fast mode indicator (`⚡ Fast`), Antigravity version.

---

## Configuration & Management

View active hook status and settings:
```powershell
python .\antigravity_pulse.py show
```

Uninstall and restore the default Antigravity CLI status line:
```powershell
python .\antigravity_pulse.py uninstall
```

Configuration is stored at:
- Windows: `%USERPROFILE%\.gemini\antigravity-cli\settings.json`
- macOS / Linux: `~/.gemini/antigravity-cli/settings.json`

---

## License

MIT. See [LICENSE](LICENSE).
