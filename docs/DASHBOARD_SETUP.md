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

Once running:
- **Local:** http://localhost:8501
- **Network:** http://192.168.0.91:8501
- **API:** http://192.168.0.91:8501/api/trades (JSON)
