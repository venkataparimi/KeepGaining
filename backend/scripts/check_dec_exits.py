import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Get exit reason breakdown
    exit_reasons = await pool.fetch('''
        SELECT exit_reason, COUNT(*) as count,
               SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winners,
               ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl_pct
        FROM strategy_trades
        WHERE trade_date >= '2025-12-01'
        GROUP BY exit_reason
        ORDER BY count DESC
    ''')
    
    print('Exit Reason Breakdown for December:')
    print('=' * 80)
    for r in exit_reasons:
        print(f"{r['exit_reason']:30} | Trades: {r['count']:3} | Winners: {r['winners']:3} | Avg P&L: {r['avg_pnl_pct']:+.1f}%")
    
    # Get all losing trades with their details
    losses = await pool.fetch('''
        SELECT trade_date, symbol, option_type, exit_reason, pnl_pct, pnl_amount
        FROM strategy_trades
        WHERE trade_date >= '2025-12-01' AND pnl_pct < 0
        ORDER BY pnl_pct ASC
        LIMIT 20
    ''')
    
    print('\n' + '=' * 80)
    print('Top 20 Losing Trades:')
    print('=' * 80)
    for l in losses:
        print(f"{l['trade_date']} | {l['symbol']:12} {l['option_type']} | {l['exit_reason']:25} | {l['pnl_pct']:+6.1f}% | Rs {l['pnl_amount']:,.0f}")
    
    await pool.close()

asyncio.run(check())
