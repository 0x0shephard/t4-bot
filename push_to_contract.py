#!/usr/bin/env python3
"""Push the aggregate T4 index price to ByteStrike CuOracle on Sepolia."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from cu_oracle_client import (
    DEFAULT_CU_ORACLE_ADDRESS,
    CuOracleClient,
    OracleUpdate,
    price_to_x18,
    x18_to_usd,
)

load_dotenv()

T4_ASSET_ID = os.getenv(
    "T4_ASSET_ID",
    "0x3a505fbe2e444482cb9c5d0c70da3dc8dea36ae62656a4c551d7750f3933f1db",
)
T4_MARKET = "T4-PERP"
T4_ASSET_KEY = "T4"


def get_private_key() -> Optional[str]:
    return (
        os.getenv("ORACLE_UPDATER_PRIVATE_KEY")
        or os.getenv("PRIVATE_KEY")
        or os.getenv("WALLET_PRIVATE_KEY")
    )


def get_oracle_address() -> str:
    return (
        os.getenv("CU_ORACLE_ADDRESS")
        or os.getenv("BYTESTRIKE_CU_ORACLE_ADDRESS")
        or DEFAULT_CU_ORACLE_ADDRESS
    )


def load_index_price(path: str) -> float:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    price = data.get("final_index_price")
    if price is None:
        raise ValueError(f"{path} does not contain final_index_price")
    return float(price)


def read_price_from_csv(path: str) -> float:
    with open(path, "r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} is empty")

    latest = rows[-1]
    for column in ("T4_Index_Price", "Full_Index_Price", "index_price", "price"):
        if column in latest:
            return float(latest[column])

    raise ValueError(f"No recognized price column in {path}: {list(latest.keys())}")


def log_update(price_usd: float, result) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset": T4_ASSET_KEY,
        "market": T4_MARKET,
        "asset_id": T4_ASSET_ID,
        "index_price_usd": price_usd,
        "index_price_scaled": price_to_x18(price_usd),
        "commit_tx_hash": result.commit_hash,
        "commitment_hash": result.commitment_hash,
        "tx_hash": result.reveal_hash,
        "commit_timestamp": result.updated_at,
        "contract_address": get_oracle_address(),
        "network": "sepolia",
    }

    log_file = "t4_contract_update_log.json"
    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as handle:
                logs = json.load(handle)
            if not isinstance(logs, list):
                logs = []
        except Exception:
            logs = []

    logs.append(entry)
    logs = logs[-100:]
    with open(log_file, "w", encoding="utf-8") as handle:
        json.dump(logs, handle, indent=2)
    print(f"Logged update to {log_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push aggregate T4 index price to ByteStrike CuOracle",
    )
    parser.add_argument("--price", type=float, help="T4 hourly price in USD")
    parser.add_argument(
        "--index-file",
        default="t4_weighted_index.json",
        help="Weighted index JSON to read when no price is supplied",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Optional legacy CSV input for index price",
    )
    parser.add_argument(
        "--read-only",
        "--show-only",
        dest="show_only",
        action="store_true",
        help="Only show current oracle state",
    )
    parser.add_argument("--no-verify", action="store_true", help="Skip post-reveal verification")
    parser.add_argument(
        "--reveal-wait-seconds",
        type=int,
        default=int(os.getenv("ORACLE_REVEAL_WAIT_SECONDS", "3")),
        help="Seconds to wait between commit and reveal",
    )
    parser.add_argument(
        "--allow-high",
        action="store_true",
        help="Allow prices above $10/hr without aborting",
    )
    return parser.parse_args()


def resolve_price(args: argparse.Namespace) -> float:
    if args.price is not None:
        return args.price
    if args.csv:
        return read_price_from_csv(args.csv)
    return load_index_price(args.index_file)


def main() -> None:
    args = parse_args()
    private_key = get_private_key()
    if not private_key:
        print("ERROR: Set ORACLE_UPDATER_PRIVATE_KEY, PRIVATE_KEY, or WALLET_PRIVATE_KEY")
        sys.exit(1)

    try:
        client = CuOracleClient(
            rpc_url=os.getenv("SEPOLIA_RPC_URL"),
            private_key=private_key,
            oracle_address=get_oracle_address(),
        )
        client.print_connection_summary()

        if not client.is_supported(T4_ASSET_ID):
            raise RuntimeError(f"{T4_ASSET_KEY} asset is not supported: {T4_ASSET_ID}")

        current_price_x18, updated_at = client.get_latest_price(T4_ASSET_ID)
        print("Current T4 index oracle price:")
        print(f"  {T4_ASSET_KEY} ({T4_MARKET}): ${x18_to_usd(current_price_x18):.6f}/hr")
        print(f"  Commit timestamp: {updated_at}")

        if args.show_only:
            return

        price_usd = resolve_price(args)
        if price_usd <= 0:
            raise ValueError(f"Price must be positive, got {price_usd}")
        if price_usd > 10 and not args.allow_high:
            raise ValueError(f"Refusing unusually high T4 price ${price_usd:.2f}/hr")

        current_usd = x18_to_usd(current_price_x18)
        change_pct = ((price_usd - current_usd) / current_usd * 100) if current_usd else 0
        print("Prepared CuOracle update:")
        print(
            f"  {T4_ASSET_KEY} ({T4_MARKET}): "
            f"${current_usd:.6f} -> ${price_usd:.6f}/hr ({change_pct:+.2f}%)"
        )

        updates = [
            OracleUpdate(
                asset_key=T4_ASSET_KEY,
                market=T4_MARKET,
                asset_id=T4_ASSET_ID,
                price_usd=price_usd,
            )
        ]
        results = client.commit_and_reveal(
            updates,
            reveal_wait_seconds=args.reveal_wait_seconds,
            verify=not args.no_verify,
        )
        log_update(price_usd, results[0])

        print("=" * 70)
        print("SUCCESS! T4 INDEX PRICE UPDATED ON-CHAIN")
        print("=" * 70)
        print(f"  Reveal transaction: {results[0].reveal_hash}")
        print(f"  Etherscan: https://sepolia.etherscan.io/tx/{results[0].reveal_hash}")
        print(f"  Price: ${price_usd:.6f}/hr")
    except Exception as exc:
        print("=" * 70)
        print("ERROR: T4 CUORACLE UPDATE FAILED")
        print("=" * 70)
        print(f"  {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
