import pandas as pd

df = pd.read_csv('backtest_exit_1430_1766207841.csv')

# Filter for Time Stop trades that lost money
time_stops = df[df['exit_reason'] == 'Time Stop (14:30PM)'].copy()
time_stop_losses = time_stops[time_stops['option_pnl_pct'] < 0]

print('Time Stop Losses (Exited at 2:30 PM with a loss):')
print('=' * 100)
print(time_stop_losses[['date', 'stock', 'option_type', 'option_pnl_pct', 'max_profit_pct', 'max_loss_pct']].to_string(index=False))

print('\n' + '=' * 100)
print(f'Total Time Stop Losses: {len(time_stop_losses)} out of {len(time_stops)} time stops')
print(f'Average Loss at 2:30 PM: {time_stop_losses["option_pnl_pct"].mean():.1f}%')
print(f'Average Max Profit These Trades Reached: {time_stop_losses["max_profit_pct"].mean():.1f}%')

# Key insight: How many were close to profit?
near_breakeven = time_stop_losses[(time_stop_losses['option_pnl_pct'] > -10) & (time_stop_losses['max_profit_pct'] > 20)]
print(f'\nTrades that reached >20% profit but closed with <10% loss: {len(near_breakeven)}')
if len(near_breakeven) > 0:
    print('These might have recovered if held till 3:30 PM:')
    print(near_breakeven[['date', 'stock', 'max_profit_pct', 'option_pnl_pct']].to_string(index=False))
