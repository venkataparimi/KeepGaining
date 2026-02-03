import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Count trades
    count = await pool.fetchval('SELECT COUNT(*) FROM strategy_trades')
    print(f'Total trades in database: {count}')
    
    # Summary
    summary = await pool.fetchrow("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winners,
            ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
            ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl_pct,
            SUM(pnl_amount) as total_pnl_amt,
            SUM(CASE WHEN pnl_amount > 0 THEN pnl_amount ELSE 0 END) as gross_profit,
            SUM(CASE WHEN pnl_amount < 0 THEN pnl_amount ELSE 0 END) as gross_loss
        FROM strategy_trades
    """)
    print(f"Winners: {summary['winners']}, Win Rate: {summary['win_rate']}%")
    print(f"Total P&L %: {summary['total_pnl_pct']}%")
    print(f"Total P&L ₹: {summary['total_pnl_amt']:,.0f}")
    print(f"Gross Profit: {summary['gross_profit']:,.0f}")
    print(f"Gross Loss:   {summary['gross_loss']:,.0f}")
    
    # By sector
    sectors = await pool.fetch("""
        SELECT sector, COUNT(*) as trades, 
               ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
               SUM(pnl_amount) as sector_pnl
        FROM strategy_trades
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY sector_pnl DESC
        LIMIT 10
    """)
    print()
    print('Top sectors by P&L:')
    for s in sectors:
        print(f"  {s['sector']}: {s['trades']} trades, {s['win_rate']}% win, P&L: ₹{s['sector_pnl']:,.0f}")
    
    await pool.close()

asyncio.run(check())
