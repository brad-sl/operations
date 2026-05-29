============================================================
CODE REVIEW REPORT
============================================================

## analysis
```json
{
  "issues": [
    {
      "id": 1,
      "description": "`Phase6Runner` is instantiated with `args.config`, but the CLI never defines a `--config`/`-c` argument. The command-line parser therefore never produces `args.config`, so the script raises `AttributeError: 'Namespace' object has no attribute 'config'` and the bot never starts.",
      "root_cause": "The CLI argument list only contains `--mode`/`--confirm-live` and never registers a flag for the configuration path even though it is required by `Phase6Runner`. The later reference to `args.config` assumes such an argument exists.",
      "impact": "The runner crashes immediately on startup with an AttributeError; no orchestration, allocation, or trading logic can execute. Deployments cannot run at all.",
      "fix": "Explicitly add the missing configuration argument so the parser produces `args.config`. If the config is required, mark it as such. For example:\n```python\n    parser.add_argument(\n        \"--config\",\n        required=True,\n        help=\"Path to the Phase 6 configuration file (JSON)\"\n    )\n```\nThis ensures `args.config` always exists before instantiating `Phase6Runner`.",
      "tests": [
        "Run `python phase6_runner.py --mode shadow` and confirm the parser exits with an error mentioning the missing required `--config` argument.",
        "Run `python phase6_runner.py --config path/to/config.json --mode shadow` and verify the runner starts (mock internals if necessary) without raising AttributeError.",
        "Add a unit test for the CLI parser that checks `Namespace` contains `config` when the flag is provided and errors when omitted."
      ]
    }
  ]
}
```

