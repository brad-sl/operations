# Handoff: P0 CDP Keys + Re-broaden AgentKit Balance Tests (t_c20927b3)
**Date:** 2026-06-26  
**Task ID:** t_c20927b3  
**Status:** Complete (setup + run with available keys; format issue noted)  
**Assignee:** crypto-orchestrator  
**Workspace:** scratch @ t_c20927b3 (populated with updated test)

## Summary
- Updated .env.example with detailed CDP key acquisition steps (portal.cdp.coinbase.com).
- Appended CDP key section (placeholders) to main .env.
- Fixed agentkit_sl.py _init_agentkit to use correct CdpEvmWalletProviderConfig fields (api_key_id / api_key_secret / wallet_secret instead of legacy api_key_name/private_key).
- Created / ran updated broaden_agentkit_poc_test.py in kanban workspace exercising real provider init path + direct components + balance vs exchange comparison.
- Ran test: CDP keys detected as present (some values in .env), but init failed with "Failed to generate JWT: Key must be either PEM EC key or base64 Ed25519 key".
  - This indicates current CDP_* values in env are either wrong type, incomplete, or mis-copied (CEX PEM key won't work directly for CDP wallet JWT).
- Balances in this isolated run came back 0.0 (likely exchange_client credential loading issue in minimal PYTHONPATH run vs full bot context; prior runs showed live numbers).
- Bare providers init OK; method calls still require wallet_provider arg in current lib version (0.7.4?).
- No accuracy/latency win observed (fallback path).
- PoC path viable once correct CDP keys provided.

## CDP Key Obtain Steps (documented in .env.example)
1. https://portal.cdp.coinbase.com
2. Sign in / create free account + Project.
3. API Keys -> create CDP API Key -> copy ID + Secret.
4. Generate Wallet Secret (Wallets / Security section).
5. Set:
   CDP_API_KEY_ID=...
   CDP_API_KEY_SECRET=...
   CDP_WALLET_SECRET=...
   (Optional) NETWORK_ID=base-sepolia
6. Verify format: secret should allow JWT gen (PEM EC or base64 Ed25519 per error).
7. Re-source .env and re-run test for on-chain wallet data vs CEX spot.

Note: CDP is for on-chain (EVM/Solana non-custodial wallets via CDP). Does not replace or directly query CEX Advanced Trade spot "available" balances used by bot for trading/SL sizing. Useful for future on-chain actions, hybrid views, or verification.

## Artifacts
- Updated: /home/brad/projects/crypto-trading-bot/.env.example
- Updated: /home/brad/projects/crypto-trading-bot/.env (CDP section)
- Updated: /home/brad/projects/crypto-trading-bot/phase6/core/agentkit_sl.py (config fix)
- New in workspace: broaden_agentkit_poc_test.py , broaden_results.json
- Run log in workspace (partial)
- This handoff + will append to MASTER_TASK_TRACKING.md

## Next / Recommendations
- User to obtain *correct* CDP keys from portal (verify the secret format matches lib expectation).
- Once set, re-run the test script in workspace or via full phase6 context to get live holdings comparison (ADA/UNI/LINK/OP etc.).
- If no on-chain holdings, expect CDP to report wallet-specific (possibly 0 or different from CEX).
- Consider enhancing _agentkit_balance_view to actually query via action providers or CDP SDK for accounts if real wallet created.
- For SL attach, continue using as shadow PoC until proven advantage.
- If CDP keys remain problematic, may need to generate fresh ones or check Coinbase AgentKit docs for exact key format.

Evidence: test run output + results.json show CDP path attempted, error isolated to key format/JWT.

## Related Prior
- SL-AGENTKIT series in recent kanban (t_7f13fcfb etc.)
- COINBASE_AGENTKIT_ANALYSIS.md
- MASTER entries on CDP for balance PoC.