# Task Handoff — Gmail Batch B (INBOX 2024 archive)

**Task ID:** `MAIL-GMAIL-BATCH-B-20260813`  
**Assigned To:** default / Scotty (not crypto-engineer)  
**Date:** 2026-08-13  
**Blocked on:** Gmail IMAP STATUS/SEARCH succeeding (Batch A left account rate-limited)

### Objective
After IMAP is healthy, measure remaining INBOX and archive **2024 unflagged** mail to All Mail (not Trash), same rules as Batch A.

### Must Do
- `himalaya account check` + `imap status INBOX` OK first
- Count 2024 unflagged vs flagged; exclude flagged
- Reuse `~/mail-agent/archive_inbox_before.py` with `ARCHIVE_BEFORE=2025-01-01` (or 2024-only search)
- Resume via `done_uids.txt` **or** a new state dir so Batch A UIDs are not confused
- No Trash; no mass delete

### Must Not
- Start while STATUS is `os error 11`
- Touch flagged
- Process 2025+ except by explicit Brad OK

### Success
INBOX pre-2025 unflagged remaining ≈ 0; measure file in `~/mail-agent/`

### Validation
`himalaya imap search -m INBOX --before 2025-01-01 --unflagged --json` count → 0
