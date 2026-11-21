
import json
from pathlib import Path
import re

runner_log_path = Path('logs/phase6_runner.log')

def _find_filter_calls(content):
    filter_calls = []
    # Regex to capture filter function calls and their arguments
    # Looking for 'plan = filter_function(..., plan)' or 'plan = apply_to_runner_plan(..., plan)'
    pattern = re.compile(r'(plan = (?:filter_trade_plan_[a-z_]+|apply_to_runner_plan)\((?:[^)]*?),?\s*plan(?:[^)]*?)\))')
    for match in pattern.finditer(content):
        filter_calls.append((match.start(), match.end(), match.group(0)))
    return filter_calls

def inject_logging_around_filters(file_path):
    content = Path(file_path).read_text(encoding='utf-8')
    filter_calls = _find_filter_calls(content)

    # Sort in reverse order to avoid issues with index changes
    filter_calls.sort(key=lambda x: x[0], reverse=True)

    new_content = list(content) # Convert to list for mutable access

    for start, end, call_str in filter_calls:
        # Determine indentation from the line of the call_str
        line_start_idx = content.rfind('\n', 0, start) + 1
        indent = content[line_start_idx:start] # Capture leading whitespace
        indent = re.match(r'^\s*', indent).group(0)

        filter_name_match = re.search(r'filter_trade_plan_([a-z_]+)|apply_to_runner_plan', call_str)
        filter_name = filter_name_match.group(1) if filter_name_match.group(1) else "apply_to_runner_plan"

        # Escaped f-strings for runtime evaluation in the target file
        pre_log_tmpl = "{indent}logger.debug(\"[DEBUG] --- PRE FILTER ({filter_name}) --- len(plan.actions)={{len(plan.actions)}} actions={{json.dumps([{{{{\'pair\\\': a[\\\'pair\\\'], \'usd\\\': a.get(\\\\'usd\\')}}}} for a in plan.actions]) if plan.actions else \'[]\'}}\")\n"
        post_log_tmpl = "{indent}logger.debug(\"[DEBUG] --- POST FILTER ({filter_name}) --- len(plan.actions)={{len(plan.actions)}} actions={{json.dumps([{{{{\'pair\\\': a[\\\'pair\\\'], \'usd\\\': a.get(\\\\'usd\\')}}}} for a in plan.actions]) if plan.actions else \'[]\'}}\")\n"
        
        pre_log = pre_log_tmpl.format(indent=indent, filter_name=filter_name)
        post_log = post_log_tmpl.format(indent=indent, filter_name=filter_name)

        # Insert post-filter log immediately after the call
        new_content.insert(end, post_log)
        
        # Insert pre-filter log immediately before the call
        new_content.insert(line_start_idx, pre_log)

    Path(file_path).write_text("".join(new_content), encoding='utf-8')
    print(f"Injected logging into {file_path}")

# Inject logging
rebalance_coordinator_path = '/home/brad/projects/crypto-trading-bot/phase6/core/rebalance_coordinator.py'
inject_logging_around_filters(rebalance_coordinator_path)

# Also ensure logging level is DEBUG
with open('/home/brad/projects/crypto-trading-bot/logs/phase6_runner.log', 'w') as f: # Clear log for fresh run
    pass
with open('/home/brad/projects/crypto-trading-bot/phase6/core/logging_config.py', 'r') as f:
    log_cfg = f.read()
log_cfg = log_cfg.replace('\"level\": \"INFO\"', '\"level\": \"DEBUG\"')
Path('/home/brad/projects/crypto-trading-bot/phase6/core/logging_config.py').write_text(log_cfg)
print("Set logging to DEBUG")
