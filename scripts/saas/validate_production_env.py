#!/usr/bin/env python3
"""Validate production environment configuration against SaaSSettings rules.

Usage:
    python scripts/saas/validate_production_env.py [.env.production]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env_file(filepath: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not filepath.exists():
        raise FileNotFoundError(f"Configuration file not found: {filepath}")
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env[key] = val
    return env


def validate_production(env: dict[str, str]) -> list[str]:
    errors: list[str] = []

    # 1. Environment
    if env.get("SAAS_ENV", "").lower() != "production":
        errors.append("SAAS_ENV must be 'production'")

    # 2. JWT Secret
    jwt_secret = env.get("SAAS_JWT_SECRET", "")
    forbidden = {
        "dev-change-me-before-production",
        "replace-with-a-long-random-production-secret",
        "CHANGE_ME_WITH_A_UNIQUE_RANDOM_SECRET",
        "GENERATE_UNIQUE_RANDOM_32_PLUS_CHARACTERS_JWT_SECRET",
        "ci-test-secret-not-for-production-1234567890",
    }
    if jwt_secret in forbidden or len(jwt_secret) < 32:
        errors.append("SAAS_JWT_SECRET must be a unique, randomly generated secret of 32+ characters")

    # 3. Registration
    if env.get("SAAS_ALLOW_PUBLIC_REGISTRATION", "").lower() in {"true", "1", "yes"}:
        errors.append("SAAS_ALLOW_PUBLIC_REGISTRATION must be 'false' in production")

    # 4. Storage
    storage_backend = env.get("STORAGE_BACKEND", "").lower()
    if storage_backend in {"local", ""}:
        errors.append(f"STORAGE_BACKEND must be 'minio', 's3', 'oss', or 'cos' in production (got: '{storage_backend}')")

    if not env.get("STORAGE_BUCKET"):
        errors.append("STORAGE_BUCKET must not be empty")

    if not env.get("STORAGE_ACCESS_KEY") or not env.get("STORAGE_SECRET_KEY"):
        errors.append("STORAGE_ACCESS_KEY and STORAGE_SECRET_KEY are required for object storage")

    # 5. Database Password
    db_pass = env.get("SAAS_DB_PASSWORD", "")
    if not db_pass or "GENERATE" in db_pass:
        errors.append("SAAS_DB_PASSWORD must be a strong, randomly generated database password")

    # 6. Worker & Queue
    if env.get("WORKER_BACKEND", "").lower() != "redis":
        errors.append("WORKER_BACKEND must be 'redis'")

    # 7. Trusted Hosts
    trusted = env.get("SAAS_TRUSTED_HOSTS", "").strip()
    if not trusted or trusted == "*":
        errors.append("SAAS_TRUSTED_HOSTS must specify explicit hosts (cannot be empty or '*')")

    # 8. CORS
    cors = env.get("SAAS_CORS_ORIGINS", "")
    origins = [o.strip() for o in cors.split(",") if o.strip()]
    if any("localhost" in o or "127.0.0.1" in o for o in origins):
        errors.append("SAAS_CORS_ORIGINS must not contain localhost or 127.0.0.1 in production")

    # 9. AI Label
    if env.get("SAAS_REQUIRE_AI_LABEL", "").lower() not in {"true", "1", "yes"}:
        errors.append("SAAS_REQUIRE_AI_LABEL must be 'true' in production")

    return errors


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env.production")
    print(f"Checking configuration file: {env_path.resolve()}...")
    try:
        env = load_env_file(env_path)
    except Exception as e:
        print(f"[FAIL] Error loading file: {e}", file=sys.stderr)
        return 1

    errors = validate_production(env)
    if errors:
        print(f"\n[FAIL] Found {len(errors)} production validation error(s):", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}", file=sys.stderr)
        return 1

    print("\n[OK] Production configuration validation passed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
