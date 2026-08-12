#!/usr/bin/env python3
"""Client helpers for ByteStrike's Sepolia CuOracle commit/reveal oracle."""

import os
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Optional, Sequence, Tuple

from eth_account import Account
from web3 import Web3
from web3.exceptions import TimeExhausted

DEFAULT_CU_ORACLE_ADDRESS = "0x97f557594bA32e51c0eA215B1886111F24E957af"
DEFAULT_SEPOLIA_RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"
SEPOLIA_CHAIN_ID = 11155111
PRICE_DECIMALS = 18

CU_ORACLE_ABI: Sequence[dict] = [
    {
        "type": "function",
        "name": "commitPrice",
        "inputs": [
            {"name": "_assetId", "type": "bytes32"},
            {"name": "_commit", "type": "bytes32"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "updatePrices",
        "inputs": [
            {"name": "_assetId", "type": "bytes32"},
            {"name": "_price", "type": "uint256"},
            {"name": "_nonce", "type": "bytes32"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "getLatestPrice",
        "inputs": [{"name": "_assetId", "type": "bytes32"}],
        "outputs": [
            {
                "components": [
                    {"name": "price", "type": "uint256"},
                    {"name": "lastUpdatedAt", "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "supportedAssets",
        "inputs": [{"name": "", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "owner",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "allowedRoles",
        "inputs": [{"name": "", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "minCommitRevealDelay",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


@dataclass(frozen=True)
class OracleUpdate:
    asset_key: str
    asset_id: str
    price_usd: float
    market: str = ""

    @property
    def price_x18(self) -> int:
        return price_to_x18(self.price_usd)


@dataclass(frozen=True)
class OracleUpdateResult:
    update: OracleUpdate
    commit_hash: str
    commitment_hash: str
    reveal_hash: str
    price_x18: int
    updated_at: int


def price_to_x18(price_usd: float) -> int:
    quantized = Decimal(str(price_usd)) * (Decimal(10) ** PRICE_DECIMALS)
    return int(quantized.to_integral_value(rounding=ROUND_HALF_UP))


def x18_to_usd(price_x18: int) -> float:
    return price_x18 / 10**PRICE_DECIMALS


def normalize_private_key(private_key: str) -> str:
    private_key = private_key.strip()
    return private_key if private_key.startswith("0x") else f"0x{private_key}"


def rpc_candidates(primary_rpc_url: Optional[str]) -> List[str]:
    candidates: List[str] = []
    for value in (
        primary_rpc_url,
        os.getenv("SEPOLIA_FALLBACK_RPC_URL"),
        DEFAULT_SEPOLIA_RPC_URL,
    ):
        if not value:
            continue
        for rpc in value.split(","):
            rpc = rpc.strip()
            if rpc and rpc not in candidates:
                candidates.append(rpc)
    return candidates


class CuOracleClient:
    def __init__(
        self,
        rpc_url: Optional[str],
        private_key: str,
        oracle_address: Optional[str] = None,
        receipt_timeout: int = 300,
    ) -> None:
        self.w3 = self._connect(rpc_candidates(rpc_url))
        self.account = Account.from_key(normalize_private_key(private_key))
        self.address = self.account.address
        self.oracle_address = Web3.to_checksum_address(
            oracle_address or DEFAULT_CU_ORACLE_ADDRESS
        )
        self.contract = self.w3.eth.contract(
            address=self.oracle_address,
            abi=CU_ORACLE_ABI,
        )
        self.receipt_timeout = receipt_timeout

    @staticmethod
    def _connect(candidates: Iterable[str]) -> Web3:
        last_error: Optional[Exception] = None
        for rpc_url in candidates:
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
                if w3.is_connected() and w3.eth.chain_id == SEPOLIA_CHAIN_ID:
                    return w3
            except Exception as exc:
                last_error = exc
        if last_error:
            raise ConnectionError(f"Failed to connect to Sepolia RPC: {last_error}") from last_error
        raise ConnectionError("Failed to connect to any Sepolia RPC endpoint")

    def print_connection_summary(self) -> None:
        balance_eth = self.w3.from_wei(self.w3.eth.get_balance(self.address), "ether")
        owner = self.contract.functions.owner().call()
        can_commit = self.can_commit()
        can_reveal = owner.lower() == self.address.lower() or bool(
            self.contract.functions.allowedRoles(self.address).call()
        )

        print("=" * 70)
        print("BYTESTRIKE CUORACLE PRICE UPDATER")
        print("=" * 70)
        print(f"Chain ID: {self.w3.eth.chain_id}")
        print(f"Latest block: {self.w3.eth.block_number}")
        print(f"Updater address: {self.address}")
        print(f"Balance: {balance_eth:.6f} ETH")
        print(f"CuOracle: {self.oracle_address}")
        print(f"Oracle owner: {owner}")
        print(f"Can commit: {can_commit}")
        print(f"Can reveal: {can_reveal}")
        print("=" * 70)

    def can_commit(self) -> bool:
        owner = self.contract.functions.owner().call()
        if owner.lower() == self.address.lower():
            return True
        return bool(self.contract.functions.allowedRoles(self.address).call())

    def assert_can_reveal(self) -> None:
        owner = self.contract.functions.owner().call()
        if owner.lower() != self.address.lower() and not bool(
            self.contract.functions.allowedRoles(self.address).call()
        ):
            raise PermissionError(
                f"{self.address} is neither the CuOracle owner nor an allowed publisher role"
            )

    def min_commit_reveal_delay(self) -> int:
        return int(self.contract.functions.minCommitRevealDelay().call())

    def is_supported(self, asset_id: str) -> bool:
        return bool(self.contract.functions.supportedAssets(asset_id).call())

    def get_latest_price(self, asset_id: str, block_identifier=None) -> Tuple[int, int]:
        price, updated_at = self.contract.functions.getLatestPrice(asset_id).call(
            block_identifier=block_identifier
        )
        return int(price), int(updated_at)

    def wait_for_price(
        self,
        asset_id: str,
        expected_price_x18: int,
        block_number: int,
        timeout_seconds: int = 60,
    ) -> Tuple[int, int]:
        deadline = time.time() + timeout_seconds
        last_price = 0
        last_updated_at = 0

        while True:
            try:
                latest_block = self.w3.eth.block_number
                block_identifier = block_number if latest_block >= block_number else "latest"
                last_price, last_updated_at = self.get_latest_price(
                    asset_id,
                    block_identifier=block_identifier,
                )
                if last_price == expected_price_x18:
                    return last_price, last_updated_at
            except Exception:
                pass

            if time.time() >= deadline:
                return last_price, last_updated_at
            time.sleep(3)

    def _fee_params(self, bump: int = 0) -> dict:
        base_fee = int(self.w3.eth.gas_price)
        priority = int(self.w3.to_wei(1 + bump, "gwei"))
        max_fee = max(base_fee * (2 + bump), priority * 2)
        return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": priority}

    def _send_transaction(self, func, gas_limit: int, label: str) -> Tuple[str, dict]:
        last_error: Optional[Exception] = None
        for attempt in range(4):
            try:
                tx = func.build_transaction(
                    {
                        "from": self.address,
                        "nonce": self.w3.eth.get_transaction_count(self.address, "pending"),
                        "gas": gas_limit,
                        "chainId": SEPOLIA_CHAIN_ID,
                        **self._fee_params(attempt),
                    }
                )
                signed = self.account.sign_transaction(tx)
                raw_tx = getattr(signed, "raw_transaction", None) or getattr(
                    signed,
                    "rawTransaction",
                    None,
                )
                tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=self.receipt_timeout,
                )
                if int(receipt.get("status", 0)) != 1:
                    raise RuntimeError(f"{label} transaction reverted: {tx_hash.hex()}")
                return tx_hash.hex(), dict(receipt)
            except TimeExhausted:
                raise
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                retryable = (
                    "replacement transaction underpriced" in message
                    or "nonce too low" in message
                    or "already known" in message
                    or "temporarily unavailable" in message
                )
                if not retryable or attempt == 3:
                    break
                time.sleep(3 + attempt * 2)
        raise RuntimeError(f"{label} transaction failed: {last_error}")

    def commit_and_reveal(
        self,
        updates: Sequence[OracleUpdate],
        reveal_wait_seconds: Optional[int] = None,
        verify: bool = True,
    ) -> List[OracleUpdateResult]:
        if not updates:
            return []
        if not self.can_commit():
            raise PermissionError(f"{self.address} cannot commit prices on CuOracle")
        self.assert_can_reveal()

        unsupported = [update.asset_key for update in updates if not self.is_supported(update.asset_id)]
        if unsupported:
            raise ValueError(f"Unsupported CuOracle assets: {', '.join(unsupported)}")

        reveal_wait = (
            reveal_wait_seconds
            if reveal_wait_seconds is not None
            else max(2, self.min_commit_reveal_delay() + 1)
        )

        prepared = []
        print("Committing prices...")
        for update in updates:
            nonce = secrets.token_bytes(32)
            commitment = Web3.solidity_keccak(
                ["uint256", "bytes32"],
                [update.price_x18, nonce],
            )
            tx_hash, receipt = self._send_transaction(
                self.contract.functions.commitPrice(update.asset_id, commitment),
                gas_limit=120_000,
                label=f"commit {update.asset_key}",
            )
            print(f"  commit {update.asset_key}: {tx_hash} (gas {receipt['gasUsed']:,})")
            prepared.append((update, nonce, tx_hash, commitment.hex()))

        print(f"Waiting {reveal_wait}s before reveal...")
        time.sleep(reveal_wait)

        results: List[OracleUpdateResult] = []
        print("Revealing prices...")
        for update, nonce, commit_tx_hash, commitment_hash in prepared:
            tx_hash, receipt = self._send_transaction(
                self.contract.functions.updatePrices(
                    update.asset_id,
                    update.price_x18,
                    nonce,
                ),
                gas_limit=140_000,
                label=f"reveal {update.asset_key}",
            )
            print(f"  reveal {update.asset_key}: {tx_hash} (gas {receipt['gasUsed']:,})")
            latest_price, updated_at = self.wait_for_price(
                update.asset_id,
                update.price_x18,
                int(receipt["blockNumber"]),
            )
            results.append(
                OracleUpdateResult(
                    update=update,
                    commit_hash=commit_tx_hash,
                    commitment_hash=commitment_hash,
                    reveal_hash=tx_hash,
                    price_x18=latest_price,
                    updated_at=updated_at,
                )
            )

        if verify:
            print("Verifying revealed prices...")
            for result in results:
                expected = result.update.price_x18
                if result.price_x18 != expected:
                    raise RuntimeError(
                        f"Verification failed for {result.update.asset_key}: "
                        f"expected {expected}, got {result.price_x18}"
                    )
                print(
                    f"  {result.update.asset_key}: "
                    f"${x18_to_usd(result.price_x18):.6f}/hr "
                    f"at commit timestamp {result.updated_at}"
                )

        return results
