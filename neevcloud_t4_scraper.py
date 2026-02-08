#!/usr/bin/env python3
"""
NeevCloud T4 GPU Price Scraper
Extracts T4 pricing from NeevCloud using Selenium (anti-bot protection)

Reference: https://www.neevcloud.com/nvidia-tesla-t4.php
Known price: $0.29/GPU/h
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from typing import Dict


class NeevCloudT4Scraper:
    """Scraper for NeevCloud T4 pricing"""

    def __init__(self):
        self.name = "NeevCloud"
        self.base_url = "https://www.neevcloud.com/nvidia-tesla-t4.php"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices"""
        print(f"🔍 Fetching {self.name} T4 pricing...")
        print("=" * 60)

        t4_prices = {}

        methods = [
            ("Selenium Scraper", self._try_selenium),
            ("Direct Requests", self._try_requests),
        ]

        for method_name, method_func in methods:
            print(f"\n📋 Method: {method_name}")
            try:
                prices = method_func()
                if prices:
                    t4_prices.update(prices)
                    print(f"   ✅ Found T4 prices!")
                    break
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:100]}")

        return t4_prices

    def _try_selenium(self) -> Dict[str, str]:
        """Use Selenium to bypass anti-bot protection"""
        t4_prices = {}

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })

            try:
                print("      Loading NeevCloud page with Selenium...")
                driver.get(self.base_url)
                time.sleep(5)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                text = soup.get_text(separator=' ')

                # Look for pricing patterns
                # Pattern: "Pricing start at $0.29/GPU/h" or similar
                patterns = [
                    r'Pricing start[s]? at \$([0-9.]+)/GPU/h',
                    r'\$([0-9.]+)/GPU/h',
                    r'\$([0-9.]+)\s*/\s*GPU\s*/\s*h',
                    r'\$([0-9.]+)\s*per\s*GPU',
                    r'start[s]?\s*(?:at|from)\s*\$([0-9.]+)',
                    r'\$([0-9.]+)(?:/hr|/hour)',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for price_str in matches:
                        try:
                            price = float(price_str)
                            if 0.10 < price < 2.0:
                                t4_prices["T4 (NeevCloud)"] = f"${price:.2f}/hr"
                                print(f"      ✓ Found: ${price:.2f}/hr")
                                return t4_prices
                        except ValueError:
                            continue

            finally:
                driver.quit()

        except ImportError:
            print("      Selenium not installed")
        except Exception as e:
            print(f"      Selenium error: {str(e)[:80]}")

        return t4_prices

    def _try_requests(self) -> Dict[str, str]:
        """Try direct requests (may fail due to anti-bot)"""
        t4_prices = {}

        try:
            session = requests.Session()
            response = session.get(self.base_url, headers=self.headers, timeout=20)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text(separator=' ')

                patterns = [
                    r'Pricing start[s]? at \$([0-9.]+)/GPU/h',
                    r'\$([0-9.]+)/GPU/h',
                    r'\$([0-9.]+)(?:/hr|/hour)',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for price_str in matches:
                        price = float(price_str)
                        if 0.10 < price < 2.0:
                            t4_prices["T4 (NeevCloud)"] = f"${price:.2f}/hr"
                            return t4_prices
            else:
                print(f"      HTTP {response.status_code} - site has anti-bot protection")

        except Exception as e:
            print(f"      Error: {str(e)[:50]}")

        return t4_prices

    def save_to_json(self, prices: Dict[str, str], filename: str = "neevcloud_t4_prices.json"):
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.name,
            "gpu_model": "T4",
            "fetch_status": "success" if prices else "failed",
            "prices": prices,
            "notes": {
                "gpu_model": "NVIDIA Tesla T4",
                "gpu_memory": "16GB GDDR6",
                "data_source": self.base_url,
                "reference_price": "$0.29/GPU/h"
            }
        }
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"💾 Results saved to: {filename}")


def main():
    print("🚀 NeevCloud T4 GPU Pricing Scraper")
    scraper = NeevCloudT4Scraper()
    prices = scraper.get_t4_prices()

    if prices:
        print("\n📊 T4 Prices Found:")
        for variant, price in prices.items():
            print(f"   {variant}: {price}")
    else:
        print("\n❌ No T4 prices found")

    scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
