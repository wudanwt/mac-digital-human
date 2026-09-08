# Security / Privacy Notes

- `samples/`, `workspace/`, `outputs/`, `models/` and `vendor/` are ignored by Git by default.
- Do not commit real face videos, cloned voices, internal training materials or API keys.
- The current Web server has no authentication. Keep it bound to localhost unless you intentionally deploy it behind an authenticated reverse proxy.
- `run_web.sh` currently binds to `0.0.0.0` for convenient LAN access. If the Mac is on an untrusted network, change it to `127.0.0.1`.
- The repository contains orchestration code only; third-party model licenses remain separate.
