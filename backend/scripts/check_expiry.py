import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check if expiry_date is populated for today's run
    trades = await pool.fetch('''
        SELECT trade_date, symbol, expiry_date 
        FROM strategy_trades
        WHERE created_at >= NOW() - INTERVAL '10 minutes'
        LIMIT 5
    ''')
    print(f'Found {len(trades)} recent trades')
    print('Recent trades with expiry date:')
    for t in trades:
        print(f"{t['trade_date']}: {t['symbol']} -> Expiry: {t['expiry_date']}")
    
    await pool.close()

asyncio.run(check())
