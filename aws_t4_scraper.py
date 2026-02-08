#!/usr/bin/env python3
"""
AWS G4dn Instance (T4 GPU) Price Scraper
Extracts T4 pricing from AWS EC2 G4dn instances

AWS offers T4 GPUs in G4dn instances:
- g4dn.xlarge: 1 x T4 GPU (16GB)
- g4dn.2xlarge: 1 x T4 GPU
- g4dn.4xlarge: 1 x T4 GPU
- g4dn.8xlarge: 1 x T4 GPU
- g4dn.12xlarge: 4 x T4 GPUs
- g4dn.16xlarge: 1 x T4 GPU
- g4dn.metal: 8 x T4 GPUs

Data Sources:
- Vantage.sh API (JSON) - Primary (derived from AWS pricing data)
- Vantage.sh Multi-Region Scraping - Secondary
- Both sources are combined and averaged

Reference: https://aws.amazon.com/ec2/instance-types/g4/
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import statistics
from typing import Dict, List, Optional


class AWST4Scraper:
    """Scraper for AWS G4dn T4 GPU instance pricing"""
    
    def __init__(self):
        self.name = "AWS"
        self.base_url = "https://aws.amazon.com/ec2/instance-types/g4/"
        # Vantage.sh API endpoint (returns JSON with AWS pricing data)
        self.vantage_api_url = "https://instances.vantage.sh/aws/ec2/instances.json"
        # Vantage.sh URLs for multiple regions - G4dn instances have T4 GPUs
        self.vantage_regions = [
            ("us-east-1", "https://instances.vantage.sh/aws/ec2/g4dn.xlarge?region=us-east-1"),
            ("us-east-2", "https://instances.vantage.sh/aws/ec2/g4dn.xlarge?region=us-east-2"),
            ("us-west-2", "https://instances.vantage.sh/aws/ec2/g4dn.xlarge?region=us-west-2"),
            ("eu-west-1", "https://instances.vantage.sh/aws/ec2/g4dn.xlarge?region=eu-west-1"),
            ("ap-northeast-1", "https://instances.vantage.sh/aws/ec2/g4dn.xlarge?region=ap-northeast-1"),
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/html,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    
    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices - BOTH Vantage API AND web scraping combined + GetDeploying"""
        print(f"🔍 Fetching {self.name} G4dn T4 pricing (multi-source)...")
        print("=" * 80)
        
        all_prices = {}
        all_numeric_prices = []  # Collect all prices for combined averaging
        sources_used = []
        
        # Try BOTH methods and combine results
        print("\n📋 Method 1: Vantage.sh API (JSON - derived from AWS pricing)")
        try:
            api_prices = self._try_vantage_api()
            if api_prices and self._validate_prices(api_prices):
                all_prices.update(api_prices)
                sources_used.append("Vantage API")
                # Extract numeric prices
                for variant, price_str in api_prices.items():
                    price_match = re.search(r'\$([0-9.]+)', price_str)
                    if price_match:
                        all_numeric_prices.append(float(price_match.group(1)))
                print(f"   ✅ Found {len(api_prices)} prices from Vantage API!")
            else:
                print(f"   ❌ No valid prices from Vantage API")
        except Exception as e:
            print(f"   ⚠️  Vantage API Error: {str(e)[:100]}")
        
        print("\n📋 Method 2: Vantage Multi-Region Web Scraping")
        try:
            vantage_prices = self._try_vantage_multi_region()
            if vantage_prices and self._validate_prices(vantage_prices):
                all_prices.update(vantage_prices)
                sources_used.append("Vantage Web")
                # Extract numeric prices
                for variant, price_str in vantage_prices.items():
                    price_match = re.search(r'\$([0-9.]+)', price_str)
                    if price_match:
                        all_numeric_prices.append(float(price_match.group(1)))
                print(f"   ✅ Found {len(vantage_prices)} prices from Vantage Web!")
            else:
                print(f"   ❌ No valid prices from Vantage Web")
        except Exception as e:
            print(f"   ⚠️  Vantage Web Error: {str(e)[:100]}")
        
        # If both failed, try Selenium as last resort
        if not all_prices:
            print("\n📋 Method 3: Selenium Scraper (Fallback)")
            try:
                selenium_prices = self._try_selenium_scraper()
                if selenium_prices and self._validate_prices(selenium_prices):
                    all_prices.update(selenium_prices)
                    sources_used.append("Selenium")
                    for variant, price_str in selenium_prices.items():
                        price_match = re.search(r'\$([0-9.]+)', price_str)
                        if price_match:
                            all_numeric_prices.append(float(price_match.group(1)))
                    print(f"   ✅ Found {len(selenium_prices)} prices from Selenium!")
            except Exception as e:
                print(f"   ⚠️  Selenium Error: {str(e)[:100]}")
        
        # Also fetch GetDeploying prices for AWS
        print("\n📋 Method 4: GetDeploying AWS Prices")
        getdeploying_prices = self._get_getdeploying_aws_prices()
        if getdeploying_prices:
            all_numeric_prices.extend(getdeploying_prices)
            sources_used.append("GetDeploying")
            print(f"   ✅ Added {len(getdeploying_prices)} prices from GetDeploying")
        
        if not all_prices and not getdeploying_prices:
            print("\n❌ All live methods failed - no fallback data (live data only mode)")
            return {}
        
        print(f"\n📊 Sources used: {', '.join(sources_used)}")
        
        # Normalize and average prices from all sources (including GetDeploying)
        normalized_prices = self._normalize_and_average_prices(all_prices, sources_used, all_numeric_prices)
        
        print(f"\n✅ Final extraction: Combined price from {len(sources_used)} sources")
        return normalized_prices
    
    def _get_getdeploying_aws_prices(self) -> List[float]:
        """Fetch AWS T4 prices from GetDeploying JSON file"""
        aws_prices = []
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        getdeploying_file = os.path.join(script_dir, "getdeploying_t4_prices.json")
        
        try:
            if os.path.exists(getdeploying_file):
                with open(getdeploying_file, 'r') as f:
                    data = json.load(f)
                
                prices_by_provider = data.get('prices_by_provider', {})
                aws_data = prices_by_provider.get('AWS', {})
                
                if aws_data:
                    all_prices = aws_data.get('all_prices', [])
                    aws_prices.extend(all_prices)
                    print(f"      ✓ Loaded {len(all_prices)} AWS prices from GetDeploying")
            else:
                print(f"      ⚠️ GetDeploying file not found")
                    
        except Exception as e:
            print(f"      ⚠️ Error loading GetDeploying data: {str(e)[:50]}")
        
        return aws_prices
    
    def _validate_prices(self, prices: Dict[str, str]) -> bool:
        """Validate that prices are in a reasonable range for T4 GPUs"""
        if not prices:
            return False
        
        for variant, price_str in prices.items():
            if 'Error' in variant:
                continue
            try:
                price_match = re.search(r'\$?([0-9.]+)', str(price_str))
                if price_match:
                    price = float(price_match.group(1))
                    # T4 pricing should be reasonable (~$0.35-1.50/GPU/hr)
                    if 0.20 < price < 2.00:
                        return True
            except:
                continue
        return False
    
    def _try_vantage_api(self) -> Dict[str, str]:
        """Fetch T4 prices from Vantage.sh JSON API (derived from AWS pricing data)"""
        t4_prices = {}
        
        print(f"    Fetching prices from Vantage.sh API (JSON)...")
        
        try:
            response = requests.get(self.vantage_api_url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                try:
                    instances = response.json()
                    print(f"      ✓ API returned {len(instances)} instances")
                    
                    # Filter for g4dn instances
                    g4dn_instances = [i for i in instances if i.get('name', '').startswith('g4dn')]
                    print(f"      ✓ Found {len(g4dn_instances)} G4dn instances")
                    
                    for instance in g4dn_instances:
                        instance_name = instance.get('name', '')
                        
                        # Get pricing - try different region keys
                        pricing = instance.get('pricing', {})
                        
                        # Try to get US East pricing
                        regions_to_try = ['us-east-1', 'us-east-2', 'us-west-2']
                        
                        for region in regions_to_try:
                            region_pricing = pricing.get(region, {})
                            linux_pricing = region_pricing.get('linux', {})
                            on_demand = linux_pricing.get('ondemand', 0)
                            
                            if on_demand and on_demand > 0:
                                price = float(on_demand)
                                
                                # Get GPU count for normalization
                                gpu_count = instance.get('GPU', 1)
                                if gpu_count == 0:
                                    gpu_count = 1
                                
                                per_gpu_price = price / gpu_count
                                
                                # Validate price range
                                if 0.20 < per_gpu_price < 2.00:
                                    region_name = region.replace('-', ' ').title()
                                    variant_name = f"{instance_name} API ({region_name})"
                                    t4_prices[variant_name] = f"${per_gpu_price:.4f}/hr"
                                    print(f"        ✓ API {instance_name} ({region}): ${price:.2f}/instance → ${per_gpu_price:.4f}/GPU")
                                    break
                    
                except json.JSONDecodeError as e:
                    print(f"      ⚠️ JSON decode error: {str(e)[:50]}")
            else:
                print(f"      Status: {response.status_code}")
                
        except Exception as e:
            print(f"      Error: {str(e)[:50]}")
        
        if t4_prices:
            print(f"    Found {len(t4_prices)} prices from Vantage API")
        
        return t4_prices
    
    def _try_vantage_multi_region(self) -> Dict[str, str]:
        """Fetch T4 prices from multiple AWS regions via Vantage.sh web scraping"""
        t4_prices = {}
        
        print(f"    Fetching prices from {len(self.vantage_regions)} AWS regions (web)...")
        
        for region_code, url in self.vantage_regions:
            try:
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text_content = soup.get_text()
                    
                    # Look for pricing patterns
                    price_patterns = [
                        r'\$([0-9]+\.?[0-9]*)\s*(?:per\s+hour|/hr|/hour)',
                        r'On.?Demand[:\s]+\$([0-9]+\.?[0-9]*)',
                        r'hourly[:\s]+\$([0-9]+\.?[0-9]*)',
                        r'\$([0-9]+\.[0-9]+)',
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, text_content, re.IGNORECASE)
                        for match in matches:
                            try:
                                price = float(match)
                                # g4dn.xlarge has 1 T4 GPU, price ~$0.50-0.60/hr
                                if 0.30 < price < 1.50:
                                    region_name = region_code.replace('-', ' ').title()
                                    variant_name = f"g4dn.xlarge Web ({region_name})"
                                    t4_prices[variant_name] = f"${price:.2f}/hr"
                                    print(f"      ✓ Web {region_code}: ${price:.2f}/GPU")
                                    break
                            except ValueError:
                                continue
                        if region_code.replace('-', ' ').title() in str(t4_prices):
                            break
                            
            except Exception as e:
                print(f"      ⚠️ {region_code}: Error - {str(e)[:30]}")
                continue
        
        if t4_prices:
            print(f"    Found prices from {len(t4_prices)} regions via web")
        
        return t4_prices
    
    def _try_selenium_scraper(self) -> Dict[str, str]:
        """Use Selenium to scrape JavaScript-loaded pricing from AWS"""
        t4_prices = {}
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import WebDriverException
            
            print("    Setting up Selenium WebDriver...")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                vantage_url = "https://instances.vantage.sh/aws/ec2/g4dn.xlarge"
                print(f"    Loading: {vantage_url}")
                driver.get(vantage_url)
                
                print("    Waiting for dynamic content to load...")
                time.sleep(5)
                
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                text_content = soup.get_text()
                
                print(f"    ✓ Page loaded, content length: {len(text_content)}")
                
                price_patterns = [
                    r'\$([0-9]+\.[0-9]+)\s*(?:per\s+hour|/hr|/hour)',
                    r'On.?Demand[:\s]+\$([0-9]+\.[0-9]+)',
                    r'\$([0-9]+\.[0-9]+)',
                ]
                
                for pattern in price_patterns:
                    matches = re.findall(pattern, text_content, re.IGNORECASE)
                    for match in matches:
                        try:
                            price = float(match)
                            if 0.30 < price < 1.50:
                                t4_prices["g4dn.xlarge Selenium"] = f"${price:.2f}/hr"
                                print(f"      ✓ Selenium: ${price:.2f}/GPU")
                                break
                        except ValueError:
                            continue
                    if t4_prices:
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
    
    def _normalize_and_average_prices(self, prices: Dict[str, str], sources: List[str], all_numeric_prices: List[float] = None) -> Dict[str, str]:
        """
        Normalize and average prices from BOTH API and web scraping sources + GetDeploying.
        G4dn.xlarge has 1 T4 GPU, so instance price = per-GPU price.
        """
        if not prices and not all_numeric_prices:
            return {}
        
        print("\n   📊 Normalizing and averaging prices from all sources...")
        
        # Use pre-collected numeric prices if available (includes GetDeploying)
        if all_numeric_prices:
            final_avg = statistics.mean(all_numeric_prices)
            print(f"\n   ✅ COMBINED AVERAGE from {len(all_numeric_prices)} price points: ${final_avg:.2f}/GPU")
            print(f"   📊 Range: ${min(all_numeric_prices):.2f} - ${max(all_numeric_prices):.2f}")
            
            return {
                'g4dn.xlarge (AWS)': f"${final_avg:.2f}/hr",
                'T4 Combined Average (AWS)': f"${final_avg:.2f}/hr"
            }
        
        # Fallback to original logic if no pre-collected prices
        api_prices = []
        web_prices = []
        other_prices = []
        
        for variant, price_str in prices.items():
            if 'Error' in variant:
                continue
            
            try:
                price_match = re.search(r'\$([0-9.]+)', price_str)
                if price_match:
                    price = float(price_match.group(1))
                    
                    if 'API' in variant:
                        api_prices.append(price)
                    elif 'Web' in variant:
                        web_prices.append(price)
                    else:
                        other_prices.append(price)
                    
            except (ValueError, TypeError):
                continue
        
        all_prices = api_prices + web_prices + other_prices
        if all_prices:
            final_avg = statistics.mean(all_prices)
            print(f"\n   ✅ COMBINED AVERAGE: ${final_avg:.2f}/GPU")
            
            return {
                'g4dn.xlarge (AWS)': f"${final_avg:.2f}/hr"
            }
        
        return {}
    
    def save_to_json(self, prices: Dict[str, str], filename: str = "aws_t4_prices.json") -> bool:
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
                "data_sources": ["Vantage.sh API (JSON)", "Vantage.sh Web Scraping"],
                "prices": prices if prices else {},
                "notes": {
                    "instance_type": "g4dn.xlarge",
                    "gpu_model": "NVIDIA T4",
                    "gpu_memory": "16GB GDDR6",
                    "gpu_count_per_instance": 1,
                    "pricing_type": "On-Demand",
                    "methodology": "Average of Vantage API (JSON) and Vantage Web (multi-region) prices",
                    "source": "https://aws.amazon.com/ec2/instance-types/g4/"
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
    """Main function to run the AWS G4dn T4 scraper"""
    print("🚀 AWS G4dn T4 GPU Pricing Scraper")
    print("=" * 80)
    print("Note: AWS offers T4 GPUs in G4dn instances (1-8 x T4)")
    print("Sources: Vantage API (JSON) + Vantage Web (multi-region)")
    print("=" * 80)
    
    scraper = AWST4Scraper()
    
    start_time = time.time()
    prices = scraper.get_t4_prices()
    end_time = time.time()
    
    print(f"\n⏱️  Scraping completed in {end_time - start_time:.2f} seconds")
    
    if prices and 'Error' not in str(prices):
        print(f"\n✅ Successfully extracted T4 price:\n")
        
        for variant, price in sorted(prices.items()):
            print(f"  • {variant:50s} {price}")
        
        scraper.save_to_json(prices)
    else:
        print("\n❌ No valid pricing data found")


if __name__ == "__main__":
    main()
