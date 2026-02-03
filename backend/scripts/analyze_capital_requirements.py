"""
Capital Requirement Analysis for Morning Momentum Alpha Strategy
Analyzes backtest data to determine capital requirements
"""
import pandas as pd
import glob
from pathlib import Path
from datetime import datetime

def analyze_capital_requirements():
    """Analyze capital requirements from backtest data"""
    
    # Find the most recent backtest CSV
    csv_files = glob.glob('backtest_exit_*.csv')
    if not csv_files:
        print("❌ No backtest CSV files found")
        return
    
    latest_file = max(csv_files, key=lambda x: Path(x).stat().st_mtime)
    print(f"📊 Analyzing: {latest_file}\n")
    
    # Load data
    df = pd.read_csv(latest_file)
    
    # Convert date to datetime
    df['date'] = pd.to_datetime(df['date'])
    
    # Calculate capital required per trade (entry premium × lot size)
    # Assuming we already have option_pnl_amount which is based on lot size
    # Capital required = entry_premium × lot_size
    # We can estimate lot_size from pnl_amount and pnl_pct
    
    df['capital_required'] = df['entry_premium'] * 50  # Conservative estimate: 50 lot size
    
    # Group by date to get daily statistics
    daily_stats = df.groupby('date').agg({
        'capital_required': ['sum', 'max', 'min', 'mean', 'count'],
        'option_pnl_amount': 'sum',
        'option_pnl_pct': 'mean'
    }).round(2)
    
    # Flatten column names
    daily_stats.columns = ['_'.join(col).strip() for col in daily_stats.columns.values]
    daily_stats = daily_stats.rename(columns={
        'capital_required_sum': 'total_capital',
        'capital_required_max': 'max_per_trade',
        'capital_required_min': 'min_per_trade',
        'capital_required_mean': 'avg_per_trade',
        'capital_required_count': 'num_trades',
        'option_pnl_amount_sum': 'daily_pnl',
        'option_pnl_pct_mean': 'avg_pnl_pct'
    })
    
    # Overall statistics
    print("=" * 80)
    print("💰 CAPITAL REQUIREMENT ANALYSIS - Morning Momentum Alpha")
    print("=" * 80)
    print()
    
    # Overall summary
    print("📈 OVERALL STATISTICS (Oct-Dec 2025)")
    print("-" * 80)
    print(f"Total Trading Days:        {len(daily_stats)}")
    print(f"Total Trades:              {df.shape[0]}")
    print(f"Avg Trades per Day:        {df.shape[0] / len(daily_stats):.1f}")
    print()
    
    # Daily capital requirements
    print("💵 DAILY CAPITAL REQUIREMENTS")
    print("-" * 80)
    print(f"Average per Day:           ₹{daily_stats['total_capital'].mean():,.0f}")
    print(f"Maximum (Single Day):      ₹{daily_stats['total_capital'].max():,.0f}")
    print(f"Minimum (Single Day):      ₹{daily_stats['total_capital'].min():,.0f}")
    print(f"Median per Day:            ₹{daily_stats['total_capital'].median():,.0f}")
    print()
    
    # Per trade requirements
    print("📊 PER TRADE CAPITAL")
    print("-" * 80)
    print(f"Average per Trade:         ₹{df['capital_required'].mean():,.0f}")
    print(f"Maximum Single Trade:      ₹{df['capital_required'].max():,.0f}")
    print(f"Minimum Single Trade:      ₹{df['capital_required'].min():,.0f}")
    print()
    
    # Recommended capital
    max_daily = daily_stats['total_capital'].max()
    recommended = max_daily * 1.2  # 20% buffer
    
    print("🎯 RECOMMENDED CAPITAL")
    print("-" * 80)
    print(f"Minimum Required:          ₹{max_daily:,.0f}")
    print(f"Recommended (with 20%):    ₹{recommended:,.0f}")
    print(f"Conservative (with 50%):   ₹{max_daily * 1.5:,.0f}")
    print()
    
    # Top 10 highest capital days
    print("📅 TOP 10 HIGHEST CAPITAL REQUIREMENT DAYS")
    print("-" * 80)
    top_days = daily_stats.nlargest(10, 'total_capital')[['num_trades', 'total_capital', 'daily_pnl']]
    for date, row in top_days.iterrows():
        pnl_color = "🟢" if row['daily_pnl'] >= 0 else "🔴"
        print(f"{date.strftime('%Y-%m-%d')}  |  {int(row['num_trades'])} trades  |  "
              f"₹{row['total_capital']:>10,.0f}  |  {pnl_color} ₹{row['daily_pnl']:>10,.0f}")
    print()
    
    # Monthly breakdown
    df['month'] = df['date'].dt.to_period('M')
    monthly_stats = df.groupby('month').agg({
        'capital_required': ['sum', 'mean', 'max'],
        'date': 'nunique',
        'option_pnl_amount': 'sum'
    }).round(2)
    
    print("📆 MONTHLY BREAKDOWN")
    print("-" * 80)
    print(f"{'Month':<15} {'Days':<8} {'Avg Daily':<15} {'Max Daily':<15} {'Monthly P&L':<15}")
    print("-" * 80)
    
    for month in monthly_stats.index:
        days = monthly_stats.loc[month, ('date', 'nunique')]
        avg_daily = monthly_stats.loc[month, ('capital_required', 'sum')] / days
        max_daily = monthly_stats.loc[month, ('capital_required', 'max')]
        monthly_pnl = monthly_stats.loc[month, ('option_pnl_amount', 'sum')]
        
        print(f"{str(month):<15} {int(days):<8} ₹{avg_daily:>12,.0f}  ₹{max_daily:>12,.0f}  "
              f"₹{monthly_pnl:>12,.0f}")
    
    print()
    
    # Risk analysis
    print("⚠️  RISK CONSIDERATIONS")
    print("-" * 80)
    max_loss_day = daily_stats.nsmallest(1, 'daily_pnl')
    max_loss_amount = max_loss_day['daily_pnl'].values[0]
    max_loss_date = max_loss_day.index[0]
    
    print(f"Worst Day Loss:            ₹{max_loss_amount:,.0f} ({max_loss_date.strftime('%Y-%m-%d')})")
    print(f"Max Drawdown Risk:         ~{abs(max_loss_amount / recommended * 100):.1f}% of recommended capital")
    print()
    
    # Capital efficiency
    total_pnl = df['option_pnl_amount'].sum()
    avg_capital = daily_stats['total_capital'].mean()
    
    print("📈 CAPITAL EFFICIENCY")
    print("-" * 80)
    print(f"Total P&L (3 months):      ₹{total_pnl:,.0f}")
    print(f"Avg Capital Deployed:      ₹{avg_capital:,.0f}")
    print(f"Return on Capital:         {(total_pnl / avg_capital * 100):.1f}%")
    print(f"Monthly Return:            {(total_pnl / avg_capital / 3 * 100):.1f}%")
    print()
    
    print("=" * 80)
    print("✅ Analysis Complete!")
    print("=" * 80)
    print()
    
    # Save detailed report
    output_file = f"capital_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    daily_stats.to_csv(output_file)
    print(f"📄 Detailed daily report saved: {output_file}")
    
    return daily_stats

if __name__ == "__main__":
    analyze_capital_requirements()
