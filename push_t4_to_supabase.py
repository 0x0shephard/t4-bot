#!/usr/bin/env python3
"""
Push T4 Weighted Index to Supabase

This script reads the T4 weighted index from t4_weighted_index.json
and pushes it to the Supabase t4_index_prices and t4_provider_prices tables.

Usage:
    python push_t4_to_supabase.py

Environment Variables Required (set in .env file):
    SUPABASE_URL - Your Supabase project URL
    SUPABASE_SERVICE_KEY - Your Supabase service role key (for write access)
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_index_data(filepath: str = "t4_weighted_index.json") -> Optional[Dict]:
    """Load T4 weighted index data from JSON file"""
    try:
        # Check current directory first, then fallback to script directory
        paths = [filepath, os.path.join(os.path.dirname(__file__), filepath)]
        for p in paths:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        print(f"[ERROR] {filepath} not found!")
        return None
    except Exception as e:
        print(f"[ERROR] Error loading JSON: {e}")
        return None


def push_to_supabase(index_data: Dict) -> bool:
    """Push T4 data to Supabase"""
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if not supabase_url or not supabase_key:
        print("[ERROR] Supabase credentials not found!")
        print("Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file")
        return False
    
    try:
        from supabase import create_client, Client
    except ImportError:
        print("[ERROR] supabase-py library not installed!")
        print("Install it with: pip install supabase")
        return False
    
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # 0. Validate Price against Previous Entry
        new_price = index_data.get("final_index_price")
        
        print("\n[VALIDATION] Checking price against previous records...")
        response = supabase.table('t4_index_prices')\
            .select('index_price')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
            
        if response.data and len(response.data) > 0:
            prev_price = float(response.data[0]['index_price'])
            lower_bound = prev_price * 0.80
            upper_bound = prev_price * 1.20 # 20% tolerance
            
            print(f"   Previous Price: ${prev_price:.2f}")
            print(f"   New Price:      ${new_price:.2f}")
            print(f"   Allowed Range:  ${lower_bound:.2f} - ${upper_bound:.2f}")
            
            if not (lower_bound <= new_price <= upper_bound):
                print(f"\n❌ [ERROR] Price validation failed!")
                print(f"   Price change exceeds 20% tolerance.")
                print("   Push ABORTED to prevent bad data.")
                return False
            else:
                print("   ✅ Price within ±20% range. Proceeding.")
        else:
            print("   ⚠️ No previous data found. Allowing initial push.")

        # 1. Insert Main Index Record
        insert_data = {
            "timestamp": index_data.get("timestamp"),
            "index_price": new_price,
            "hyperscaler_component": index_data.get("components", {}).get("hyperscaler"),
            "neocloud_component": index_data.get("components", {}).get("neocloud"),
            "metadata": {
                "details": index_data.get("details", {})
            }
        }
        
        print(f"\n[PUSH] Pushing T4 Index to Supabase...")
        print(f"   Index Price: ${insert_data['index_price']:.2f}/hr")
        
        response = supabase.table('t4_index_prices').insert(insert_data).execute()
        
        if not response.data:
            print("[ERROR] Failed to insert index record")
            return False
            
        index_id = response.data[0]['id']
        print(f"[SUCCESS] Index Record ID: {index_id}")
        
        # 2. Insert Provider Records
        provider_records = []
        details = index_data.get("details", {})
        
        # Hyperscalers
        for name, data in details.get("hyperscalers", {}).items():
            provider_records.append({
                "index_id": index_id,
                "timestamp": insert_data["timestamp"],
                "provider_name": name,
                "provider_type": "hyperscaler",
                "original_price": data.get("original"),
                "effective_price": data.get("effective"),
                "discount_rate": (data.get("original") - data.get("discounted")) / data.get("original") if data.get("original") else 0,
                "relative_weight": data.get("weight"), # From config
                "absolute_weight": data.get("weight") * 0.65, # Approx
                "weighted_contribution": data.get("contribution")
            })
            
        # Neoclouds
        for name, data in details.get("neoclouds", {}).items():
            # Neocloud data structure is simpler: price, raw_weight
            provider_records.append({
                "index_id": index_id,
                "timestamp": insert_data["timestamp"],
                "provider_name": name,
                "provider_type": "neocloud",
                "original_price": data.get("price"),
                "effective_price": data.get("price"),
                "discount_rate": 0,
                "relative_weight": data.get("raw_weight"),
                "absolute_weight": data.get("raw_weight") * 0.35, # Approx
                "weighted_contribution": 0 # We didn't save this explicitly in all cases, but logic suggests price * weight * total_weight
            })
            
        if provider_records:
            print(f"[PUSH] Pushing {len(provider_records)} provider records...")
            supabase.table('t4_provider_prices').insert(provider_records).execute()
            print("[SUCCESS] Provider records pushed")
            
        return True
            
    except Exception as e:
        print(f"[ERROR] Exception pushing to Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 T4 Index -> Supabase Uploader")
    index_data = load_index_data()
    
    if index_data:
        push_to_supabase(index_data)
    else:
        print("❌ Could not load index data")

if __name__ == "__main__":
    main()
