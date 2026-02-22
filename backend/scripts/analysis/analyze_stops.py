import pandas as pd

df = pd.read_csv('backtest_exit_1430_1766207841.csv')

# Filter for Stop Loss trades
stops = df[df['exit_reason'] == 'Stop (-40%)'].copy()

print('Trades that hit 40% Stop Loss:')
print('=' * 100)
print(stops[['date', 'stock', 'option_type', 'strike', 'option_pnl_pct', 'max_profit_pct', 'max_loss_pct']].to_string(index=False))

print('\n' + '=' * 100)
print(f'Total Stop Loss Trades: {len(stops)}')
print(f'Average Final Loss: {stops["option_pnl_pct"].mean():.1f}%')
print(f'Average Max Profit Reached Before Stop: {stops["max_profit_pct"].mean():.1f}%')
print(f'Average Max Loss: {stops["max_loss_pct"].mean():.1f}%')

# Check if any would have recovered
print('\n' + '=' * 100)
print('KEY INSIGHT: Did they recover after hitting stop?')
print('(If max_profit_pct > 0, the trade was profitable at some point)')
recovered = stops[stops['max_profit_pct'] > 10]
print(f'\nTrades that reached >10% profit before hitting -40% stop: {len(recovered)}')
if len(recovered) > 0:
    print(recovered[['date', 'stock', 'max_profit_pct', 'option_pnl_pct']].to_string(index=False))
