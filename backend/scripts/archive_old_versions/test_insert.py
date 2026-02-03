"""Test INSERT result format."""

import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check():
    conn = await asyncpg.connect(DB_URL)
    
    # Create test table
    await conn.execute('DROP TABLE IF EXISTS test_insert')
    await conn.execute('CREATE TABLE test_insert (id int PRIMARY KEY, val text)')
    
    # Insert new row
    result = await conn.execute('INSERT INTO test_insert VALUES (1, \'test\')')
    print(f'New insert result: {repr(result)}')
    
    # Insert with conflict
    result2 = await conn.execute('INSERT INTO test_insert VALUES (1, \'updated\') ON CONFLICT (id) DO UPDATE SET val = EXCLUDED.val')
    print(f'Upsert result: {repr(result2)}')
    
    # Test copy_records_to_table
    await conn.execute('CREATE TEMP TABLE temp_test (id int, val text)')
    records = [(10, 'a'), (11, 'b'), (12, 'c')]
    await conn.copy_records_to_table('temp_test', records=records, columns=['id', 'val'])
    print(f'copy_records_to_table completed')
    
    # Upsert from temp to main
    result3 = await conn.execute('''
        INSERT INTO test_insert (id, val)
        SELECT id, val FROM temp_test
        ON CONFLICT (id) DO UPDATE SET val = EXCLUDED.val
    ''')
    print(f'Batch upsert result: {repr(result3)}')
    
    # Check data
    rows = await conn.fetch('SELECT * FROM test_insert ORDER BY id')
    print(f'Data in table: {[dict(r) for r in rows]}')
    
    await conn.execute('DROP TABLE test_insert')
    await conn.close()


if __name__ == "__main__":
    asyncio.run(check())
