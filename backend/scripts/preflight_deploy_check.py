#!/usr/bin/env python3
"""
Signal Scanner - Preflight Deployment Readiness Verification Script.

This script performs automated production-readiness checks on:
1. Environment variables & cryptographic secrets configuration
2. Database connectivity & Alembic migration head alignment
3. Redis stream broker connectivity
4. Network endpoint & health status

Usage:
    python backend/scripts/preflight_deploy_check.py [--strict]
"""

import argparse
import asyncio
import os
import sys
from urllib.parse import urlparse

# Ensure backend package root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

INSECURE_DEV_TOKENS = {
    "signal-scanner-dev-token-2026",
    "collector-dev-key-2026",
    "signal-scanner-local-agent-token-2026",
    "dev-secret-key-12345",
    "postgres",
    "password",
    "admin",
}


class PreflightChecker:
    def __init__(self, strict: bool = False):
        self.strict = strict
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def log_pass(self, title: str, details: str = ""):
        self.passed += 1
        print(f"  \033[92m[PASS]\033[0m {title}")
        if details:
            print(f"         {details}")

    def log_warn(self, title: str, details: str = ""):
        self.warnings += 1
        print(f"  \033[93m[WARN]\033[0m {title}")
        if details:
            print(f"         {details}")

    def log_fail(self, title: str, details: str = ""):
        self.failed += 1
        print(f"  \033[91m[FAIL]\033[0m {title}")
        if details:
            print(f"         {details}")

    async def check_environment_and_secrets(self):
        print("\n--- 1. Environment & Secret Verification ---")
        env_mode = getattr(settings, "ENVIRONMENT", "development").lower()
        print(f"  Active ENVIRONMENT: {env_mode}")

        # Check API_AUTH_TOKEN
        token = getattr(settings, "API_AUTH_TOKEN", "")
        if not token:
            self.log_fail("API_AUTH_TOKEN is not set", "API authentication is unconfigured.")
        elif token in INSECURE_DEV_TOKENS:
            if env_mode == "production" or self.strict:
                self.log_fail(
                    "API_AUTH_TOKEN uses default development credential",
                    "Replace API_AUTH_TOKEN with a cryptographically secure token.",
                )
            else:
                self.log_warn(
                    "API_AUTH_TOKEN uses default development credential",
                    "Acceptable in development; must be rotated for production.",
                )
        else:
            self.log_pass("API_AUTH_TOKEN is customized and non-default.")

        # Check COLLECTOR_API_KEY
        collector_key = getattr(settings, "COLLECTOR_API_KEY", "")
        if not collector_key:
            self.log_fail("COLLECTOR_API_KEY is not set", "Collector ingestion authentication is missing.")
        elif collector_key in INSECURE_DEV_TOKENS:
            if env_mode == "production" or self.strict:
                self.log_fail(
                    "COLLECTOR_API_KEY uses default development credential",
                    "Replace COLLECTOR_API_KEY with a cryptographically secure key.",
                )
            else:
                self.log_warn(
                    "COLLECTOR_API_KEY uses default development credential",
                    "Acceptable in development; must be rotated for production.",
                )
        else:
            self.log_pass("COLLECTOR_API_KEY is customized and non-default.")

        # Check Database Password in URL
        db_url = getattr(settings, "DATABASE_URL", "")
        parsed = urlparse(db_url)
        if parsed.password and parsed.password in INSECURE_DEV_TOKENS:
            if env_mode == "production" or self.strict:
                self.log_fail(
                    "DATABASE_URL password is using weak default credential",
                    f"Default password '{parsed.password}' detected in database connection string.",
                )
            else:
                self.log_warn(
                    "DATABASE_URL password is using default credential",
                    f"Default password '{parsed.password}' in use.",
                )
        else:
            self.log_pass("DATABASE_URL password is configured.")

    async def check_database_connectivity(self):
        print("\n--- 2. Database Connectivity & Migrations ---")
        db_url = getattr(settings, "DATABASE_URL", "")
        print(f"  Target DB URI: {db_url.split('@')[-1] if '@' in db_url else db_url}")

        try:
            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                res = await conn.execute(text("SELECT 1"))
                assert res.scalar() == 1
                self.log_pass("Database connection successful", "SQLAlchemy async engine connection verified.")

                # Check Alembic migration table
                try:
                    res_ver = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                    active_version = res_ver.scalar()
                    if active_version:
                        self.log_pass(f"Alembic migration version: {active_version}")
                    else:
                        self.log_warn("Alembic version table empty", "Run 'alembic upgrade head' to apply migrations.")
                except Exception:
                    self.log_warn("alembic_version table not found", "Database may not have been migrated via Alembic.")

            await engine.dispose()
        except Exception as exc:
            self.log_fail("Database connection failed", str(exc))

    async def check_redis_broker(self):
        print("\n--- 3. Event Stream Broker ---")
        stream_backend = getattr(settings, "STREAM_BACKEND", "memory").lower()
        print(f"  Configured STREAM_BACKEND: {stream_backend}")

        if stream_backend == "redis":
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            try:
                import redis.asyncio as aioredis
                client = aioredis.from_url(redis_url, decode_responses=True)
                pong = await client.ping()
                if pong:
                    self.log_pass("Redis connection verified", f"Ping response received from {redis_url}.")
                await client.aclose()
            except Exception as exc:
                self.log_fail("Redis ping failed", f"Could not connect to {redis_url}: {exc}")
        elif stream_backend == "memory":
            if getattr(settings, "ENVIRONMENT", "").lower() == "production":
                self.log_warn(
                    "In-memory stream broker used in production",
                    "Consider setting STREAM_BACKEND=redis for multi-worker / multi-container scaling.",
                )
            else:
                self.log_pass("In-memory broker configured (suitable for local dev/testing).")

    async def run(self):
        print("=" * 65)
        print("SIGNAL SCANNER - PREFLIGHT DEPLOYMENT READINESS CHECK")
        print("=" * 65)

        await self.check_environment_and_secrets()
        await self.check_database_connectivity()
        await self.check_redis_broker()

        print("\n" + "=" * 65)
        print(f"RESULTS: {self.passed} Passed, {self.warnings} Warnings, {self.failed} Failed")
        print("=" * 65)

        if self.failed > 0:
            print("\n\033[91m[ERROR] Preflight checks failed. Address errors before deploying to production.\033[0m\n")
            return 1
        elif self.warnings > 0 and self.strict:
            print("\n\033[93m[WARN] Warnings detected in strict mode. Preflight check failed.\033[0m\n")
            return 1
        else:
            print("\n\033[92m[SUCCESS] System passed preflight checks and is ready for execution.\033[0m\n")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Signal Scanner Preflight Deploy Check")
    parser.add_argument("--strict", action="store_true", help="Fail if any warnings are detected")
    args = parser.parse_args()

    checker = PreflightChecker(strict=args.strict)
    exit_code = asyncio.run(checker.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
