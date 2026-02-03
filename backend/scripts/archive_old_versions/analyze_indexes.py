"""
Comprehensive index analysis and creation for KeepGaining database.
Analyzes all tables and creates indexes needed for:
- UI queries (fast lookups, filtering, sorting)
- Strategy execution (real-time data access)
- Backtesting (historical data scans)
- Backfill validation (coverage checks)
"""
import asyncio
import asyncpg
import time

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def analyze_and_create_indexes():
    conn = await asyncpg.connect(DB_URL)
    
    print('=' * 80)
    print('DATABASE INDEX ANALYSIS')
    print('=' * 80)
    
    # Get all tables with their sizes
    tables = await conn.fetch('''
        SELECT 
            t.table_name,
            pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) as total_size,
            pg_total_relation_size(quote_ident(t.table_name)) as size_bytes,
            (SELECT count(*) FROM information_schema.columns c WHERE c.table_name = t.table_name) as col_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' 
        AND t.table_type = 'BASE TABLE'
        ORDER BY pg_total_relation_size(quote_ident(t.table_name)) DESC
    ''')
    
    print('\n=== TABLE SIZES ===')
    for t in tables:
        print(f"  {t['table_name']}: {t['total_size']} ({t['col_count']} columns)")
    
    # Get existing indexes
    print('\n=== EXISTING INDEXES ===')
    indexes = await conn.fetch('''
        SELECT 
            tablename,
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    ''')
    
    current_table = None
    for idx in indexes:
        if idx['tablename'] != current_table:
            current_table = idx['tablename']
            print(f"\n{current_table}:")
        print(f"  - {idx['indexname']}")
    
    # Analyze what indexes are needed
    print('\n' + '=' * 80)
    print('INDEX RECOMMENDATIONS')
    print('=' * 80)
    
    # Define recommended indexes for each use case
    recommended_indexes = [
        # instrument_master - Core lookup table
        ('instrument_master', 'idx_im_trading_symbol', 'trading_symbol', 'Symbol lookups'),
        ('instrument_master', 'idx_im_underlying', 'underlying', 'Filter by underlying'),
        ('instrument_master', 'idx_im_type', 'instrument_type', 'Filter by type (CE/PE/FUTURES)'),
        ('instrument_master', 'idx_im_segment', 'segment', 'Filter by segment'),
        ('instrument_master', 'idx_im_type_underlying', '(instrument_type, underlying)', 'Combined filter'),
        
        # option_master - Options chain queries
        ('option_master', 'idx_om_expiry', 'expiry', 'Filter by expiry date'),
        ('option_master', 'idx_om_strike', 'strike', 'Filter by strike price'),
        ('option_master', 'idx_om_underlying_expiry', '(underlying, expiry)', 'Options chain lookup'),
        ('option_master', 'idx_om_underlying_expiry_strike', '(underlying, expiry, strike)', 'Full chain lookup'),
        
        # future_master - Futures queries
        ('future_master', 'idx_fm_expiry', 'expiry', 'Filter by expiry'),
        ('future_master', 'idx_fm_underlying', 'underlying', 'Filter by underlying'),
        
        # indicator_data - Technical analysis
        ('indicator_data', 'idx_ind_instrument_time', '(instrument_id, timestamp)', 'Indicator time series'),
        ('indicator_data', 'idx_ind_indicator_name', 'indicator_name', 'Filter by indicator type'),
        
        # orders - Order management UI
        ('orders', 'idx_ord_status', 'status', 'Filter by status'),
        ('orders', 'idx_ord_created', 'created_at', 'Sort by time'),
        ('orders', 'idx_ord_strategy', 'strategy_id', 'Filter by strategy'),
        
        # trades - Trade history
        ('trades', 'idx_trd_timestamp', 'timestamp', 'Sort by time'),
        ('trades', 'idx_trd_strategy', 'strategy_id', 'Filter by strategy'),
        
        # positions - Current positions
        ('positions', 'idx_pos_instrument', 'instrument_id', 'Lookup by instrument'),
        ('positions', 'idx_pos_strategy', 'strategy_id', 'Filter by strategy'),
        
        # signal_log - Strategy signals
        ('signal_log', 'idx_sig_timestamp', 'timestamp', 'Sort by time'),
        ('signal_log', 'idx_sig_strategy', 'strategy_id', 'Filter by strategy'),
        
        # daily_pnl - PnL reports
        ('daily_pnl', 'idx_pnl_date', 'date', 'Filter by date'),
        ('daily_pnl', 'idx_pnl_strategy', 'strategy_id', 'Filter by strategy'),
        
        # option_chain_snapshot - Options data
        ('option_chain_snapshot', 'idx_ocs_timestamp', 'timestamp', 'Time series queries'),
        ('option_chain_snapshot', 'idx_ocs_underlying', 'underlying', 'Filter by underlying'),
        
        # option_greeks - Greeks analysis
        ('option_greeks', 'idx_og_instrument_time', '(instrument_id, timestamp)', 'Greeks time series'),
        
        # expiry_calendar - Expiry lookups
        ('expiry_calendar', 'idx_ec_expiry_date', 'expiry_date', 'Find expiries'),
        ('expiry_calendar', 'idx_ec_underlying', 'underlying', 'Filter by underlying'),
    ]
    
    # Check which indexes already exist
    existing_idx_names = {idx['indexname'] for idx in indexes}
    
    indexes_to_create = []
    for table, idx_name, columns, purpose in recommended_indexes:
        if idx_name not in existing_idx_names:
            # Check if table exists
            table_exists = await conn.fetchval('''
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = $1 AND table_schema = 'public'
                )
            ''', table)
            
            if table_exists:
                indexes_to_create.append((table, idx_name, columns, purpose))
                print(f"  MISSING: {idx_name} ON {table}({columns}) - {purpose}")
            else:
                print(f"  SKIP: Table {table} does not exist")
        else:
            print(f"  EXISTS: {idx_name}")
    
    # Create missing indexes
    if indexes_to_create:
        print('\n' + '=' * 80)
        print('CREATING MISSING INDEXES')
        print('=' * 80)
        
        for table, idx_name, columns, purpose in indexes_to_create:
            try:
                # Check if columns exist
                if columns.startswith('('):
                    # Multi-column index
                    col_list = columns.strip('()').split(', ')
                else:
                    col_list = [columns]
                
                cols_exist = True
                for col in col_list:
                    col_exists = await conn.fetchval('''
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = $1 AND column_name = $2
                        )
                    ''', table, col.strip())
                    if not col_exists:
                        print(f"  SKIP {idx_name}: Column {col} does not exist in {table}")
                        cols_exist = False
                        break
                
                if cols_exist:
                    start = time.time()
                    sql = f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} {columns if columns.startswith("(") else "(" + columns + ")"}'
                    await conn.execute(sql)
                    elapsed = time.time() - start
                    print(f"  CREATED: {idx_name} in {elapsed:.2f}s")
            except Exception as e:
                print(f"  ERROR creating {idx_name}: {e}")
    
    # Check materialized views
    print('\n' + '=' * 80)
    print('MATERIALIZED VIEWS')
    print('=' * 80)
    
    matviews = await conn.fetch('''
        SELECT matviewname, pg_size_pretty(pg_total_relation_size(quote_ident(matviewname))) as size
        FROM pg_matviews
        WHERE schemaname = 'public'
    ''')
    
    if matviews:
        for mv in matviews:
            print(f"  {mv['matviewname']}: {mv['size']}")
    else:
        print("  No materialized views found")
    
    await conn.close()
    print('\n' + '=' * 80)
    print('DONE')
    print('=' * 80)

if __name__ == '__main__':
    asyncio.run(analyze_and_create_indexes())
