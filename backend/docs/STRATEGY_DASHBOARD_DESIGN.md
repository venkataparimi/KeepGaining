# Morning Momentum Alpha - Premium Strategy Dashboard

## 🎨 Expert Design Features

### Glassmorphic UI Design
- **Dark gradient background**: Slate-950 → Blue-950 → Slate-950
- **Glass cards**: Frosted glass effect with backdrop blur
- **Smooth animations**: 300ms transitions on all interactive elements
- **Gradient accents**: Color-coded mode indicators
- **Micro-interactions**: Hover states, pulse animations, smooth transitions

### Mode Control System

#### 3 Operating Modes

1. **🔴 Live Trading** (Green)
   - Real money trades
   - Requires sufficient funds
   - Auto-switches to Paper if funds insufficient
   - Gradient: Green-500 → Emerald-600

2. **📝 Paper Trading** (Blue)
   - Simulated trades in live market
   - No capital required
   - Tracks performance as if real
   - Gradient: Blue-500 → Cyan-600

3. **⏸️ Stopped** (Gray)
   - Strategy paused
   - No trades executed
   - Preserves current state
   - Gradient: Gray-500 → Slate-600

### Intelligent Auto-Switching

**Automatic Mode Protection**:
```typescript
if (availableFunds < requiredFunds && mode === 'live') {
  switchTo('paper')
  showWarning('Insufficient funds for live trading')
}
```

**Features**:
- Real-time fund monitoring
- Automatic fallback to paper mode
- Warning notifications with reason
- Manual override capability
- Funds display: Available vs Required

---

## 🏗️ Architecture

### Frontend (`frontend/app/strategy/page.tsx`)

**Components**:
1. **Header Section**
   - Strategy name with gradient icon
   - Real-time running status indicator
   - Pulsing green dot animation

2. **Mode Selector**
   - 3-column grid layout
   - Click to switch modes
   - Active state highlighting
   - Checkmark indicator
   - Hover effects

3. **Auto-Switch Warning**
   - Yellow alert banner
   - Shows reason for switch
   - Displays fund comparison
   - Auto-dismissible

4. **Performance Metrics** (4 cards)
   - Total P&L with trend arrow
   - Win Rate with pie chart icon
   - Avg Win with bar chart
   - Avg Loss with shield icon
   - Gradient backgrounds per metric
   - Hover lift effect

5. **Strategy Rules** (2 cards)
   - Entry rules with checkmarks
   - Exit rules with emojis
   - Glass card styling
   - Icon indicators

### Backend (`backend/services/strategy_executor.py`)

**StrategyExecutor Class**:
```python
class StrategyExecutor:
    - register_strategy()      # Add new strategy
    - update_available_funds() # Update capital
    - set_strategy_mode()      # Change mode
    - start_strategy()         # Begin execution
    - stop_strategy()          # Pause execution
    - execute_trade()          # Place order
    - get_strategy_status()    # Get current state
```

**Auto-Switch Logic**:
```python
def check_funds_and_switch(self):
    if mode == LIVE and available < required:
        mode = PAPER
        auto_switched = True
        reason = "Insufficient funds"
```

### API (`backend/api/strategy_api.py`)

**Endpoints**:
- `GET /api/strategy/status` - Current mode & funds
- `POST /api/strategy/mode` - Change mode
- `POST /api/strategy/funds` - Update funds
- `GET /api/strategy/performance` - Metrics
- `GET /api/strategy/monthly-summary` - Monthly data

---

## 🚀 Usage Guide

### 1. Start Backend
```bash
cd backend/api
python strategy_api.py
```

### 2. Start Frontend
```bash
cd frontend
npm run dev
```

### 3. Access Dashboard
Navigate to: `http://localhost:3000/strategy`

### 4. Control Strategy

**Change Mode**:
- Click on Live/Paper/Stopped button
- System validates funds before switching
- Auto-switches if insufficient funds

**Monitor Status**:
- Green pulsing dot = Running
- Mode badge shows current state
- Yellow warning if auto-switched

**View Performance**:
- Real-time P&L updates
- Win rate percentage
- Average win/loss metrics
- Monthly breakdown

---

## 💾 Database Schema

```sql
CREATE TABLE strategy_trades (
    trade_id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100),
    trade_date DATE,
    stock VARCHAR(50),
    strike DECIMAL,
    option_type VARCHAR(2),
    entry_time TIMESTAMP,
    entry_premium DECIMAL,
    exit_time TIMESTAMP,
    exit_premium DECIMAL,
    pnl_pct DECIMAL,
    pnl_amount DECIMAL,
    exit_reason VARCHAR(50),
    trade_type VARCHAR(20),  -- 'live', 'paper', 'backtest'
    lot_size INTEGER,
    order_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE strategy_status (
    strategy_name VARCHAR(100) PRIMARY KEY,
    mode VARCHAR(20),  -- 'live', 'paper', 'stopped'
    is_running BOOLEAN,
    auto_switched BOOLEAN,
    switch_reason TEXT,
    available_funds DECIMAL,
    required_funds DECIMAL,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🎯 Design Principles

### 1. **Clarity First**
- Clear mode indicators
- Obvious status states
- Explicit warnings
- Readable metrics

### 2. **Safety Built-in**
- Auto-switch protection
- Fund validation
- Confirmation dialogs
- Error handling

### 3. **Premium Feel**
- Glassmorphic cards
- Smooth animations
- Gradient accents
- Micro-interactions

### 4. **Responsive Design**
- Mobile-friendly grid
- Adaptive layouts
- Touch-optimized
- Fast loading

---

## 🔄 Strategy Lifecycle

```
1. Register Strategy
   ↓
2. Set Initial Funds
   ↓
3. Start Strategy (Default: Live)
   ↓
4. Monitor Funds Continuously
   ↓
5. Auto-Switch if Needed
   ↓
6. Execute Trades (Live/Paper)
   ↓
7. Update Performance
   ↓
8. Repeat from Step 4
```

---

## 📊 Performance Tracking

### Metrics Displayed
- **Total P&L**: Cumulative profit/loss
- **Win Rate**: Percentage of winning trades
- **Avg Win**: Average profit per winning trade
- **Avg Loss**: Average loss per losing trade
- **Max Win**: Largest single win
- **Max Loss**: Largest single loss
- **Total Trades**: Number of trades executed
- **Active Positions**: Currently open trades

### Color Coding
- 🟢 Green: Profits, wins, positive metrics
- 🔴 Red: Losses, negative metrics
- 🔵 Blue: Neutral, informational
- 🟡 Yellow: Warnings, alerts

---

## 🛡️ Safety Features

1. **Fund Monitoring**: Real-time balance checks
2. **Auto-Switch**: Automatic paper mode fallback
3. **Manual Override**: Can force mode change
4. **Warning System**: Clear notifications
5. **Stop Capability**: Emergency pause button
6. **Validation**: Pre-trade fund verification

---

## 🎨 UI Components

### Glass Card
```css
background: rgba(255, 255, 255, 0.05)
backdrop-filter: blur(20px)
border: 1px solid rgba(255, 255, 255, 0.1)
```

### Gradient Backgrounds
- Purple-Pink: P&L card
- Blue-Cyan: Win rate card
- Green-Emerald: Avg win card
- Red-Rose: Avg loss card

### Animations
- Pulse: Running indicator (2s infinite)
- Transition: All interactive elements (300ms)
- Hover: Lift effect on cards
- Click: Scale feedback

---

## 📱 Responsive Breakpoints

- **Mobile**: < 768px (1 column)
- **Tablet**: 768px - 1024px (2 columns)
- **Desktop**: > 1024px (4 columns)

---

## 🔮 Future Enhancements

1. **Real-time WebSocket**: Live trade updates
2. **Push Notifications**: Trade alerts
3. **Advanced Charts**: Equity curve, drawdown
4. **Multi-Strategy**: Support multiple strategies
5. **Risk Management**: Position sizing, max drawdown
6. **Backtesting UI**: Interactive parameter tuning
7. **Trade Journal**: Detailed trade log
8. **Mobile App**: Native iOS/Android

---

*Designed with ❤️ for premium trading experience*
*Morning Momentum Alpha - 81.6% Win Rate*
