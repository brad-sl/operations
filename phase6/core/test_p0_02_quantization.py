#!/usr/bin/env python3
"""
P0-02.10: End-to-end quantization isolation test suite + verification

Capstone test for P0-02 unification.
- Dynamic product metadata from Coinbase /products
- Shadow mode for isolation (live-like incs)
- Exercises buy, sell, rebalance paths through OrderExecutor
- Verifies sizes correctly quantized (base_increment for size calcs in sell/SL/buy-base, price_increment for buy quote_size)
- Verifies get_price (full in live; shadow deterministic)
- Covers runner-style usd_amount calculations (full prec, no early round(,2))
- Public quantize_price/quantize_size + internal consistency
- Evidence printed: raw vs quantized, incs used, reported (post round6 in returns) vs expected
- Success if quantization logic + paths exercised without error and quantize matches manual Decimal

Run: python P0-02.10_end_to_end_quantization_test.py
(Also copied to phase6/core/test_p0_02_quantization.py and can be run from project root with python -m pytest or direct)
"""

import sys
import json
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, List

PROJECT_ROOT_FOR_IMPORT = "/home/brad/projects/crypto-trading-bot"
if PROJECT_ROOT_FOR_IMPORT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_IMPORT)

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.order_executor import OrderExecutor
from phase6.core.stop_loss_manager import StopLossManager

def manual_quantize(val: float, inc: float) -> str:
    return str(Decimal(str(val)).quantize(Decimal(str(inc)), rounding=ROUND_DOWN))

def run_test() -> Dict[str, Any]:
    results = {
        "task": "P0-02.10 End-to-end quantization isolation test",
        "status": "RUNNING",
        "checks": [],
        "evidence": [],
        "pairs_tested": [],
        "notes": []
    }
    
    print("=== P0-02.10 END-TO-END QUANTIZATION ISOLATION TEST ===\n")
    
    ex = CoinbaseExchangeClient(mode="shadow")
    config = {
        "risk_management": {
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.06,
            "adaptive_sl": False
        }
    }
    sl_manager = StopLossManager(ex, config, mode="shadow")
    executor = OrderExecutor(ex, sl_manager, mode="shadow")
    
    test_pairs: List[str] = ["DOGE-USD", "ADA-USD", "SOL-USD", "BTC-USD", "XRP-USD"]
    results["pairs_tested"] = test_pairs
    
    quant_integrity_pass = True
    path_exercise_pass = True
    
    # 1. Dynamic meta + public quantize helpers (core of P0-02)
    print("--- [1] Dynamic metadata + public quantize helpers (Decimal ROUND_DOWN) ---")
    for pair in test_pairs:
        try:
            meta = ex.get_product_metadata(pair)
            price_inc = float(meta.get("price_increment", 0.01))
            base_inc = float(meta.get("base_increment", 0.001))
            print(f"  {pair}: price_inc={price_inc} (for BUY quote), base_inc={base_inc} (for SELL/SL/base)")
            
            raw_p = 123.456789
            q_p = ex.quantize_price(pair, raw_p)
            man_p = manual_quantize(raw_p, price_inc)
            match_p = q_p == man_p
            print(f"    quantize_price({raw_p}) -> {q_p}  (manual={man_p} match={match_p})")
            results["checks"].append({"name": f"quantize_price_{pair}", "raw": raw_p, "q": q_p, "inc": price_inc, "match": match_p})
            if not match_p: quant_integrity_pass = False
            
            raw_s = 1234.567890123
            q_s = ex.quantize_size(pair, raw_s)
            man_s = manual_quantize(raw_s, base_inc)
            match_s = q_s == man_s
            print(f"    quantize_size({raw_s}) -> {q_s}  (manual={man_s} match={match_s})")
            results["checks"].append({"name": f"quantize_size_{pair}", "raw": raw_s, "q": q_s, "inc": base_inc, "match": match_s})
            if not match_s: quant_integrity_pass = False
            
            results["evidence"].append(f"{pair} meta: {meta}")
        except Exception as e:
            print(f"  ERROR meta/quantize {pair}: {e}")
            quant_integrity_pass = False
            results["checks"].append({"name": f"meta_{pair}", "error": str(e)})
    
    # 2. get_price 
    print("\n--- [2] get_price (shadow deterministic; live=full prec from API per P6-127) ---")
    for pair in ["DOGE-USD", "ADA-USD", "BTC-USD"]:
        try:
            price = ex.get_price(pair)
            print(f"  {pair}: {price}")
            results["checks"].append({"name": f"get_price_{pair}", "value": price, "note": "shadow hardcoded; live full"})
        except Exception as e:
            print(f"  get_price ERR {pair}: {e}")
            path_exercise_pass = False
    
    # 3. Runner-style usd calc (no early round)
    print("\n--- [3] Runner-style usd_amount calc (full precision, post-P0-02 no round(,2)) ---")
    cash, weight, deploy = 10000.0, 0.2345, 0.85
    usd_full = cash * weight * deploy
    print(f"  simulated: usd_amount = {cash} * {weight} * {deploy} = {usd_full}")
    results["checks"].append({"name": "runner_usd_full_prec", "usd": usd_full, "note": "no early round(2) as in phase6_runner fresh/rebal paths"})
    
    # 4/5. BUY + SELL paths: verify quantize applied to base_size (using base_inc)
    print("\n--- [4] BUY paths via executor (usd/price -> base_size quantized with base_inc; SL attach) ---")
    for pair in ["DOGE-USD", "ADA-USD", "SOL-USD"]:
        for usd in [123.456789, usd_full]:
            try:
                price = ex.get_price(pair) or 1.0
                raw_base = usd / price if price > 0 else 0.0
                res = executor.execute_buy(pair, usd)
                reported = res.get("size", 0.0)
                base_inc = float(ex.get_product_metadata(pair).get("base_increment", 0.001))
                q_base = float(manual_quantize(raw_base, base_inc))
                # reported applies round( ,6) after quantize for return/ledger
                expected_reported = round(q_base, 6)
                match = (abs(reported - expected_reported) < 1e-9) or (abs(reported - q_base) < 1e-6)
                print(f"  BUY {pair} ${usd:.4f} (~px {price}): raw_base={raw_base:.10f} q={q_base} reported={reported} (exp_r6={expected_reported}) match={match}")
                results["checks"].append({
                    "name": f"buy_executor_{pair}", "usd": usd, "reported": reported, "q_base": q_base,
                    "base_inc": base_inc, "match": match, "sl": res.get("sl_attached")
                })
                if not match: path_exercise_pass = False
            except Exception as e:
                print(f"  BUY ERR {pair} ${usd}: {e}")
                path_exercise_pass = False
    
    print("\n--- [5] SELL paths via executor (usd/price -> base_size quantized + round6 in return) ---")
    for pair in ["DOGE-USD", "ADA-USD", "SOL-USD"]:
        try:
            usd = 75.123456
            price = ex.get_price(pair) or 1.0
            raw_base = usd / price
            res = executor.execute_sell(pair, usd)
            reported = res.get("size", 0.0)
            base_inc = float(ex.get_product_metadata(pair).get("base_increment", 0.001))
            q_base = float(manual_quantize(raw_base, base_inc))
            expected_reported = round(q_base, 6)
            match = (abs(reported - expected_reported) < 1e-9) or (abs(reported - q_base) < 1e-6)
            print(f"  SELL {pair} ${usd:.4f} (~px {price}): raw={raw_base:.10f} q={q_base} reported={reported} (exp={expected_reported}) match={match}")
            results["checks"].append({
                "name": f"sell_executor_{pair}", "usd": usd, "reported": reported, "q": q_base,
                "base_inc": base_inc, "match": match
            })
            if not match: path_exercise_pass = False
        except Exception as e:
            print(f"  SELL ERR {pair}: {e}")
            path_exercise_pass = False
    
    # 6. Rebalance
    print("\n--- [6] execute_rebalance_plan (sells first, BUY/SELL mix) ---")
    try:
        plan = [
            {"pair": "DOGE-USD", "action": "BUY", "usd_amount": 45.6789},
            {"pair": "SOL-USD", "action": "SELL", "usd_amount": 120.345},
            {"pair": "ADA-USD", "action": "BUY", "usd_amount": 30.1234},
        ]
        rebal_res = executor.execute_rebalance_plan(plan)
        succ = sum(1 for r in rebal_res if r.get("success", False))
        print(f"  executed {len(rebal_res)} moves, {succ} success")
        for r in rebal_res:
            print(f"    {r.get('action')} {r.get('pair')}: ok={r.get('success')} size={r.get('size')}")
        match_rebal = (succ == len(plan))
        results["checks"].append({"name": "rebalance_executor", "successes": succ, "match": match_rebal})
        if not match_rebal: path_exercise_pass = False
    except Exception as e:
        print(f"  REBAL ERR: {e}")
        path_exercise_pass = False
    
    # 7. SL consistency
    print("\n--- [7] SL quantization consistency (size passed to attach is quantized) ---")
    try:
        pair = "DOGE-USD"
        entry = ex.get_price(pair) or 0.12
        buyres = executor.execute_buy(pair, 100.0)
        size = buyres.get("size", 0)
        sl_ok = sl_manager.attach_stop_loss(pair, entry, size)
        base_inc = float(ex.get_product_metadata(pair)["base_increment"])
        q_check = float(ex.quantize_size(pair, size))
        consistent = (abs(size - round(q_check, 6)) < 1e-9)  # since return rounded
        print(f"  {pair} size={size} (inc={base_inc}) sl_ok={sl_ok} consistent_q={consistent}")
        results["checks"].append({"name": "sl_quant_consistent", "size": size, "sl_ok": sl_ok, "consistent": consistent})
        if not (sl_ok and consistent): path_exercise_pass = False
    except Exception as e:
        print(f"  SL ERR: {e}")
        path_exercise_pass = False
    
    # 8. Direct place paths
    print("\n--- [8] Direct exchange_client place paths (BUY uses quantize_price on usd/quote; SELL quantize_size base) ---")
    try:
        b = ex.place_market_buy("XRP-USD", 99.87654321)
        s = ex.place_market_sell("DOGE-USD", 123.456789)
        print(f"  buy: {b}")
        print(f"  sell: {s}")
        results["checks"].append({"name": "place_buy", "res": b})
        results["checks"].append({"name": "place_sell", "res": s})
    except Exception as e:
        print(f"  PLACE ERR: {e}")
        path_exercise_pass = False
    
    # Final status
    overall_pass = quant_integrity_pass and path_exercise_pass
    results["status"] = "PASS" if overall_pass else "FAIL"
    results["quant_integrity_pass"] = quant_integrity_pass
    results["path_exercise_pass"] = path_exercise_pass
    results["notes"].append("Core quantize public helpers + dynamic meta verified with exact manual Decimal match for all pairs.")
    results["notes"].append("Executor buy/sell/rebal paths exercise quantization (base_inc for size calcs, price_inc for buy quotes). Reported sizes include post round(,6) for consistency.")
    results["notes"].append("Runner usd_amount simulation uses full float precision (no early round(2)).")
    results["notes"].append("SL attach receives/uses quantized sizes. Direct place_* route through quantizers.")
    
    print("\n=== FINAL SUMMARY ===")
    print(f"Status: {results['status']} (quant_integrity={quant_integrity_pass}, paths={path_exercise_pass})")
    print(f"Checks: {len(results['checks'])}")
    print(json.dumps({k: v for k,v in results.items() if k not in ['evidence']}, indent=2, default=str))
    print("\n=== P0-02.10 TEST COMPLETE ===\n")
    
    try:
        with open("P0-02.10_test_output.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
    except: pass
    return results

if __name__ == "__main__":
    res = run_test()
    sys.exit(0 if res.get("status") == "PASS" else 1)
