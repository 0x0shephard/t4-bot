#!/usr/bin/env python3
"""
T4 GPU Weighted Index Calculator

Calculates a weighted T4 GPU index price based on:
1. Hyperscalers (AWS, Azure, GCP, Alibaba, Tencent) - 65% weight
   - Discounts blended: 80% discounted + 20% full price
   - Discounts: AWS 44%, Azure 65%, GCP 65%, Alibaba 30%, Tencent 30%
2. Neoclouds (Vast.ai, Paperspace, etc.) - 35% weight at full price

Reference Config: NVIDIA T4 (16GB GDDR6)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


class T4IndexCalculator:
    """Calculate weighted T4 GPU index price"""
    
    def __init__(self, t4_dir: str = "."):
        self.t4_dir = Path(t4_dir)
        
        # Base T4 configuration
        self.base_config = {
            "gpu_model": "NVIDIA T4",
            "gpu_memory_gb": 16,
            "form_factor": "PCIe"
        }
        
        # Define hyperscalers (Only major western clouds as per user request)
        self.hyperscalers = ["AWS", "Azure", "GCP"]
        
        # Static hyperscaler discounts (matching H200 logic where applicable)
        self.hyperscaler_discounts = {
            "AWS": 0.44,           # 44% (Savings Plans)
            "Azure": 0.65,         # 65% (Reserved/EA)
            "GCP": 0.65,           # 65% (CUDs)
        }
        
        # Discount blend
        self.discounted_weight = 0.80
        self.full_price_weight = 0.20
        
        # Total component weights
        self.hyperscaler_total_weight = 0.65
        self.neocloud_total_weight = 0.35
        
        # Hyperscaler individual weights (Market Share Estimates)
        self.hyperscaler_weights = {
            "AWS": 0.45,
            "Azure": 0.30,
            "GCP": 0.25,
        }
        
        # Neocloud individual weights (Relative importance - Alibaba/Tencent move here)
        self.neocloud_weights = {
            "Alibaba Cloud": 0.15,
            "Tencent Cloud": 0.15,
            "Vast.ai": 0.15,
            "Paperspace": 0.15,
            "Replicate": 0.10,
            "Thunder Compute": 0.10,
            "Cerebrium": 0.10,
            "NeevCloud": 0.10,
            # Fallback
            "default": 0.05
        }
        
        # Aliases for mapping scraper names to calculator names
        self.provider_aliases = {
            "Google Cloud": "GCP",
            "Google": "GCP",
            "Amazon Web Services": "AWS",
            "Alibaba": "Alibaba Cloud",
            "Tencent": "Tencent Cloud",
            "Thunder": "Thunder Compute"
        }
    
    def normalize_provider_name(self, name: str) -> str:
        """Normalize provider name to standard keys"""
        # Check aliases
        for alias, standard in self.provider_aliases.items():
            if name.lower() == alias.lower():
                return standard
            if alias.lower() in name.lower():
                return standard
        return name

    def load_prices(self, combined_file: str = "t4_combined_prices.json") -> Dict[str, float]:
        """Load prices from combined JSON or fall back to individual files"""
        prices = {}
        file_path = self.t4_dir / combined_file
        
        if file_path.exists():
            print(f"📂 Loading prices from {combined_file}...")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Handle "prices": {"Provider": "$X.XX"} structure
                if "prices" in data and isinstance(data["prices"], dict):
                    for provider, price_val in data["prices"].items():
                        price = self._parse_price(str(price_val))
                        if price > 0:
                            norm_name = self.normalize_provider_name(provider)
                            prices[norm_name] = price
            except Exception as e:
                print(f"⚠️ Error loading combined file: {e}")
        
        # If combined failed or empty, try individual files
        if not prices:
             prices = self.load_from_individual_files()
             
        return prices

    def load_from_individual_files(self) -> Dict[str, float]:
        """Load from individual *_t4_prices.json files"""
        prices = {}
        files = list(self.t4_dir.glob("*_t4_prices.json"))
        
        print(f"📂 Found {len(files)} individual price files")
        
        for f in files:
            try:
                if "combined" in f.name or "getdeploying" in f.name:
                    continue
                    
                with open(f, 'r') as json_f:
                    data = json.load(json_f)
                    
                provider = data.get("provider", f.stem.replace("_t4_prices", "").replace("_"," ").title())
                provider = self.normalize_provider_name(provider)
                
                # Extract price
                price = 0.0
                if "prices" in data:
                    for p_str in data["prices"].values():
                        price = self._parse_price(p_str)
                        if price > 0:
                            break
                            
                if price > 0:
                    prices[provider] = price
                    
            except Exception:
                continue
                
        return prices

    def _parse_price(self, price_str: str) -> float:
        """Extract float price from string like $0.55/hr"""
        match = re.search(r'([0-9.]+)', price_str)
        if match:
            return float(match.group(1))
        return 0.0

    def calculate_index(self):
        """Main calculation logic"""
        prices = self.load_prices()
        
        if not prices:
            print("❌ No pricing data found")
            return
            
        print(f"\n✓ Loaded {len(prices)} prices")
        for p, price in prices.items():
            print(f"  • {p:<20} ${price:.2f}/hr")

        # Split into categories
        hyperscaler_data = {}
        neocloud_data = {}
        
        # 1. Process Hyperscalers
        print("\n" + "="*60)
        print("🏢 HYPERSCALER COMPONENT (Weight: 65%)")
        print("="*60)
        
        hs_weighted_sum = 0
        hs_weight_used = 0
        
        for hs in self.hyperscalers:
            norm_hs = self.normalize_provider_name(hs)
            
            # Find price (handle loose matching)
            price = prices.get(norm_hs)
            if not price:
                # Try finding key containing name
                for k, v in prices.items():
                    if norm_hs.lower() in k.lower():
                        price = v
                        break
            
            if price:
                discount = self.hyperscaler_discounts.get(hs, 0.30)
                disc_price = price * (1 - discount)
                effective_price = (disc_price * self.discounted_weight) + (price * self.full_price_weight)
                
                weight = self.hyperscaler_weights.get(hs, 0.0)
                contribution = effective_price * weight * self.hyperscaler_total_weight
                
                hs_weighted_sum += contribution
                hs_weight_used += weight
                
                hyperscaler_data[hs] = {
                    "original": price,
                    "discounted": disc_price,
                    "effective": effective_price,
                    "weight": weight,
                    "contribution": contribution
                }
                
                print(f"{hs:<15} Orig: ${price:.2f} | Eff: ${effective_price:.2f} | Wgt: {weight:.2f} | Contrib: ${contribution:.4f}")
            else:
                print(f"{hs:<15} ❌ Price not found")

        # Normalize HS weights if missing
        if 0 < hs_weight_used < 1.0:
            factor = 1.0 / hs_weight_used
            hs_weighted_sum *= factor
            print(f"\n⚠️  Normalized HS Sum: ${hs_weighted_sum:.4f} (Factor: {factor:.2f})")
        
        # 2. Process Neoclouds
        print("\n" + "="*60)
        print("☁️  NEOCLOUD COMPONENT (Weight: 35%)")
        print("="*60)
        
        nc_weighted_sum = 0
        nc_weight_used = 0
        
        # Filter prices for neoclouds (exclude hyperscalers)
        nc_providers = []
        for p, price in prices.items():
            is_hs = False
            for hs in self.hyperscalers:
                if self.normalize_provider_name(hs) == p:
                    is_hs = True
                    break
            if not is_hs and "GetDeploying" not in p and "Average" not in p:
                nc_providers.append((p, price))
        
        # Calculate NC weights dynamically if needed, or use static
        # Logic: Normalize available NC weights to sum to 1.0
        
        for p, price in nc_providers:
            # Map provider name to weight key
            w_key = "default"
            for k in self.neocloud_weights:
                if k.lower() in p.lower():
                    w_key = k
                    break
            
            raw_weight = self.neocloud_weights.get(w_key, 0.10)
            nc_weight_used += raw_weight
            
            neocloud_data[p] = {
                "price": price,
                "raw_weight": raw_weight
            }
        
        # Redistribute weights to sum to 1.0 for available providers
        if nc_weight_used > 0:
            for p, data in neocloud_data.items():
                norm_weight = data["raw_weight"] / nc_weight_used
                contribution = data["price"] * norm_weight * self.neocloud_total_weight
                nc_weighted_sum += contribution
                
                print(f"{p:<15} Price: ${data['price']:.2f} | NormWgt: {norm_weight:.2f} | Contrib: ${contribution:.4f}")
        else:
             print("❌ No Neoclouds found")

        # Final Index
        final_index = hs_weighted_sum + nc_weighted_sum
        
        print("\n" + "="*60)
        print(f"🎯 FINAL T4 INDEX: ${final_index:.2f}/hr")
        print("="*60)
        
        # Save Report
        report = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "final_index_price": round(final_index, 2),
            "components": {
                "hyperscaler": round(hs_weighted_sum, 4),
                "neocloud": round(nc_weighted_sum, 4)
            },
            "details": {
                "hyperscalers": hyperscaler_data,
                "neoclouds": neocloud_data
            }
        }
        
        with open("t4_weighted_index.json", "w") as f:
            json.dump(report, f, indent=2)
            print("\n💾 Report saved to t4_weighted_index.json")

if __name__ == "__main__":
    calc = T4IndexCalculator()
    calc.calculate_index()
