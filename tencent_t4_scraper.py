#!/usr/bin/env python3
"""
Tencent Cloud T4 GPU Price Scraper
Extracts T4 pricing from Tencent Cloud (GN7 instances)

Reference: https://www.tencentcloud.com/pricing
Known price: ~$0.20/hr for GN7 with T4
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from typing import Dict


class TencentCloudT4Scraper:
    def __init__(self):
        self.name = "Tencent Cloud"
        self.pricing_url = "https://www.tencentcloud.com/products/cvm/pricing"
        self.gpu_url = "https://www.tencentcloud.com/products/gpu"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

    def get_t4_prices(self) -> Dict[str, str]:
        print(f"🔍 Fetching {self.name} T4 pricing...")
        print("=" * 60)

        t4_prices = {}

        urls = [self.pricing_url, self.gpu_url]

        for url in urls:
            print(f"\n📋 Trying: {url}")
            try:
                response = requests.get(url, headers=self.headers, timeout=20)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text = soup.get_text()

                    # Look for T4/GN7 pricing patterns
                    patterns = [
                        r'T4[^\$]*\$([0-9.]+)(?:/hr|/hour|per hour)',
                        r'GN7[^\$]*\$([0-9.]+)',
                        r'Tesla\s*T4[^\$]*\$([0-9.]+)',
                        r'\$([0-9.]+)[^\n]*(?:T4|GN7)',
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, text, re.IGNORECASE)
                        for price_str in matches:
                            try:
                                price = float(price_str)
                                if 0.10 < price < 1.5:
                                    t4_prices["GN7 T4 (Tencent)"] = f"${price:.2f}/hr"
                                    print(f"   ✅ Found T4 price: ${price:.2f}/hr")
                                    return t4_prices
                            except ValueError:
                                continue
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:50]}")

        return t4_prices

    def save_to_json(self, prices: Dict[str, str], filename: str = "tencent_t4_prices.json"):
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.name,
            "gpu_model": "T4",
            "fetch_status": "success" if prices else "failed",
            "prices": prices,
            "notes": {"gpu_model": "NVIDIA T4", "instance_type": "GN7", "reference_price": "$0.20/hr"}
        }
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"💾 Results saved to: {filename}")


def main():
    scraper = TencentCloudT4Scraper()
    prices = scraper.get_t4_prices()
    scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
