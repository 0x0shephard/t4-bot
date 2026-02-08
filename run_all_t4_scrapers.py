#!/usr/bin/env python3
"""
T4 GPU Price Scraper Orchestrator
Runs all working T4 GPU scrapers and combines the results.
Uses direct imports for reliability.

Confirmed Working Providers (11):
1. AWS ($1.01/hr) - Combined
2. Azure ($0.55/hr) - Combined
3. GCP ($0.55/hr) - Combined
4. Vast.ai ($0.12/hr) - Direct
5. Tencent Cloud ($0.20/hr) - Direct
6. NeevCloud ($0.29/hr) - Direct
7. Paperspace ($0.51/hr) - Direct
8. Thunder Compute ($0.27/hr) - Website + GetDeploying
9. Cerebrium ($0.59/hr) - Website + GetDeploying
10. Alibaba Cloud ($0.74/hr) - GetDeploying
11. Replicate ($0.81/hr) - Website + GetDeploying

Aggregator:
- GetDeploying
"""

import os
import json
import time
import sys
import traceback

# Ensure current directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import all scrapers
try:
    from aws_t4_scraper import AWST4Scraper
    from azure_t4_scraper import AzureT4Scraper
    from gcp_t4_scraper import GCPT4Scraper
    from vastai_t4_scraper import VastAIT4Scraper
    from tencent_t4_scraper import TencentT4Scraper
    from neevcloud_t4_scraper import NeevCloudT4Scraper
    from paperspace_t4_scraper import PaperspaceT4Scraper
    from thundercompute_t4_scraper import ThunderComputeT4Scraper
    from cerebrium_t4_scraper import CerebriumT4Scraper
    from alibaba_t4_scraper import AlibabaT4Scraper
    from replicate_t4_scraper import ReplicateT4Scraper
    from getdeploying_t4_scraper import GetDeployingT4Scraper
except ImportError as e:
    print(f"❌ Error importing scrapers: {e}")
    traceback.print_exc()
    print(f"Current sys.path: {sys.path}")
    print("Ensure all scraper files are in the same directory.")
    sys.exit(1)

def run_scraper_class(name, scraper_class, filename):
    """Run a specific scraper class and return the result"""
    print(f"\n{'='*80}")
    print(f"🔄 Running {name} Scraper...")
    print(f"{'='*80}")
    
    try:
        start_time = time.time()
        
        # Instantiate and run
        scraper = scraper_class()
        prices = scraper.get_t4_prices()
        
        # Save results
        if hasattr(scraper, 'save_to_json'):
            scraper.save_to_json(prices, filename)
        else:
            # Fallback save if method missing
            with open(filename, 'w') as f:
                json.dump({"prices": prices}, f, indent=2)
                
        duration = time.time() - start_time
        
        if prices:
            price_str = list(prices.values())[0] if isinstance(prices, dict) else "N/A"
            count = len(prices)
            print(f"✅ {name} finished in {duration:.2f}s | Found {count} prices")
            return {"status": "success", "price": price_str, "count": count}
        else:
            print(f"❌ {name} finished in {duration:.2f}s | No prices found")
            return {"status": "failed", "reason": "No prices found"}
            
    except Exception as e:
        print(f"❌ Error running {name}: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "reason": str(e)}

def main():
    print("🚀 Starting T4 GPU Price Collection (11 Providers)")
    print("=" * 80)
    
    results = {}
    
    # 1. Run Aggregator First
    print("\n📦 Step 1: Running Aggregator (GetDeploying) First...")
    agg_result = run_scraper_class("GetDeploying", GetDeployingT4Scraper, "getdeploying_t4_prices.json")
    results["GetDeploying"] = agg_result
    
    # 2. Run Individual Scrapers
    print("\n📦 Step 2: Running Individual Provider Scrapers...")
    
    scrapers = [
        ("AWS", AWST4Scraper, "aws_t4_prices.json"),
        ("GCP", GCPT4Scraper, "gcp_t4_prices.json"),
        ("Azure", AzureT4Scraper, "azure_t4_prices.json"),
        ("Vast.ai", VastAIT4Scraper, "vastai_t4_prices.json"),
        ("Tencent Cloud", TencentT4Scraper, "tencent_t4_prices.json"),
        ("NeevCloud", NeevCloudT4Scraper, "neevcloud_t4_prices.json"),
        ("Paperspace", PaperspaceT4Scraper, "paperspace_t4_prices.json"),
        ("Thunder Compute", ThunderComputeT4Scraper, "thundercompute_t4_prices.json"),
        ("Cerebrium", CerebriumT4Scraper, "cerebrium_t4_prices.json"),
        ("Alibaba Cloud", AlibabaT4Scraper, "alibaba_t4_prices.json"),
        ("Replicate", ReplicateT4Scraper, "replicate_t4_prices.json"),
    ]
    
    for name, cls, outfile in scrapers:
        results[name] = run_scraper_class(name, cls, outfile)
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 Final T4 Pricing Summary")
    print(f"{'='*80}")
    print(f"{'Provider':<20} | {'Status':<10} | {'Price/Msg':<20} | {'Count'}")
    print("-" * 65)
    
    success_count = 0
    ordered_keys = ["Vast.ai", "Tencent Cloud", "Thunder Compute", "NeevCloud", "Paperspace", 
                   "Azure", "GCP", "Cerebrium", "Alibaba Cloud", "Replicate", "AWS", "GetDeploying"]
    
    for name in ordered_keys:
        if name in results:
            res = results[name]
            status = res.get('status', 'unknown')
            
            if status == 'success':
                price = res.get('price', 'N/A')
                count = res.get('count', 0)
                status_icon = "✅"
                success_count += 1
            else:
                price = res.get('reason', 'Failed')
                count = 0
                status_icon = "❌"
            
            print(f"{status_icon} {name:<18} | {status:<10} | {price:<20} | {count}")
    
    print("-" * 65)
    print(f"Total Successful Providers: {success_count}/{len(scrapers) + 1}")
    
    # Compile combined JSON
    combined_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_providers": len(results),
            "successful_providers": success_count,
        },
        "prices": {}
    }
    
    for name, res in results.items():
        if res.get('status') == 'success':
            combined_data["prices"][name] = res.get('price')
            
    with open("t4_combined_prices.json", "w") as f:
        json.dump(combined_data, f, indent=2)
        print("\n💾 Saved combined results to t4_combined_prices.json")

if __name__ == "__main__":
    main()
