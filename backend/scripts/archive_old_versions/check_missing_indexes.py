"""Check for missing indexes on remaining tables."""
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check_missing():
    conn = await asyncpg.connect(DB_URL)
    
    # Count total indexes
    total = await conn.fetchval("SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'")
    print(f'Total indexes in database: {total}')
    
    # Get all existing indexes
    indexes = await conn.fetch('''
        SELECT tablename, indexname, indexdef
        FROM pg_indexes WHERE schemaname = 'public'
    ''')
    
    # Table sizes vs index count
    print('\n=== TABLE SIZES vs INDEX COUNT ===')
    stats = await conn.fetch('''
        SELECT 
            t.table_name,
            pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) as size,
            (SELECT count(*) FROM pg_indexes i WHERE i.tablename = t.table_name) as idx_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY pg_total_relation_size(quote_ident(t.table_name)) DESC
        LIMIT 15
    ''')
    for s in stats:
        name = s['table_name']
        size = s['size']
        cnt = s['idx_count']
        print(f"  {name:30} {size:>10}  ({cnt} indexes)")
    
    await conn.close()

asyncio.run(check_missing())
