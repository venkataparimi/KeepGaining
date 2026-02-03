import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check a few trades with their P&L calculation
    trades = await pool.fetch('''
        SELECT symbol, entry_premium, exit_premium, pnl_pct, pnl_amount, quantity
        FROM strategy_trades
        ORDER BY trade_date, entry_time
        LIMIT 10
    ''')
    print('Sample trades with P&L:')
    print('Symbol      | Entry   | Exit    | PnL%   | PnL Amt | Qty')
    print('-'*60)
    for t in trades:
        entry = float(t['entry_premium'] or 0)
        exit_p = float(t['exit_premium'] or 0)
        pnl_pct = float(t['pnl_pct'] or 0)
        pnl_amt = t['pnl_amount']
        qty = t['quantity']
        symbol = t['symbol']
        print(f"{symbol:12}| {entry:7.2f} | {exit_p:7.2f} | {pnl_pct:6.2f} | {pnl_amt or 'None':>7} | {qty or 'None'}")
    
    # Check if any have pnl_amount populated
    count_with_pnl = await pool.fetchval("SELECT COUNT(*) FROM strategy_trades WHERE pnl_amount IS NOT NULL")
    print(f"\nTrades with pnl_amount populated: {count_with_pnl}")
    
    await pool.close()

asyncio.run(check())
