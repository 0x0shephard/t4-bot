#!/usr/bin/env python3
"""
Cerebrium T4 GPU Price Scraper
Extracts T4 pricing from Cerebrium AI serverless platform

Cerebrium offers T4 GPUs at $0.000164/second = ~$0.59/hr

Reference: https://www.cerebrium.ai/
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import statistics
from typing import Dict, List, Optional


class CerebriumT4Scraper:
    """Scraper for Cerebrium T4 GPU pricing"""
    
    def __init__(self):
        self.name = "Cerebrium"
        self.base_url = "https://www.cerebrium.ai/"
        self.pricing_url = "https://www.cerebrium.ai/pricing"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    
    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices - combines own scraping with GetDeploying"""
        print(f"🔍 Fetching {self.name} T4 pricing...")
        print("=" * 80)
        
        t4_prices = {}
        all_numeric_prices = []
        sources_used = []
        
        # Method 1: Try direct website scraping
        print("\n📋 Method 1: Cerebrium Website Scraping")
        try:
            website_prices = self._try_website_scraping()
            if website_prices:
                t4_prices.update(website_prices)
                sources_used.append("Website")
                for variant, price_str in website_prices.items():
                    price_match = re.search(r'\$([0-9.]+)', price_str)
                    if price_match:
                        all_numeric_prices.append(float(price_match.group(1)))
                print(f"   ✅ Found {len(website_prices)} prices from website!")
            else:
                print(f"   ❌ No prices from website scraping")
        except Exception as e:
            print(f"   ⚠️  Website Error: {str(e)[:100]}")
        
        # Method 2: Try Selenium if needed
        if not t4_prices:
            print("\n📋 Method 2: Selenium Scraping")
            try:
                selenium_prices = self._try_selenium_scraper()
                if selenium_prices:
                    t4_prices.update(selenium_prices)
                    sources_used.append("Selenium")
                    for variant, price_str in selenium_prices.items():
                        price_match = re.search(r'\$([0-9.]+)', price_str)
                        if price_match:
                            all_numeric_prices.append(float(price_match.group(1)))
                    print(f"   ✅ Found {len(selenium_prices)} prices from Selenium!")
            except Exception as e:
                print(f"   ⚠️  Selenium Error: {str(e)[:100]}")
        
        # Method 3: GetDeploying prices
        print("\n📋 Method 3: GetDeploying Cerebrium Prices")
        getdeploying_prices = self._get_getdeploying_prices()
        if getdeploying_prices:
            all_numeric_prices.extend(getdeploying_prices)
            sources_used.append("GetDeploying")
            print(f"   ✅ Added {len(getdeploying_prices)} prices from GetDeploying")
        
        # Calculate combined average
        if all_numeric_prices:
            avg_price = statistics.mean(all_numeric_prices)
            t4_prices["T4 Combined Average (Cerebrium)"] = f"${avg_price:.2f}/hr"
            print(f"\n📊 Combined Average: ${avg_price:.2f}/hr (from {len(all_numeric_prices)} price points)")
        
        if not t4_prices and not getdeploying_prices:
            print("\n❌ All methods failed")
            return {}
        
        print(f"\n📊 Sources used: {', '.join(sources_used)}")
        print(f"✅ Final extraction: {len(t4_prices)} T4 price variants")
        return t4_prices
    
    def _try_website_scraping(self) -> Dict[str, str]:
        """Try to scrape pricing from Cerebrium website"""
        t4_prices = {}
        
        try:
            response = requests.get(self.pricing_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text_content = soup.get_text()
                
                # Look for T4 pricing patterns
                # Cerebrium uses per-second pricing: $0.000164/sec = $0.59/hr
                price_patterns = [
                    r'T4[:\s]+\$([0-9.]+)',
                    r'Tesla\s+T4[:\s]+\$([0-9.]+)',
                    r'\$([0-9.]+)\s*(?:per\s+hour|/hr|/hour).*?T4',
                    r'T4.*?\$([0-9.]+)\s*(?:per\s+hour|/hr|/hour)',
                    r'\$0\.000164',  # Per-second rate
                    r'\$0\.59',  # Hourly rate
                ]
                
                for pattern in price_patterns:
                    matches = re.findall(pattern, text_content, re.IGNORECASE)
                    for match in matches:
                        try:
                            if isinstance(match, str):
                                price = float(match.replace('$', ''))
                            else:
                                price = float(match)
                            # Convert per-second to per-hour if needed
                            if price < 0.01:  # Per-second pricing
                                price = price * 3600
                            if 0.20 < price < 2.00:
                                t4_prices["T4 (Cerebrium)"] = f"${price:.2f}/hr"
                                print(f"      ✓ Found T4: ${price:.2f}/hr")
                                return t4_prices
                        except ValueError:
                            continue
                
                # Check if known price appears
                if '$0.59' in text_content or '0.59' in text_content:
                    t4_prices["T4 (Cerebrium)"] = "$0.59/hr"
                    print(f"      ✓ Found T4: $0.59/hr")
                elif '$0.000164' in text_content:
                    t4_prices["T4 (Cerebrium)"] = "$0.59/hr"
                    print(f"      ✓ Found T4: $0.59/hr (converted from per-second)")
                    
        except Exception as e:
            print(f"      ⚠️ Error: {str(e)[:50]}")
        
        return t4_prices
    
    def _try_selenium_scraper(self) -> Dict[str, str]:
        """Use Selenium for JavaScript-rendered content"""
        t4_prices = {}
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                driver.get(self.pricing_url)
                time.sleep(3)
                
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                text_content = soup.get_text()
                
                # Look for T4 pricing
                if '$0.59' in text_content:
                    t4_prices["T4 (Cerebrium)"] = "$0.59/hr"
                    print(f"      ✓ Selenium found T4: $0.59/hr")
                elif '$0.000164' in text_content:
                    t4_prices["T4 (Cerebrium)"] = "$0.59/hr"
                    print(f"      ✓ Selenium found T4: $0.59/hr (per-second)")
                    
            finally:
                driver.quit()
                
        except ImportError:
            print("      ⚠️ Selenium not installed")
        except Exception as e:
            print(f"      ⚠️ Selenium Error: {str(e)[:50]}")
        
        return t4_prices
    
    def _get_getdeploying_prices(self) -> List[float]:
        """Fetch Cerebrium T4 prices from GetDeploying JSON file"""
        prices = []
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        getdeploying_file = os.path.join(script_dir, "getdeploying_t4_prices.json")
        
        try:
            if os.path.exists(getdeploying_file):
                with open(getdeploying_file, 'r') as f:
                    data = json.load(f)
                
                prices_by_provider = data.get('prices_by_provider', {})
                provider_data = prices_by_provider.get('Cerebrium', {})
                
                if provider_data:
                    all_prices = provider_data.get('all_prices', [])
                    prices.extend(all_prices)
                    print(f"      ✓ Loaded {len(all_prices)} Cerebrium prices from GetDeploying")
            else:
                print(f"      ⚠️ GetDeploying file not found")
                    
        except Exception as e:
            print(f"      ⚠️ Error loading GetDeploying data: {str(e)[:50]}")
        
        return prices
    
    def save_to_json(self, prices: Dict[str, str], filename: str = "cerebrium_t4_prices.json") -> bool:
        """Save results to a JSON file"""
        try:
            price_value = 0.0
            if prices:
                for variant, price_str in prices.items():
                    price_match = re.search(r'\$([0-9.]+)', price_str)
                    if price_match:
                        price_value = float(price_match.group(1))
                        break
            
            output_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "provider": self.name,
                "fetch_status": "success" if prices else "failed",
                "prices": prices if prices else {},
                "notes": {
                    "gpu_model": "NVIDIA T4",
                    "gpu_memory": "16GB GDDR6",
                    "pricing_type": "Serverless (pay-per-second)",
                    "source": self.pricing_url
                }
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Results saved to: {filename}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving to file: {str(e)}")
            return False


def main():
    """Main function to run the Cerebrium T4 scraper"""
    print("🚀 Cerebrium T4 GPU Pricing Scraper")
    print("=" * 80)
    
    scraper = CerebriumT4Scraper()
    
    start_time = time.time()
    prices = scraper.get_t4_prices()
    end_time = time.time()
    
    print(f"\n⏱️  Scraping completed in {end_time - start_time:.2f} seconds")
    
    if prices:
        print(f"\n✅ Successfully extracted {len(prices)} T4 price entries:\n")
        for variant, price in sorted(prices.items()):
            print(f"  • {variant:50s} {price}")
        scraper.save_to_json(prices)
    else:
        print("\n❌ No valid pricing data found")
        scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
