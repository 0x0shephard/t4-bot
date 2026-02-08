#!/usr/bin/env python3
"""
Azure NCasT4_v3 Instance (T4 GPU) Price Scraper
Extracts T4 pricing from Microsoft Azure VM pricing

Azure offers T4 GPUs in NCasT4_v3 series VMs:
- Standard_NC4as_T4_v3: 1 x T4 GPU, 4 vCPUs
- Standard_NC8as_T4_v3: 1 x T4 GPU, 8 vCPUs
- Standard_NC16as_T4_v3: 1 x T4 GPU, 16 vCPUs
- Standard_NC64as_T4_v3: 4 x T4 GPUs, 64 vCPUs

Sources:
- Azure Retail Prices API (primary - direct)
- Vantage.sh (secondary)
- Selenium fallback

Reference: https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import statistics
from typing import Dict, Optional, List


class AzureT4Scraper:
    """Scraper for Azure NCasT4_v3 instance pricing"""
    
    def __init__(self):
        self.name = "Azure"
        self.base_url = "https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/"
        self.api_url = "https://prices.azure.com/api/retail/prices"
        self.vantage_regions = [
            ("eastus", "https://instances.vantage.sh/azure/nc4as-t4-v3?region=eastus"),
            ("westus2", "https://instances.vantage.sh/azure/nc4as-t4-v3?region=westus2"),
            ("centralus", "https://instances.vantage.sh/azure/nc4as-t4-v3?region=centralus"),
            ("northeurope", "https://instances.vantage.sh/azure/nc4as-t4-v3?region=northeurope"),
            ("westeurope", "https://instances.vantage.sh/azure/nc4as-t4-v3?region=westeurope"),
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    
    def get_t4_prices(self) -> Dict[str, str]:
        """Main method to extract T4 prices - Azure API AND Vantage + GetDeploying"""
        print(f"🔍 Fetching {self.name} NCasT4_v3 pricing (multi-source)...")
        print("=" * 80)
        
        all_prices = {}
        all_numeric_prices = []  # Collect all prices for combined averaging
        sources_used = []
        
        # Try ALL methods and combine results
        methods = [
            ("Azure Retail Prices API (Direct)", self._try_azure_pricing_api),
            ("Vantage Multi-Region Pricing", self._try_vantage_multi_region),
            ("Azure Pricing Page (Selenium)", self._try_azure_pricing_selenium),
        ]
        
        for method_name, method_func in methods:
            print(f"\n📋 Method: {method_name}")
            try:
                prices = method_func()
                if prices and self._validate_prices(prices):
                    all_prices.update(prices)
                    sources_used.append(method_name)
                    # Extract numeric prices
                    for variant, price_str in prices.items():
                        price_match = re.search(r'\$([0-9.]+)', price_str)
                        if price_match:
                            all_numeric_prices.append(float(price_match.group(1)))
                    print(f"   ✅ Found {len(prices)} T4 prices!")
                    break  # Use first successful method
                else:
                    print(f"   ❌ No valid prices found")
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:100]}")
                continue
        
        # Also fetch GetDeploying prices for Azure
        print(f"\n📋 Method: GetDeploying Azure Prices")
        getdeploying_prices = self._get_getdeploying_azure_prices()
        if getdeploying_prices:
            all_numeric_prices.extend(getdeploying_prices)
            sources_used.append("GetDeploying")
            print(f"   ✅ Added {len(getdeploying_prices)} prices from GetDeploying")
        
        if not all_prices and not getdeploying_prices:
            print("\n❌ All live methods failed - no fallback data (live data only mode)")
            return {}
        
        print(f"\n📊 Sources used: {', '.join(sources_used)}")
        
        # Normalize to per-GPU pricing (including GetDeploying)
        normalized_prices = self._normalize_prices(all_prices, all_numeric_prices)
        
        print(f"\n✅ Final extraction: {len(normalized_prices)} T4 price variants")
        return normalized_prices
    
    def _get_getdeploying_azure_prices(self) -> List[float]:
        """Fetch Azure T4 prices from GetDeploying JSON file"""
        azure_prices = []
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        getdeploying_file = os.path.join(script_dir, "getdeploying_t4_prices.json")
        
        try:
            if os.path.exists(getdeploying_file):
                with open(getdeploying_file, 'r') as f:
                    data = json.load(f)
                
                prices_by_provider = data.get('prices_by_provider', {})
                azure_data = prices_by_provider.get('Azure', {})
                
                if azure_data:
                    all_prices = azure_data.get('all_prices', [])
                    azure_prices.extend(all_prices)
                    print(f"      ✓ Loaded {len(all_prices)} Azure prices from GetDeploying")
            else:
                print(f"      ⚠️ GetDeploying file not found")
                    
        except Exception as e:
            print(f"      ⚠️ Error loading GetDeploying data: {str(e)[:50]}")
        
        return azure_prices
    
    def _validate_prices(self, prices: Dict[str, str]) -> bool:
        """Validate that prices are in a reasonable range for T4 GPUs"""
        if not prices:
            return False
        
        for variant, price_str in prices.items():
            if 'Error' in variant or 'error' in variant:
                continue
            try:
                price_match = re.search(r'\$?([0-9.]+)', str(price_str))
                if price_match:
                    price = float(price_match.group(1))
                    # T4 pricing should be reasonable (~$0.30-1.00/GPU/hr)
                    if 0.20 < price < 1.50:
                        return True
            except:
                continue
        return False
    
    def _try_azure_pricing_api(self) -> Dict[str, str]:
        """Use Azure Retail Prices API directly for multi-region pricing"""
        t4_prices = {}
        us_region_prices = []
        
        try:
            # Filter queries for NCasT4_v3 instances
            filter_queries = [
                "armSkuName eq 'Standard_NC4as_T4_v3' and priceType eq 'Consumption'",
                "contains(armSkuName, 'NC') and contains(armSkuName, 'T4') and priceType eq 'Consumption'",
                "contains(productName, 'NCas T4') and priceType eq 'Consumption'",
            ]
            
            print(f"    Trying Azure Retail Prices API (Direct)...")
            items = []
            
            for filter_query in filter_queries:
                api_url = f"{self.api_url}?$filter={filter_query}"
                print(f"    Filter: {filter_query[:60]}...")
                
                response = requests.get(api_url, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('Items', [])
                    
                    if items:
                        print(f"      ✓ API returned {len(items)} pricing items")
                        break
            
            if not items:
                print("      No items found")
                return t4_prices
            
            for item in items:
                sku_name = item.get('armSkuName', '')
                region = item.get('armRegionName', '')
                unit_price = item.get('unitPrice', 0)
                product_name = item.get('productName', '')
                
                # Filter for Linux VMs only, exclude Spot/Low Priority
                if 'Windows' in product_name or 'Spot' in product_name or 'Low Priority' in product_name:
                    continue
                
                # NC4as_T4_v3 has 1 T4 GPU
                if ('T4' in sku_name or 'NC4as' in sku_name or 'NC8as' in sku_name or 'NC16as' in sku_name) and unit_price > 0:
                    # Determine GPU count
                    gpu_count = 1
                    if 'NC64as' in sku_name:
                        gpu_count = 4
                    
                    per_gpu_price = unit_price / gpu_count
                    
                    region_display = region.replace('eastus', 'East US').replace('westus', 'West US')
                    region_display = region_display.replace('centralus', 'Central US')
                    
                    # Validate price range for T4
                    if 0.20 < per_gpu_price < 1.50:
                        # Collect US region prices
                        if region and ('us' in region.lower() or 'central' in region.lower()):
                            us_region_prices.append({
                                'price': per_gpu_price,
                                'region': region,
                                'region_display': region_display,
                                'sku': sku_name,
                            })
                            print(f"        ✓ API {region} ({sku_name}): ${unit_price:.2f}/instance → ${per_gpu_price:.2f}/GPU")
                        else:
                            variant_name = f"NCasT4_v3 API ({region_display})"
                            t4_prices[variant_name] = f"${per_gpu_price:.2f}/hr"
            
            # Average US region prices
            if us_region_prices:
                avg_price = sum(p['price'] for p in us_region_prices) / len(us_region_prices)
                t4_prices['NCasT4_v3 API (US Avg)'] = f"${avg_price:.2f}/hr"
                print(f"\n      ✅ Averaged {len(us_region_prices)} US API prices: ${avg_price:.2f}/GPU")
                
                # Add a few individual region prices
                for p in us_region_prices[:3]:
                    variant_name = f"NCasT4_v3 API ({p['region_display']})"
                    t4_prices[variant_name] = f"${p['price']:.2f}/hr"
                    
        except Exception as e:
            print(f"      Error: {str(e)[:80]}...")
        
        return t4_prices
    
    def _try_vantage_multi_region(self) -> Dict[str, str]:
        """Fetch T4 prices from Vantage.sh for Azure"""
        t4_prices = {}
        
        print(f"    Fetching prices from {len(self.vantage_regions)} Azure regions via Vantage...")
        
        for region_code, url in self.vantage_regions:
            try:
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text_content = soup.get_text()
                    
                    price_patterns = [
                        r'\$([0-9]+\.?[0-9]*)\s*(?:per\s+hour|/hr|/hour)',
                        r'On.?Demand[:\s]+\$([0-9]+\.?[0-9]*)',
                        r'Pay as you go[:\s]+\$([0-9]+\.?[0-9]*)',
                        r'\$([0-9]+\.[0-9]+)',
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, text_content, re.IGNORECASE)
                        for match in matches:
                            try:
                                price = float(match)
                                # NC4as_T4_v3 has 1 T4 GPU, instance price ~$0.50-0.60/hr
                                if 0.30 < price < 1.00:
                                    region_name = region_code.replace('eastus', 'East US').replace('westus2', 'West US 2')
                                    variant_name = f"NCasT4_v3 Vantage ({region_name})"
                                    t4_prices[variant_name] = f"${price:.2f}/hr"
                                    print(f"      ✓ Vantage {region_code}: ${price:.2f}/GPU")
                                    break
                            except ValueError:
                                continue
                        if any(region_code in k for k in t4_prices.keys()):
                            break
                            
            except Exception as e:
                print(f"      ⚠️ {region_code}: Error - {str(e)[:30]}")
                continue
        
        if t4_prices:
            print(f"    Found {len(t4_prices)} prices via Vantage")
        
        return t4_prices
    
    def _try_azure_pricing_selenium(self) -> Dict[str, str]:
        """Use Selenium to scrape Azure pricing page directly"""
        t4_prices = {}
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            print("    Setting up Selenium WebDriver for Azure...")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                # Try Vantage.sh with Selenium
                vantage_url = "https://instances.vantage.sh/azure/nc4as-t4-v3"
                print(f"    Loading: {vantage_url}")
                driver.get(vantage_url)
                
                print("    Waiting for dynamic content to load...")
                time.sleep(5)
                
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                text_content = soup.get_text()
                
                print(f"    ✓ Page loaded, content length: {len(text_content)}")
                
                # Look for pricing in tables or text
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
                            if 0.30 < price < 1.00:
                                t4_prices["NCasT4_v3 (Azure Selenium)"] = f"${price:.2f}/hr"
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
            print("      ⚠️  Selenium not installed")
        except Exception as e:
            print(f"      ⚠️  Error: {str(e)[:100]}")
        
        return t4_prices
    
    def _normalize_prices(self, prices: Dict[str, str], all_numeric_prices: List[float] = None) -> Dict[str, str]:
        """Normalize prices and average across all sources including GetDeploying"""
        if not prices and not all_numeric_prices:
            return {}
        
        print("\n   📊 Normalizing Azure NCasT4_v3 pricing...")
        
        # Use pre-collected numeric prices if available (includes GetDeploying)
        if all_numeric_prices:
            avg_per_gpu = statistics.mean(all_numeric_prices)
            min_price = min(all_numeric_prices)
            max_price = max(all_numeric_prices)
            
            print(f"\n   ✅ Averaged {len(all_numeric_prices)} prices → ${avg_per_gpu:.2f}/GPU")
            print(f"   📊 Price range: ${min_price:.2f} - ${max_price:.2f}/GPU (volatility: ${max_price - min_price:.2f})")
            
            return {
                'NCasT4_v3 (Azure)': f"${avg_per_gpu:.2f}/hr",
                'T4 Combined Average (Azure)': f"${avg_per_gpu:.2f}/hr"
            }
        
        # Fallback to original logic
        per_gpu_prices = []
        
        for variant, price_str in prices.items():
            if 'Error' in variant or 'error' in variant:
                continue
            
            try:
                price_match = re.search(r'\$([0-9.]+)', price_str)
                if price_match:
                    price = float(price_match.group(1))
                    per_gpu_prices.append(price)
                    print(f"      {variant}: ${price:.2f}/hr")
                    
            except (ValueError, TypeError):
                continue
        
        if per_gpu_prices:
            avg_per_gpu = statistics.mean(per_gpu_prices)
            print(f"\n   ✅ Averaged {len(per_gpu_prices)} prices → ${avg_per_gpu:.2f}/GPU")
            
            return {
                'NCasT4_v3 (Azure)': f"${avg_per_gpu:.2f}/hr"
            }
        
        return {}
    
    def save_to_json(self, prices: Dict[str, str], filename: str = "azure_t4_prices.json") -> bool:
        """Save results to a JSON file"""
        try:
            has_error = not prices or any("error" in str(v).lower() for v in prices.values())
            
            price_value = 0.0
            if not has_error:
                for variant, price_str in prices.items():
                    price_match = re.search(r'\$([0-9.]+)', price_str)
                    if price_match:
                        price_value = float(price_match.group(1))
                        break
            
            output_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "provider": self.name,
                "fetch_status": "failed" if has_error else "success",
                "data_sources": ["Azure Retail Prices API", "Vantage.sh", "Azure Pricing Page"],
                "prices": prices if prices else {},
                "notes": {
                    "instance_type": "Standard_NC4as_T4_v3",
                    "gpu_model": "NVIDIA T4",
                    "gpu_memory": "16GB GDDR6",
                    "gpu_count_per_instance": 1,
                    "pricing_type": "On-Demand (Linux)",
                    "source": "https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/"
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
    """Main function to run the Azure NCasT4_v3 scraper"""
    print("🚀 Azure NCasT4_v3 T4 GPU Pricing Scraper")
    print("=" * 80)
    print("Note: Azure offers T4 GPUs in NCasT4_v3 instances (1-4 x T4)")
    print("Sources: Azure Retail API + Vantage.sh + Azure Pricing Page")
    print("=" * 80)
    
    scraper = AzureT4Scraper()
    
    start_time = time.time()
    prices = scraper.get_t4_prices()
    end_time = time.time()
    
    print(f"\n⏱️  Scraping completed in {end_time - start_time:.2f} seconds")
    
    if prices and 'error' not in str(prices).lower():
        print(f"\n✅ Successfully extracted {len(prices)} T4 price entries:\n")
        
        for variant, price in sorted(prices.items()):
            print(f"  • {variant:50s} {price}")
        
        scraper.save_to_json(prices)
    else:
        print("\n❌ No valid pricing data found")
        scraper.save_to_json(prices)


if __name__ == "__main__":
    main()
