-- ============================================
-- T4 Index & Provider Prices Tables
-- ============================================
-- Run this in Supabase SQL Editor to create the necessary tables
-- for tracking T4 GPU pricing index.

-- 1. Create the main index table
CREATE TABLE IF NOT EXISTS t4_index_prices (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    index_price DECIMAL(10, 4) NOT NULL,
    hyperscaler_component DECIMAL(10, 4),
    neocloud_component DECIMAL(10, 4),
    hyperscaler_count INTEGER,
    neocloud_count INTEGER,
    metadata JSONB
);

-- Indexes for main table
CREATE INDEX IF NOT EXISTS idx_t4_index_prices_timestamp ON t4_index_prices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_t4_index_prices_created_at ON t4_index_prices(created_at DESC);

-- RLS for main table
ALTER TABLE t4_index_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access on t4_index_prices" ON t4_index_prices
    FOR SELECT USING (true);

CREATE POLICY "Allow service role insert on t4_index_prices" ON t4_index_prices
    FOR INSERT WITH CHECK (true);

-- Grant permissions
GRANT SELECT ON t4_index_prices TO anon;
GRANT SELECT ON t4_index_prices TO authenticated;
GRANT ALL ON t4_index_prices TO service_role;


-- 2. Create the provider prices table (breakdown)
CREATE TABLE IF NOT EXISTS t4_provider_prices (
    id BIGSERIAL PRIMARY KEY,
    
    -- Link to the parent index record
    index_id UUID REFERENCES t4_index_prices(id) ON DELETE CASCADE,
    
    -- Timestamp (matches parent index timestamp)
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Provider identification
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK (provider_type IN ('hyperscaler', 'neocloud')),
    
    -- Pricing data
    original_price DECIMAL(10, 4) NOT NULL,
    effective_price DECIMAL(10, 4) NOT NULL,
    discount_rate DECIMAL(5, 4),
    
    -- Weight data
    relative_weight DECIMAL(6, 4) NOT NULL,
    absolute_weight DECIMAL(6, 4) NOT NULL,
    weighted_contribution DECIMAL(10, 4) NOT NULL,
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for provider table
CREATE INDEX IF NOT EXISTS idx_t4_provider_prices_timestamp ON t4_provider_prices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_t4_provider_prices_provider ON t4_provider_prices(provider_name);
CREATE INDEX IF NOT EXISTS idx_t4_provider_prices_index_id ON t4_provider_prices(index_id);
CREATE INDEX IF NOT EXISTS idx_t4_provider_prices_provider_time ON t4_provider_prices(provider_name, timestamp DESC);

-- RLS for provider table
ALTER TABLE t4_provider_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access on t4_provider_prices" ON t4_provider_prices
    FOR SELECT USING (true);

CREATE POLICY "Allow service role full access on t4_provider_prices" ON t4_provider_prices
    FOR ALL USING (auth.role() = 'service_role');

-- Grant permissions
GRANT SELECT ON t4_provider_prices TO anon;
GRANT SELECT ON t4_provider_prices TO authenticated;
GRANT ALL ON t4_provider_prices TO service_role;

-- 3. Create Views for Analysis

-- View: Latest prices for all T4 providers
CREATE OR REPLACE VIEW v_latest_t4_provider_prices AS
SELECT DISTINCT ON (provider_name)
    provider_name,
    provider_type,
    original_price,
    effective_price,
    weighted_contribution,
    timestamp
FROM t4_provider_prices
ORDER BY provider_name, timestamp DESC;

-- View: T4 Price History (Daily Average)
CREATE OR REPLACE VIEW v_t4_price_history AS
SELECT 
    provider_name,
    DATE(timestamp) as date,
    AVG(effective_price) as avg_price,
    COUNT(*) as records
FROM t4_provider_prices
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY provider_name, DATE(timestamp)
ORDER BY provider_name, date DESC;
