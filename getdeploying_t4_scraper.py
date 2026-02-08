#!/usr/bin/env python3
"""
GetDeploying T4 GPU Price Aggregator
Scrapes getdeploying.com for comprehensive T4 pricing across all providers
Extracts on-demand, spot, and reserved pricing, then normalizes to base model

Reference: https://getdeploying.com/gpus/nvidia-t4
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import statistics
from typing import Dict, List, Tuple


class GetDeployingT4Scraper:
    """Comprehensive T4 price aggregator from getdeploying.com"""

    def __init__(self):
        self.name = "GetDeploying"
        self.base_url = "https://getdeploying.com/gpus/nvidia-t4"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        # Base T4 model: Standard T4 with 16GB VRAM (most common)
        self.base_model = "T4 16GB"

    def get_t4_prices(self) -> Dict[str, any]:
        """Main method to extract all T4 prices and organize by provider"""
        print(f"🔍 Fetching {self.name} T4 pricing...")
        print("=" * 60)

        all_prices = {}
        raw_data = []

        methods = [
            ("Selenium Scraper", self._try_selenium),
            ("Direct Requests", self._try_requests),
        ]

        for method_name, method_func in methods:
            print(f"\n📋 Method: {method_name}")
            try:
                prices, data = method_func()
                if prices:
                    all_prices.update(prices)
                    raw_data.extend(data)
                    print(f"   ✅ Found {len(data)} T4 price entries!")
                    break
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:100]}")

        return all_prices

    def _try_selenium(self) -> Tuple[Dict, List]:
        """Use Selenium to scrape the pricing table"""
        prices = {}
        raw_data = []

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
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            driver = webdriver.Chrome(options=chrome_options)
            try:
                print("      Loading GetDeploying T4 page...")
                driver.get(self.base_url)
                time.sleep(8)

                # Scroll to load all content
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Find all tables
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        row_text = ' '.join([cell.get_text().strip() for cell in cells])
                        
                        # Extract provider and price
                        entry = self._parse_row(row_text, cells)
                        if entry:
                            raw_data.append(entry)

                # Also search for price patterns in general text
                text = soup.get_text(separator=' ')
                additional_prices = self._extract_prices_from_text(text)
                raw_data.extend(additional_prices)

                # Organize by provider
                prices = self._organize_prices(raw_data)

                if prices:
                    print(f"      ✓ Extracted prices from {len(prices)} providers")
                    for provider, price_info in list(prices.items())[:5]:
                        print(f"        - {provider}: {price_info.get('on_demand', 'N/A')}")

            finally:
                driver.quit()

        except ImportError:
            print("      Selenium not installed - pip install selenium")
        except Exception as e:
            print(f"      Selenium error: {str(e)[:100]}")

        return prices, raw_data

    def _try_requests(self) -> Tuple[Dict, List]:
        """Fallback: try direct requests"""
        prices = {}
        raw_data = []

        try:
            response = requests.get(self.base_url, headers=self.headers, timeout=20)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text(separator=' ')
                raw_data = self._extract_prices_from_text(text)
                prices = self._organize_prices(raw_data)
        except Exception as e:
            print(f"      Requests error: {str(e)[:50]}")

        return prices, raw_data

    def _parse_row(self, row_text: str, cells: list) -> Dict:
        """Parse a table row to extract provider, instance, price, billing type"""
        providers = ['AWS', 'Azure', 'Google Cloud', 'GCP', 'Alibaba', 'Thunder Compute', 
                     'Cerebrium', 'Replicate', 'Vast.ai', 'RunPod', 'Lambda']
        
        entry = {}
        
        # Check for provider
        for provider in providers:
            if provider.lower() in row_text.lower():
                entry['provider'] = provider
                break
        
        if not entry.get('provider'):
            return None

        # Extract price ($/hr pattern)
        price_match = re.search(r'\$([0-9.]+)(?:/hr|/hour)?', row_text)
        if price_match:
            entry['price'] = float(price_match.group(1))
        
        # Check billing type
        if 'spot' in row_text.lower():
            entry['billing'] = 'spot'
        elif 'reserved' in row_text.lower() or 'commit' in row_text.lower():
            entry['billing'] = 'reserved'
        else:
            entry['billing'] = 'on_demand'

        # Extract GPU count
        gpu_match = re.search(r'(\d+)\s*x?\s*T4', row_text, re.IGNORECASE)
        if gpu_match:
            entry['gpu_count'] = int(gpu_match.group(1))
        else:
            entry['gpu_count'] = 1

        return entry if 'price' in entry else None

    def _extract_prices_from_text(self, text: str) -> List[Dict]:
        """Extract price entries from general text"""
        entries = []
        
        # Look for price patterns with context
        patterns = [
            (r'(AWS|Azure|Google Cloud|GCP|Alibaba)[^\$]*\$([0-9.]+)/hr', 'on_demand'),
            (r'\$([0-9.]+)/hr[^\n]*(AWS|Azure|Google Cloud|GCP|Alibaba)', 'on_demand'),
            (r'spot[^\$]*\$([0-9.]+)', 'spot'),
            (r'\$([0-9.]+)[^\n]*spot', 'spot'),
        ]

        for pattern, billing in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        if match[0].replace('.', '').isdigit():
                            price = float(match[0])
                            provider = match[1] if len(match) > 1 else 'Unknown'
                        else:
                            provider = match[0]
                            price = float(match[1])
                    else:
                        price = float(match)
                        provider = 'Unknown'
                    
                    if 0.05 < price < 10.0:
                        entries.append({
                            'provider': provider,
                            'price': price,
                            'billing': billing,
                            'gpu_count': 1
                        })
                except (ValueError, IndexError):
                    continue

        return entries

    def _organize_prices(self, raw_data: List[Dict]) -> Dict[str, Dict]:
        """Organize prices by provider with on-demand, spot, reserved"""
        organized = {}

        for entry in raw_data:
            provider = entry.get('provider', 'Unknown')
            if provider not in organized:
                organized[provider] = {
                    'on_demand': None,
                    'spot': None,
                    'reserved': None,
                    'all_prices': []
                }

            price = entry.get('price')
            billing = entry.get('billing', 'on_demand')
            gpu_count = entry.get('gpu_count', 1)

            # Normalize to per-GPU price
            per_gpu_price = price / gpu_count if gpu_count > 0 else price

            organized[provider]['all_prices'].append(per_gpu_price)

            # Set specific billing type price (use min for that type)
            current = organized[provider].get(billing)
            if current is None or per_gpu_price < float(current.replace('$', '').replace('/hr', '')):
                organized[provider][billing] = f"${per_gpu_price:.2f}/hr"

        # Calculate averages
        for provider in organized:
            if organized[provider]['all_prices']:
                avg = statistics.mean(organized[provider]['all_prices'])
                organized[provider]['average'] = f"${avg:.2f}/hr"

        return organized

    def get_normalized_prices(self) -> Dict[str, str]:
        """Get normalized on-demand prices for each provider"""
        all_prices = self.get_t4_prices()
        
        normalized = {}
        for provider, price_info in all_prices.items():
            # Prefer on-demand, fallback to average
            if price_info.get('on_demand'):
                normalized[f"T4 ({provider})"] = price_info['on_demand']
            elif price_info.get('average'):
                normalized[f"T4 ({provider})"] = price_info['average']

        return normalized

    def save_to_json(self, prices: Dict, filename: str = "getdeploying_t4_prices.json"):
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.name,
            "gpu_model": "T4",
            "base_model": self.base_model,
            "fetch_status": "success" if prices else "failed",
            "prices_by_provider": prices,
            "notes": {
                "data_source": self.base_url,
                "pricing_types": ["on_demand", "spot", "reserved"],
                "normalization": "All prices normalized to per-GPU hourly rate"
            }
        }
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"💾 Results saved to: {filename}")


def main():
    print("🚀 GetDeploying T4 GPU Price Aggregator")
    scraper = GetDeployingT4Scraper()
    prices = scraper.get_t4_prices()

    if prices:
        print("\n📊 T4 Prices by Provider:")
        for provider, info in prices.items():
            on_demand = info.get('on_demand', 'N/A')
            spot = info.get('spot', 'N/A')
            print(f"   {provider}: On-Demand: {on_demand}, Spot: {spot}")
    else:
        print("\n❌ No T4 prices found")

    scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
