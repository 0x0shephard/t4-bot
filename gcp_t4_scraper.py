#!/usr/bin/env python3
"""
Google Cloud Platform (GCP) T4 GPU Price Scraper
Extracts T4 pricing from Google Cloud Compute Engine

GCP offers T4 GPUs as accelerators attached to VMs:
- nvidia-tesla-t4: 16GB GDDR6
- Can attach 1-4 T4 GPUs to various machine types

Reference: https://cloud.google.com/compute/gpus-pricing
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import statistics
from typing import Dict, Optional, List


class GCPT4Scraper:
    """Scraper for Google Cloud Platform T4 GPU pricing"""
    
    def __init__(self):
        self.name = "Google Cloud"
        self.base_urls = [
            "https://cloud.google.com/compute/gpus-pricing",
            "https://cloud.google.com/compute/vm-instance-pricing",
        ]
        # Vantage.sh URLs for multiple GCP regions - T4 GPU pricing
        # Note: GCP prices GPUs separately, we look for T4-attached instances
        self.vantage_regions = [
            ("us-central1", "https://instances.vantage.sh/gcp/n1-standard-4?region=us-central1&gpu=nvidia-tesla-t4"),
            ("us-east1", "https://instances.vantage.sh/gcp/n1-standard-4?region=us-east1&gpu=nvidia-tesla-t4"),
            ("us-west1", "https://instances.vantage.sh/gcp/n1-standard-4?region=us-west1&gpu=nvidia-tesla-t4"),
            ("europe-west1", "https://instances.vantage.sh/gcp/n1-standard-4?region=europe-west1&gpu=nvidia-tesla-t4"),
            ("asia-east1", "https://instances.vantage.sh/gcp/n1-standard-4?region=asia-east1&gpu=nvidia-tesla-t4"),
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    
    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices from GCP - combines own scraping with GetDeploying"""
        print(f"🔍 Fetching {self.name} T4 pricing (multi-source)...")
        print("=" * 80)
        
        t4_prices = {}
        all_gcp_prices = []  # Collect all prices for averaging
        
        # Try multiple methods - Vantage multi-region first for volatility
        methods = [
            ("Vantage Multi-Region Pricing", self._try_vantage_multi_region),
            ("GCP GPU Pricing Page Scraping", self._try_pricing_page),
            ("Selenium Scraper", self._try_selenium_scraper),
        ]
        
        for method_name, method_func in methods:
            print(f"\n📋 Method: {method_name}")
            try:
                prices = method_func()
                if prices and self._validate_prices(prices):
                    t4_prices.update(prices)
                    # Extract numeric prices for averaging
                    for variant, price_str in prices.items():
                        price_match = re.search(r'\$([0-9.]+)', price_str)
                        if price_match:
                            all_gcp_prices.append(float(price_match.group(1)))
                    print(f"   ✅ Found {len(prices)} T4 prices!")
                    break
                else:
                    print(f"   ❌ No valid prices found")
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:100]}")
                continue
        
        # Also fetch GetDeploying prices for Google Cloud
        print(f"\n📋 Method: GetDeploying Google Cloud Prices")
        getdeploying_prices = self._get_getdeploying_gcp_prices()
        if getdeploying_prices:
            all_gcp_prices.extend(getdeploying_prices)
            print(f"   ✅ Added {len(getdeploying_prices)} prices from GetDeploying")
        
        # Calculate combined average
        if all_gcp_prices:
            avg_price = statistics.mean(all_gcp_prices)
            t4_prices["T4 Combined Average (GCP)"] = f"${avg_price:.2f}/hr"
            print(f"\n📊 Combined Average: ${avg_price:.2f}/hr (from {len(all_gcp_prices)} price points)")
        
        if not t4_prices:
            print("\n❌ All live methods failed - no fallback data (live data only mode)")
            return {}
        
        print(f"\n✅ Final extraction: {len(t4_prices)} T4 price variants")
        return t4_prices
    
    def _get_getdeploying_gcp_prices(self) -> List[float]:
        """Fetch Google Cloud T4 prices from GetDeploying JSON file or scraper"""
        gcp_prices = []
        
        # Try to read from existing GetDeploying JSON file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        getdeploying_file = os.path.join(script_dir, "getdeploying_t4_prices.json")
        
        try:
            if os.path.exists(getdeploying_file):
                with open(getdeploying_file, 'r') as f:
                    data = json.load(f)
                
                # Look for Google Cloud prices
                prices_by_provider = data.get('prices_by_provider', {})
                google_data = prices_by_provider.get('Google Cloud', {})
                
                if google_data:
                    all_prices = google_data.get('all_prices', [])
                    gcp_prices.extend(all_prices)
                    print(f"      ✓ Loaded {len(all_prices)} Google Cloud prices from GetDeploying")
            else:
                print(f"      ⚠️ GetDeploying file not found, running scraper...")
                # Try to run the GetDeploying scraper
                try:
                    from getdeploying_t4_scraper import GetDeployingT4Scraper
                    scraper = GetDeployingT4Scraper()
                    all_prices = scraper.get_t4_prices()
                    google_data = all_prices.get('Google Cloud', {})
                    if google_data:
                        gcp_prices.extend(google_data.get('all_prices', []))
                except ImportError:
                    print(f"      ⚠️ GetDeploying scraper not available")
                    
        except Exception as e:
            print(f"      ⚠️ Error loading GetDeploying data: {str(e)[:50]}")
        
        return gcp_prices
    
    def _validate_prices(self, prices: Dict[str, str]) -> bool:
        """Validate that prices are in a reasonable range for T4 GPUs (per-GPU)"""
        if not prices:
            return False
        
        for variant, price_str in prices.items():
            if 'Error' in variant:
                continue
            try:
                price_match = re.search(r'([0-9.]+)', price_str)
                if price_match:
                    price = float(price_match.group(1))
                    # Per-GPU T4 pricing should be ~$0.35-0.60/hr
                    if 0.20 < price < 1.50:
                        return True
            except:
                continue
        return False
    
    def _try_vantage_multi_region(self) -> Dict[str, str]:
        """Fetch T4 prices from multiple GCP regions via Vantage.sh for volatility"""
        t4_prices = {}
        
        print(f"    Fetching prices from {len(self.vantage_regions)} GCP regions...")
        
        for region_code, url in self.vantage_regions:
            try:
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text_content = soup.get_text()
                    
                    # Look for T4 GPU pricing patterns
                    # GCP charges for GPU separately, ~$0.35/hr for T4
                    price_patterns = [
                        r'T4[:\s]*\$([0-9]+\.?[0-9]*)',
                        r'tesla.t4[:\s]*\$([0-9]+\.?[0-9]*)',
                        r'GPU[:\s]*\$([0-9]+\.?[0-9]*)',
                        r'\$([0-9]+\.[0-9]+)\s*(?:per\s+hour|/hr|/hour)',
                        r'\$([0-9]+\.[0-9]+)',
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, text_content, re.IGNORECASE)
                        for match in matches:
                            try:
                                price = float(match)
                                # GCP T4 GPU ~$0.35/hr
                                if 0.20 < price < 0.80:
                                    region_name = region_code.replace('-', ' ').title()
                                    variant_name = f"nvidia-tesla-t4 ({region_name})"
                                    t4_prices[variant_name] = f"${price:.2f}/hr"
                                    print(f"      ✓ {region_code}: ${price:.2f}/GPU")
                                    break
                            except ValueError:
                                continue
                        if region_code.replace('-', ' ').title() in str(t4_prices):
                            break
                            
            except Exception as e:
                print(f"      ⚠️ {region_code}: Error - {str(e)[:30]}")
                continue
        
        if t4_prices:
            print(f"    Found prices from {len(t4_prices)} regions")
        
        return t4_prices
    
    def _try_pricing_page(self) -> Dict[str, str]:
        """Scrape GCP pricing pages for T4 prices"""
        t4_prices = {}
        
        for url in self.base_urls:
            try:
                print(f"    Trying: {url}")
                response = requests.get(url, headers=self.headers, timeout=20)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text_content = soup.get_text()
                    
                    print(f"      Content length: {len(text_content)}")
                    
                    # Check for T4 mentions
                    if 'T4' in text_content or 't4' in text_content.lower() or 'Tesla T4' in text_content:
                        print(f"      ✓ Found T4 content")
                        
                        # Extract from tables
                        found_prices = self._extract_from_tables(soup)
                        if found_prices:
                            t4_prices.update(found_prices)
                            return t4_prices
                        
                        # Extract from text patterns
                        found_prices = self._extract_from_text(text_content)
                        if found_prices:
                            t4_prices.update(found_prices)
                            return t4_prices
                    else:
                        print(f"      ⚠️  No T4 content found")
                else:
                    print(f"      Status {response.status_code}")
                    
            except Exception as e:
                print(f"      Error: {str(e)[:50]}...")
                continue
        
        return t4_prices
    
    def _extract_from_tables(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract T4 prices from HTML tables"""
        prices = {}
        
        tables = soup.find_all('table')
        print(f"      Found {len(tables)} tables")
        
        for table in tables:
            table_text = table.get_text()
            
            # Look for T4 mentions
            if 'T4' not in table_text and 't4' not in table_text.lower() and 'tesla-t4' not in table_text.lower():
                continue
            
            print(f"      📋 Processing table with T4 data")
            
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = ' '.join([cell.get_text().strip() for cell in cells])
                
                # Check for T4 rows
                if ('T4' in row_text or 't4' in row_text.lower()) and '$' in row_text:
                    print(f"         Row: {row_text[:150]}")
                    
                    # Extract all prices from the row
                    price_matches = re.findall(r'\$([0-9.]+)', row_text)
                    
                    for price_str in price_matches:
                        try:
                            price = float(price_str)
                            # GCP T4 GPU is ~$0.35/hr
                            if 0.20 < price < 0.80:
                                variant_name = "nvidia-tesla-t4 (Google Cloud)"
                                if variant_name not in prices:
                                    prices[variant_name] = f"${price:.2f}/hr"
                                    print(f"        Table ✓ {variant_name} = ${price:.2f}/hr")
                        except ValueError:
                            continue
        
        return prices
    
    def _extract_from_text(self, text_content: str) -> Dict[str, str]:
        """Extract T4 prices from text content"""
        prices = {}
        
        # GCP pricing patterns for T4
        price_patterns = [
            r'T4[^$]*\$([0-9.]+)',
            r'tesla.t4[^$]*\$([0-9.]+)',
            r'nvidia-t4[^$]*\$([0-9.]+)',
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE | re.DOTALL)
            
            for price_str in matches:
                try:
                    price = float(price_str)
                    
                    # GCP T4 is ~$0.35/hr
                    if 0.20 < price < 0.80:
                        variant_name = "nvidia-tesla-t4 (Google Cloud)"
                        if variant_name not in prices:
                            prices[variant_name] = f"${price:.2f}/hr"
                            print(f"        Pattern ✓ {variant_name} = ${price:.2f}/hr")
                            return prices
                except ValueError:
                    continue
        
        return prices
    
    def _try_selenium_scraper(self) -> Dict[str, str]:
        """Use Selenium to scrape JavaScript-loaded pricing from GCP"""
        t4_prices = {}
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import WebDriverException
            
            print("    Setting up Selenium WebDriver...")
            
            # Configure Chrome options
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Initialize the driver
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                for url in self.base_urls:
                    print(f"    Loading: {url}")
                    driver.get(url)
                    
                    # Wait for page to load
                    time.sleep(5)
                    
                    # Get the page source after JavaScript has loaded
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    text_content = soup.get_text()
                    
                    print(f"    ✓ Page loaded, content length: {len(text_content)}")
                    
                    # Try extraction methods
                    found_prices = self._extract_from_tables(soup)
                    if found_prices:
                        t4_prices.update(found_prices)
                        break
                    
                    found_prices = self._extract_from_text(text_content)
                    if found_prices:
                        t4_prices.update(found_prices)
                        break
                
            finally:
                driver.quit()
                print("    WebDriver closed")
                
        except ImportError:
            print("      ⚠️  Selenium not installed. Run: pip install selenium")
        except WebDriverException as e:
            print(f"      ⚠️  Selenium WebDriver error: {str(e)[:100]}")
        except Exception as e:
            print(f"      ⚠️  Error: {str(e)[:100]}")
        
        return t4_prices
    
    def save_to_json(self, prices: Dict[str, str], filename: str = "gcp_t4_prices.json") -> bool:
        """Save results to a JSON file"""
        try:
            # Extract numeric price
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
                    "gpu_type": "nvidia-tesla-t4",
                    "gpu_model": "NVIDIA T4",
                    "gpu_memory": "16GB GDDR6",
                    "pricing_type": "On-demand GPU accelerator",
                    "source": "https://cloud.google.com/compute/gpus-pricing",
                    "note": "GCP charges for T4 GPUs separately from VM compute costs"
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
    """Main function to run the GCP T4 scraper"""
    print("🚀 Google Cloud Platform T4 GPU Pricing Scraper")
    print("=" * 80)
    print("Note: GCP offers T4 GPUs as accelerators (nvidia-tesla-t4)")
    print("=" * 80)
    
    scraper = GCPT4Scraper()
    
    start_time = time.time()
    prices = scraper.get_t4_prices()
    end_time = time.time()
    
    print(f"\n⏱️  Scraping completed in {end_time - start_time:.2f} seconds")
    
    # Display results
    if prices and 'Error' not in str(prices):
        print(f"\n✅ Successfully extracted {len(prices)} T4 price entries:\n")
        
        for variant, price in sorted(prices.items()):
            print(f"  • {variant:50s} {price}")
        
        # Save results to JSON
        scraper.save_to_json(prices)
    else:
        print("\n❌ No valid pricing data found")


if __name__ == "__main__":
    main()
