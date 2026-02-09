#!/usr/bin/env python3
"""MultiAssetOracle price updater script for T4 GPU rental rates.

Pushes T4 GPU hourly rental index prices to the MultiAssetOracle contract
on Sepolia testnet. The oracle is shared across all GPU markets and uses
asset IDs (bytes32) to distinguish between GPU types.

Pipeline Integration:
  Input:  t4_gpu_index.csv (from GPU pricing pipeline) or --price flag
  Output: t4_contract_update_log.json (transaction history)

Environment Variables:
  SEPOLIA_RPC_URL              Ethereum RPC endpoint
  ORACLE_UPDATER_PRIVATE_KEY   Wallet private key for signing transactions
"""

import csv
import json
import os
import sys
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

load_dotenv()

# ==================== Configuration ====================

SEPOLIA_RPC_URL = os.getenv("SEPOLIA_RPC_URL", "https://rpc.sepolia.org")
PRIVATE_KEY = os.getenv("ORACLE_UPDATER_PRIVATE_KEY") or os.getenv("WALLET_PRIVATE_KEY")

# MultiAssetOracle (shared across all GPU markets)
MULTI_ASSET_ORACLE_ADDRESS = os.getenv(
    "MULTI_ASSET_ORACLE_ADDRESS",
    "0xB44d652354d12Ac56b83112c6ece1fa2ccEfc683",
)

# T4 asset ID: keccak256("T4_HOURLY")
T4_ASSET_ID = "0x3579a517d9a62c57f1158cfdc01603549103ed87556523a42712c9fda4f8439e"

PRICE_DECIMALS = 18

# ==================== ABI ====================

MULTI_ASSET_ORACLE_ABI: Sequence[dict] = [
    {
        "type": "function",
        "name": "updatePrice",
        "inputs": [
            {"name": "assetId", "type": "bytes32"},
            {"name": "newPrice", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "getPrice",
        "inputs": [
            {"name": "assetId", "type": "bytes32"},
        ],
        "outputs": [
            {"name": "", "type": "uint256"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "getPriceData",
        "inputs": [
            {"name": "assetId", "type": "bytes32"},
        ],
        "outputs": [
            {"name": "price", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "isAssetRegistered",
        "inputs": [
            {"name": "assetId", "type": "bytes32"},
        ],
        "outputs": [
            {"name": "", "type": "bool"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "event",
        "name": "PriceUpdated",
        "inputs": [
            {"name": "assetId", "type": "bytes32", "indexed": True},
            {"name": "price", "type": "uint256", "indexed": False},
            {"name": "timestamp", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
]


@dataclass
class PriceData:
    price_raw: int
    updated_at: int = 0

    @property
    def price(self) -> float:
        return self.price_raw / 10**PRICE_DECIMALS

    @property
    def last_updated_str(self) -> str:
        if self.updated_at == 0:
            return "never"
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )


class T4OraclePriceUpdater:
    """Update T4 GPU rental price on the MultiAssetOracle contract.

    The MultiAssetOracle stores prices for multiple GPU types (H100, H200,
    B200, A100, T4, etc.) keyed by asset ID (bytes32). This updater targets
    the T4_HOURLY asset specifically.
    """

    def __init__(self, rpc_url: str, private_key: str, oracle_address: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")

        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.asset_id = T4_ASSET_ID
        self.oracle_address = oracle_address
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(oracle_address),
            abi=MULTI_ASSET_ORACLE_ABI,
        )

        balance_eth = self.w3.from_wei(
            self.w3.eth.get_balance(self.address), "ether"
        )

        print("Connected to Sepolia testnet")
        print(f"   Chain ID:          {self.w3.eth.chain_id}")
        print(f"   Latest block:      {self.w3.eth.block_number}")
        print(f"   Updater address:   {self.address}")
        print(f"   Balance:           {balance_eth:.4f} ETH")
        print(f"   MultiAssetOracle:  {oracle_address}")
        print(f"   Asset:             T4_HOURLY")
        print(f"   Asset ID:          {self.asset_id}")

        # Check asset is registered
        is_registered = self.contract.functions.isAssetRegistered(
            bytes.fromhex(self.asset_id[2:])
        ).call()
        if not is_registered:
            raise ValueError(
                f"T4_HOURLY asset is not registered in MultiAssetOracle. "
                f"Run the DeployT4Market script first."
            )

        latest = self.get_current_price()
        if latest.price_raw:
            print(f"   Current price:     ${latest.price:.6f}/hr")
            print(f"   Last updated:      {latest.last_updated_str}")
        else:
            print("   Current price:     not set")

    def _build_dynamic_fee(self) -> Tuple[int, int]:
        base_fee = self.w3.eth.gas_price
        max_priority = self.w3.to_wei(1, "gwei")
        max_fee = max(base_fee * 2, max_priority * 2)
        return max_fee, max_priority

    def _send_transaction(self, func, gas_limit: int) -> Tuple[str, dict]:
        max_fee, max_priority = self._build_dynamic_fee()
        tx = func.build_transaction(
            {
                "from": self.address,
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "gas": gas_limit,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority,
                "chainId": 11155111,
            }
        )
        signed = self.account.sign_transaction(tx)

        if hasattr(signed, "raw_transaction"):
            raw_tx = signed.raw_transaction
        elif hasattr(signed, "rawTransaction"):
            raw_tx = signed.rawTransaction
        else:
            raw_tx = signed

        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        return tx_hash.hex(), dict(receipt)

    def get_current_price(self) -> PriceData:
        try:
            asset_bytes = bytes.fromhex(self.asset_id[2:])
            price_raw, updated_at = self.contract.functions.getPriceData(
                asset_bytes
            ).call()
            return PriceData(price_raw=price_raw, updated_at=updated_at)
        except Exception:
            return PriceData(price_raw=0, updated_at=0)

    def update_price(self, price_usd: float) -> str:
        """Update the T4 GPU rental price on the MultiAssetOracle.

        Args:
            price_usd: New price in USD per hour (e.g., 0.45)

        Returns:
            Transaction hash of the update transaction
        """
        price_scaled = int(price_usd * (10**PRICE_DECIMALS))
        asset_bytes = bytes.fromhex(self.asset_id[2:])
        current = self.get_current_price()

        if current.price_raw:
            delta = price_usd - current.price
            change_pct = (delta / current.price) * 100 if current.price else 0
            print(f"Current oracle: ${current.price:.6f}/hr (delta {change_pct:+.2f}%)")

        print(f"Updating to:    ${price_usd:.6f}/hr")
        print("Sending transaction...")

        tx_hash, receipt = self._send_transaction(
            self.contract.functions.updatePrice(asset_bytes, price_scaled),
            gas_limit=100_000,
        )

        print(f"Transaction confirmed: {tx_hash}")
        print(f"Gas used: {receipt['gasUsed']:,}")

        # Verify
        latest = self.get_current_price()
        if latest.price_raw == price_scaled:
            print(f"On-chain price verified: ${latest.price:.6f}/hr")
        else:
            print(f"WARNING: On-chain price mismatch!")
            print(f"   Expected: ${price_usd:.6f}/hr")
            print(f"   Got:      ${latest.price:.6f}/hr")

        self._log_update(price_usd, tx_hash, receipt["blockNumber"])
        return tx_hash

    def read_price_from_csv(self, csv_file: str) -> Optional[float]:
        """Read T4 GPU price from pipeline-generated CSV file.

        Expected CSV columns:
        - Full_Index_Price or T4_Index_Price: Weighted average price
        - Calculation_Date: Timestamp of calculation
        """
        try:
            with open(csv_file, "r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
        except FileNotFoundError:
            print(f"ERROR: CSV file not found: {csv_file}")
            return None
        except Exception as exc:
            print(f"ERROR: Failed to read CSV: {exc}")
            return None

        if not rows:
            print(f"ERROR: CSV file is empty: {csv_file}")
            return None

        latest = rows[-1]

        # Try different column names
        price_col = None
        for col in ("T4_Index_Price", "Full_Index_Price", "index_price", "price"):
            if col in latest:
                price_col = col
                break

        if price_col is None:
            print(f"ERROR: No recognized price column found")
            print(f"   Available columns: {list(latest.keys())}")
            return None

        try:
            price = float(latest[price_col])
        except (ValueError, TypeError) as exc:
            print(f"ERROR: Invalid price value: {latest[price_col]} ({exc})")
            return None

        timestamp = latest.get("Calculation_Date", latest.get("timestamp", "unknown"))
        print("=" * 60)
        print("T4 GPU INDEX PRICE FROM PIPELINE")
        print("=" * 60)
        print(f"   Calculation Date: {timestamp}")
        print(f"   Index Price:      ${price:.6f}/hour")
        print(f"   Source column:    {price_col}")
        print("=" * 60)

        return price

    def _log_update(
        self, price_usd: float, tx_hash: str, block_number: int
    ) -> None:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "asset": "T4_HOURLY",
            "asset_id": self.asset_id,
            "index_price_usd": price_usd,
            "index_price_scaled": int(price_usd * (10**PRICE_DECIMALS)),
            "tx_hash": tx_hash,
            "block_number": block_number,
            "contract_address": self.oracle_address,
            "network": "sepolia",
            "updater_address": self.address,
        }

        log_file = "t4_contract_update_log.json"
        logs = []

        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as handle:
                    logs = json.load(handle)
                if not isinstance(logs, list):
                    logs = []
            except (json.JSONDecodeError, Exception):
                logs = []

        logs.append(log_entry)
        logs = logs[-100:]

        try:
            with open(log_file, "w", encoding="utf-8") as handle:
                json.dump(logs, handle, indent=2)
            print(f"Logged update to {log_file} (entry {len(logs)}/100)")
        except Exception as exc:
            print(f"ERROR: Failed to write log: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push T4 GPU index price to MultiAssetOracle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  SEPOLIA_RPC_URL              Ethereum RPC endpoint (default: https://rpc.sepolia.org)
  ORACLE_UPDATER_PRIVATE_KEY   Wallet private key for signing transactions
  MULTI_ASSET_ORACLE_ADDRESS   MultiAssetOracle contract address

Examples:
  # Use pipeline CSV
  python scripts/update_t4_oracle_price.py --csv t4_gpu_index.csv

  # Manual price update
  python scripts/update_t4_oracle_price.py --price 0.45

  # Read current on-chain price only
  python scripts/update_t4_oracle_price.py --read-only
        """,
    )
    parser.add_argument(
        "--csv",
        default="t4_gpu_index.csv",
        help="Path to T4 GPU index CSV (default: t4_gpu_index.csv)",
    )
    parser.add_argument(
        "--price",
        type=float,
        help="Manual price override in USD/hour (bypasses CSV)",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only read and display current on-chain price, don't update",
    )
    args = parser.parse_args()

    if not PRIVATE_KEY:
        print("=" * 60)
        print("ERROR: Private key not configured")
        print("=" * 60)
        print("Set one of these environment variables:")
        print("  - ORACLE_UPDATER_PRIVATE_KEY")
        print("  - WALLET_PRIVATE_KEY")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("T4 GPU ORACLE PRICE UPDATER")
    print("=" * 60)

    try:
        updater = T4OraclePriceUpdater(
            rpc_url=SEPOLIA_RPC_URL,
            private_key=PRIVATE_KEY,
            oracle_address=MULTI_ASSET_ORACLE_ADDRESS,
        )
    except ConnectionError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: Failed to initialize: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if args.read_only:
        current = updater.get_current_price()
        print("\n" + "=" * 60)
        print("CURRENT ON-CHAIN T4 PRICE")
        print("=" * 60)
        print(f"   Price:        ${current.price:.6f}/hr")
        print(f"   Raw:          {current.price_raw}")
        print(f"   Last updated: {current.last_updated_str}")
        print("=" * 60)
        sys.exit(0)

    # Determine price source
    if args.price is not None:
        price = args.price
        print("\n" + "=" * 60)
        print("MANUAL PRICE OVERRIDE")
        print("=" * 60)
        print(f"   Using manual price: ${price:.6f}/hour")
        print("=" * 60)
    else:
        price = updater.read_price_from_csv(args.csv)
        if price is None:
            print("\nERROR: Unable to read price from CSV")
            print("Use --price <value> to set manually")
            sys.exit(1)

    if price <= 0:
        print(f"\nERROR: Price must be > 0 (got {price})")
        sys.exit(1)

    if price > 10:
        print(f"\nWARNING: ${price:.2f}/hr seems high for T4 GPU")
        print("Expected range: $0.10-$2.00/hour")
        print("Proceeding anyway...\n")

    # Execute update
    print("\n" + "=" * 60)
    print("EXECUTING BLOCKCHAIN UPDATE")
    print("=" * 60)
    try:
        tx_hash = updater.update_price(price)
        print("\n" + "=" * 60)
        print("SUCCESS! T4 PRICE UPDATED ON-CHAIN")
        print("=" * 60)
        print(f"   Transaction: {tx_hash}")
        print(f"   Etherscan:   https://sepolia.etherscan.io/tx/{tx_hash}")
        print(f"   Price:       ${price:.6f}/hour")
        print("=" * 60)
        sys.exit(0)
    except Exception as exc:
        print("\n" + "=" * 60)
        print("ERROR: BLOCKCHAIN UPDATE FAILED")
        print("=" * 60)
        print(f"   {exc}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
