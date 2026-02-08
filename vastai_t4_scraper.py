#!/usr/bin/env python3
"""
Vast.ai T4 GPU Price Scraper
Uses Selenium to fetch T4 pricing from Vast.ai website

Reference: https://vast.ai/pricing
The page shows:
- "Vast Pricing" section
- "Rent Tesla T4" button
- "$0.15/hr" price displayed
- "You can rent the Tesla T4 by the hour with prices ranging from $0.080 to $6.667 per hour."
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from typing import Dict


class VastAIT4Scraper:
    """Scraper for Vast.ai T4 pricing using Selenium"""

    def __init__(self):
        self.name = "Vast.ai"
        self.pricing_url = "https://vast.ai/pricing"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices from Vast.ai"""
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
        """Use Selenium to scrape Vast.ai pricing page"""
        t4_prices = {}

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            driver = webdriver.Chrome(options=chrome_options)
            try:
                print("      Loading Vast.ai pricing page...")
                driver.get(self.pricing_url)
                
                # Wait for page to load
                time.sleep(8)

                # Get page source
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                text = soup.get_text(separator=' ')

                print(f"      Page loaded, searching for T4 pricing...")

                # Based on screenshot - look for the specific patterns
                # The page shows: "Rent Tesla T4" and "$0.15/hr" and range "$0.080 to $6.667"

                # Pattern 1: Look for the main displayed price
                main_price_patterns = [
                    r'\$([0-9.]+)/hr\s*You can rent the Tesla T4',
                    r'Rent Tesla T4.*?\$([0-9.]+)/hr',
                    r'\$([0-9.]+)/hr.*?Tesla T4',
                    r'Tesla T4.*?\$([0-9.]+)/hr',
                ]

                for pattern in main_price_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
                    for price_str in matches:
                        try:
                            price = float(price_str)
                            if 0.05 < price < 1.0:
                                t4_prices["T4 (Vast.ai)"] = f"${price:.2f}/hr"
                                print(f"      ✓ Found main price: ${price:.2f}/hr")
                                break
                        except ValueError:
                            continue
                    if t4_prices:
                        break

                # Pattern 2: Look for price range
                range_pattern = r'ranging from \$([0-9.]+) to \$([0-9.]+)'
                range_matches = re.findall(range_pattern, text, re.IGNORECASE)
                for min_p, max_p in range_matches:
                    try:
                        min_price = float(min_p)
                        max_price = float(max_p)
                        if 0.01 < min_price < 1.0:
                            t4_prices["T4 Min (Vast.ai)"] = f"${min_price:.3f}/hr"
                            t4_prices["T4 Max (Vast.ai)"] = f"${max_price:.3f}/hr"
                            print(f"      ✓ Range: ${min_price:.3f} - ${max_price:.3f}/hr")
                            break
                    except ValueError:
                        continue

                # If no specific pattern, try broader search
                if not t4_prices:
                    # Look for any price near T4 text
                    all_prices = re.findall(r'\$([0-9.]+)/hr', text)
                    for price_str in all_prices:
                        price = float(price_str)
                        if 0.10 <= price <= 0.20:  # T4 typical range
                            t4_prices["T4 (Vast.ai)"] = f"${price:.2f}/hr"
                            print(f"      ✓ Found likely T4 price: ${price:.2f}/hr")
                            break

            finally:
                driver.quit()

        except ImportError:
            print("      Selenium not installed - pip install selenium")
        except Exception as e:
            print(f"      Selenium error: {str(e)[:100]}")

        return t4_prices

    def _try_requests(self) -> Dict[str, str]:
        """Fallback: try direct requests"""
        t4_prices = {}

        try:
            response = requests.get(self.pricing_url, headers=self.headers, timeout=20)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text(separator=' ')

                # Look for T4 pricing patterns
                patterns = [
                    r'Rent Tesla T4.*?\$([0-9.]+)/hr',
                    r'\$([0-9.]+)/hr.*?Tesla T4',
                    r'Tesla T4.*?\$([0-9.]+)/hr',
                    r'T4.*?\$([0-9.]+)/hr',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
                    for price_str in matches:
                        price = float(price_str)
                        if 0.05 < price < 1.0:
                            t4_prices["T4 (Vast.ai)"] = f"${price:.2f}/hr"
                            return t4_prices

                # Look for range
                range_pattern = r'ranging from \$([0-9.]+) to \$([0-9.]+)'
                range_matches = re.findall(range_pattern, text, re.IGNORECASE)
                for min_p, max_p in range_matches:
                    min_price = float(min_p)
                    max_price = float(max_p)
                    if 0.01 < min_price < 1.0:
                        t4_prices["T4 Min (Vast.ai)"] = f"${min_price:.3f}/hr"
                        t4_prices["T4 Max (Vast.ai)"] = f"${max_price:.3f}/hr"
                        # Use min as representative price
                        if "T4 (Vast.ai)" not in t4_prices:
                            t4_prices["T4 (Vast.ai)"] = f"${min_price:.2f}/hr"
                        break

        except Exception as e:
            print(f"      Requests error: {str(e)[:50]}")

        return t4_prices

    def save_to_json(self, prices: Dict[str, str], filename: str = "vastai_t4_prices.json"):
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.name,
            "gpu_model": "T4",
            "fetch_status": "success" if prices else "failed",
            "prices": prices,
            "notes": {
                "gpu_model": "NVIDIA Tesla T4",
                "gpu_memory": "16GB GDDR6",
                "data_source": "vast.ai/pricing",
                "pricing_type": "marketplace (variable)",
                "reference_range": "$0.080 - $6.667/hr",
                "typical_price": "$0.15/hr"
            }
        }
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"💾 Results saved to: {filename}")


def main():
    print("🚀 Vast.ai T4 GPU Pricing Scraper")
    scraper = VastAIT4Scraper()
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
