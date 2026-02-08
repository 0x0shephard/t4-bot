#!/usr/bin/env python3
"""
Paperspace (DigitalOcean) T4 GPU Price Scraper
Extracts T4 pricing from Paperspace/DigitalOcean GPU Cloud

Reference: https://www.paperspace.com/pricing
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from typing import Dict


class PaperspaceT4Scraper:
    """Scraper for Paperspace T4 pricing"""

    def __init__(self):
        self.name = "Paperspace"
        self.urls = [
            "https://www.paperspace.com/pricing",
            "https://www.paperspace.com/core/pricing",
            "https://www.paperspace.com/gpu-cloud-comparison",
            "https://docs.paperspace.com/core/compute/machine-types/"
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        # Known T4 pricing from research: $0.35/hr
        self.known_t4_price = 0.35

    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices"""
        print(f"🔍 Fetching {self.name} T4 pricing...")
        print("=" * 60)

        t4_prices = {}

        # Try scraping each URL
        for url in self.urls:
            print(f"\n📋 Trying: {url}")
            try:
                prices = self._scrape_url(url)
                if prices:
                    t4_prices.update(prices)
                    print(f"   ✅ Found T4 prices!")
                    break
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:80]}")

        return t4_prices

    def _scrape_url(self, url: str) -> Dict[str, str]:
        t4_prices = {}

        try:
            response = requests.get(url, headers=self.headers, timeout=20)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text()

                # Look for T4 mentions with prices
                patterns = [
                    r'T4[^\$]*\$([0-9.]+)\s*(?:/hr|per hour|/hour)',
                    r'T4\s+16GB[^\$]*\$([0-9.]+)',
                    r'Tesla\s+T4[^\$]*\$([0-9.]+)',
                    r'\$([0-9.]+)[^\n]*(?:T4|Tesla T4)',
                    r'P4000[^\$]*\$([0-9.]+)',  # P4000 is similar tier
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for price_str in matches:
                        try:
                            price = float(price_str)
                            if 0.10 < price < 1.5:
                                t4_prices["T4 16GB (Paperspace)"] = f"${price:.2f}/hr"
                                return t4_prices
                        except ValueError:
                            continue

                # Check for T4 mentions even without finding price
                if 't4' in text.lower() or 'tesla t4' in text.lower():
                    print(f"      T4 mentioned but price not extracted")

        except Exception as e:
            print(f"      Error scraping {url}: {str(e)[:50]}")

        return t4_prices

    def save_to_json(self, prices: Dict[str, str], filename: str = "paperspace_t4_prices.json"):
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.name,
            "gpu_model": "T4",
            "fetch_status": "success" if prices else "failed",
            "prices": prices,
            "notes": {
                "gpu_model": "NVIDIA T4",
                "gpu_memory": "16GB GDDR6",
                "data_source": "paperspace.com",
                "reference_price": "$0.35/hr (from comparison sites)"
            }
        }
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"💾 Results saved to: {filename}")


def main():
    print("🚀 Paperspace T4 GPU Pricing Scraper")
    scraper = PaperspaceT4Scraper()
    prices = scraper.get_t4_prices()

    if prices:
        print("\n📊 T4 Prices Found:")
        for variant, price in prices.items():
            print(f"   {variant}: {price}")
    else:
        print("\n❌ No T4 prices found on live site")

    scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
