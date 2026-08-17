"""Seed local workspace and API key control-plane records.

This module is intended to run inside the public API image as a one-shot
Compose service. It keeps the pip-installable CLI out of PostgreSQL and MongoDB
while still letting checkout-free users provision a local stack.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient


@dataclass(frozen=True)
class PrincipalSeed:
    """One local caller identity to seed in Postgres and MongoDB."""

    api_key: str
    key_id: str
    user_id: str
    workspace_id: str
    key_name: str
    workspace_name: str


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"{name} must be set")
    return value


def _seed_from_env(suffix: str = "") -> PrincipalSeed:
    label = suffix or ""
    api_key = _env(f"API_KEY{label}", "ink_dev_local_key_001" if not suffix else "")
    key_id = os.getenv(f"KEY_ID{label}") or str(uuid.uuid4())
    return PrincipalSeed(
        api_key=api_key,
        key_id=key_id,
        user_id=_env(f"USER_ID{label}", "local-dev-user" if not suffix else ""),
        workspace_id=_env(f"WORKSPACE_ID{label}", "ws_local_001" if not suffix else ""),
        key_name=_env(f"KEY_NAME{label}", "Local Dev Key" if not suffix else "Local Dev Key B"),
        workspace_name=_env(
            f"WORKSPACE_NAME{label}",
            "Local Dev Workspace" if not suffix else "Local Dev Workspace B",
        ),
    )


def _should_seed_b(primary_key: str) -> bool:
    explicit = os.getenv("SEED_PRINCIPAL_B")
    if explicit is not None:
        return explicit == "1"
    return primary_key == "ink_dev_local_key_001"


async def _seed_postgres(connection: asyncpg.Connection, seed: PrincipalSeed) -> None:
    key_hash = hashlib.sha256(seed.api_key.encode("utf-8")).hexdigest()
    key_prefix = f"{seed.api_key[:12]}..."
    await connection.execute(
        """
        INSERT INTO api_keys
          (key_id, key_hash, key_prefix, user_id, workspace_id, name, status,
           permissions, rate_limit)
        VALUES
          ($1, $2, $3, $4, $5, $6, 'active', $7::jsonb, 100)
        ON CONFLICT (key_hash) DO UPDATE SET
          key_id = EXCLUDED.key_id,
          key_prefix = EXCLUDED.key_prefix,
          user_id = EXCLUDED.user_id,
          workspace_id = EXCLUDED.workspace_id,
          name = EXCLUDED.name,
          status = 'active',
          permissions = EXCLUDED.permissions,
          rate_limit = EXCLUDED.rate_limit,
          updated_at = NOW()
        """,
        seed.key_id,
        key_hash,
        key_prefix,
        seed.user_id,
        seed.workspace_id,
        seed.key_name,
        json.dumps(["read", "search", "write"]),
    )


async def _seed_mongo(client: AsyncIOMotorClient, seed: PrincipalSeed) -> None:
    db = client[_env("MONGODB_DB_NAME", "main")]
    await db["workspaces"].update_one(
        {"_id": seed.workspace_id},
        {"$set": {"user_id": seed.user_id, "name": seed.workspace_name}},
        upsert=True,
    )


async def _seed(seed: PrincipalSeed) -> None:
    connection = await asyncpg.connect(_env("DATABASE_URL"))
    mongo = AsyncIOMotorClient(_env("MONGODB_URI", "mongodb://mongodb:27017"))
    try:
        await _seed_postgres(connection, seed)
        await _seed_mongo(mongo, seed)
    finally:
        await connection.close()
        mongo.close()


async def main() -> None:
    primary = _seed_from_env()
    seeds = [primary]
    if _should_seed_b(primary.api_key):
        seeds.append(
            PrincipalSeed(
                api_key=_env("API_KEY_B", "ink_dev_local_key_002"),
                key_id=os.getenv("KEY_ID_B") or str(uuid.uuid4()),
                user_id=_env("USER_ID_B", "local-dev-user-b"),
                workspace_id=_env("WORKSPACE_ID_B", "ws_local_002"),
                key_name=_env("KEY_NAME_B", "Local Dev Key B"),
                workspace_name=_env("WORKSPACE_NAME_B", "Local Dev Workspace B"),
            )
        )

    for seed in seeds:
        await _seed(seed)
        print(f"seeded workspace={seed.workspace_id} key_prefix={seed.api_key[:12]}...")


if __name__ == "__main__":
    asyncio.run(main())
