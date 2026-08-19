# Dashboard Setup (Systemd Service)

## Installation

1. **Copy service file:**
```bash
cp crypto-dashboard.service ~/.config/systemd/user/
```

2. **Reload systemd:**
```bash
systemctl --user daemon-reload
```

3. **Enable on boot:**
```bash
systemctl --user enable crypto-dashboard.service
```

4. **Start immediately:**
```bash
systemctl --user start crypto-dashboard.service
```

5. **Check status:**
```bash
systemctl --user status crypto-dashboard.service
```

## Logs

Dashboard logs to: `logs/dashboard.log`

View live:
```bash
tail -f logs/dashboard.log
```

## Manual Control

**Stop:**
```bash
systemctl --user stop crypto-dashboard.service
```

**Restart:**
```bash
systemctl --user restart crypto-dashboard.service
```

**View logs:**
```bash
journalctl --user -u crypto-dashboard.service -f
```

## Dashboard URL

**Canonical Phase 6 dashboard:** http://localhost:8502 (live mode, `serve_dashboard.py`)

Do **not** use port 8501 unless you have disabled the legacy system unit `crypto-dashboard.service` (OpenClaw Phase4d copy under `~/.openclaw/workspace/operations/crypto-bot`).

Once running:
- **Local:** http://localhost:8502
- **API balances:** http://localhost:8502/api/balances
