import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check date range
    date_range = await pool.fetchrow('''
        SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date, COUNT(*) as total
        FROM strategy_trades
    ''')
    print(f"Date Range: {date_range['min_date']} to {date_range['max_date']}")
    print(f"Total Trades: {date_range['total']}")
    
    # Check unique symbols
    symbols = await pool.fetch('SELECT DISTINCT symbol FROM strategy_trades ORDER BY symbol')
    print(f"\nUnique Symbols ({len(symbols)}):")
    symbol_list = [s['symbol'] for s in symbols]
    for i in range(0, len(symbol_list), 10):
        print(", ".join(symbol_list[i:i+10]))
    
    # Trades per month
    monthly = await pool.fetch('''
        SELECT DATE_TRUNC('month', trade_date) as month, COUNT(*) as trades
        FROM strategy_trades
        GROUP BY DATE_TRUNC('month', trade_date)
        ORDER BY month DESC
    ''')
    print('\nTrades per Month:')
    for m in monthly:
        print(f"  {m['month'].strftime('%Y-%m')}: {m['trades']} trades")
    
    await pool.close()

asyncio.run(check())
