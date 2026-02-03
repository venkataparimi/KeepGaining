from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.db.session import get_db
from app.db.models.strategy import Strategy, StrategyTest
from app.backtest.enhanced_engine import BacktestEngine, BacktestConfig, OrderSide
from app.backtest.walk_forward import (
    WalkForwardEngine,
    WalkForwardConfig,
    WalkForwardType,
    create_walk_forward_engine,
)
from datetime import datetime, timedelta
import json
import pandas as pd

router = APIRouter()


# ============ Request/Response Models ============

class WalkForwardRequest(BaseModel):
    """Request for walk-forward analysis."""
    symbol: str = Field(..., description="Symbol to backtest")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    training_period_days: int = Field(default=180, description="Training period in days")
    testing_period_days: int = Field(default=30, description="Testing period in days")
    step_days: int = Field(default=30, description="Step forward in days")
    walk_type: str = Field(default="rolling", description="rolling, anchored, or expanding")
    optimize_metric: str = Field(default="sharpe_ratio", description="Metric to optimize")
    initial_capital: float = Field(default=100000.0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "NIFTY",
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                "training_period_days": 180,
                "testing_period_days": 30,
                "step_days": 30,
                "walk_type": "rolling",
                "optimize_metric": "sharpe_ratio",
                "initial_capital": 100000.0,
            }
        }

async def run_backtest_task(test_id: int, strategy_code: str, db: Session):
    """Background task to run backtest"""
    try:
        # Create backtest engine
        config = BacktestConfig(
            initial_capital=100000.0,
            commission_percent=0.03,
            slippage_percent=0.05
        )
        engine = BacktestEngine(config)
        
        # TODO: Execute strategy code against historical data
        # For now, generate sample trades
        base_time = datetime.now() - timedelta(days=30)
        for i in range(20):
            engine.execute_trade(
                entry_time=base_time + timedelta(days=i),
                exit_time=base_time + timedelta(days=i, hours=6),
                symbol="NIFTY",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                entry_price=18000 + (i * 10),
                exit_price=18000 + (i * 10) + (50 if i % 3 == 0 else -30)
            )
        
        # Calculate metrics
        metrics = engine.calculate_metrics()
        equity_curve = engine.get_equity_curve().to_dict('records')
        trades = engine.get_trades_df().to_dict('records')
        
        # Update test record
        test = db.query(StrategyTest).filter(StrategyTest.id == test_id).first()
        if test:
            test.status = "passed" if metrics.get('total_return_percent', 0) > 0 else "failed"
            test.completed_at = datetime.now()
            test.duration_seconds = int((test.completed_at - test.started_at).total_seconds())
            test.metrics = metrics
            test.results = {
                'equity_curve': equity_curve,
                'trades': trades
            }
            db.commit()
    except Exception as e:
        # Mark test as failed
        test = db.query(StrategyTest).filter(StrategyTest.id == test_id).first()
        if test:
            test.status = "failed"
            test.completed_at = datetime.now()
            test.results = {'error': str(e)}
            db.commit()

@router.post("/strategies/{strategy_id}/backtest")
async def run_backtest(
    strategy_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Run backtest for a strategy"""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy or not strategy.current_version:
        raise HTTPException(status_code=404, detail="Strategy or version not found")
    
    # Create test record
    test = StrategyTest(
        strategy_id=strategy_id,
        version_id=strategy.current_version_id,
        test_type="backtest",
        status="running",
        started_at=datetime.now()
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    
    # Run backtest in background
    background_tasks.add_task(
        run_backtest_task,
        test.id,
        strategy.current_version.code,
        db
    )
    
    return {"test_id": test.id, "status": "running"}

@router.get("/strategies/{strategy_id}/tests/{test_id}/results")
async def get_test_results(
    strategy_id: int,
    test_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed test results"""
    test = db.query(StrategyTest).filter(
        StrategyTest.strategy_id == strategy_id,
        StrategyTest.id == test_id
    ).first()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    
    return {
        'id': test.id,
        'status': test.status,
        'test_type': test.test_type,
        'started_at': test.started_at,
        'completed_at': test.completed_at,
        'duration_seconds': test.duration_seconds,
        'metrics': test.metrics,
        'results': test.results
    }

@router.get("/strategies/{strategy_id}/tests/{test_id}/equity-curve")
async def get_equity_curve(
    strategy_id: int,
    test_id: int,
    db: Session = Depends(get_db)
):
    """Get equity curve data"""
    test = db.query(StrategyTest).filter(
        StrategyTest.strategy_id == strategy_id,
        StrategyTest.id == test_id
    ).first()
    
    if not test or not test.results:
        raise HTTPException(status_code=404, detail="Test results not found")
    
    return test.results.get('equity_curve', [])

@router.get("/strategies/{strategy_id}/tests/{test_id}/trades")
async def get_trade_log(
    strategy_id: int,
    test_id: int,
    db: Session = Depends(get_db)
):
    """Get trade log"""
    test = db.query(StrategyTest).filter(
        StrategyTest.strategy_id == strategy_id,
        StrategyTest.id == test_id
    ).first()
    
    if not test or not test.results:
        raise HTTPException(status_code=404, detail="Test results not found")
    
    return test.results.get('trades', [])


# ============ Walk-Forward Analysis Endpoints ============

def _sample_strategy_runner(data: pd.DataFrame, params: Dict[str, Any], config: BacktestConfig):
    """
    Sample strategy runner for testing.
    In production, this would execute actual strategy logic.
    """
    from app.backtest.enhanced_engine import BacktestEngine, Trade
    
    engine = BacktestEngine(config)
    
    # Simple moving average crossover strategy (placeholder)
    if len(data) < 20:
        return [], engine.calculate_metrics()
    
    # Get SMA periods from params or use defaults
    fast_period = params.get('fast_sma', 5)
    slow_period = params.get('slow_sma', 20)
    
    if 'close' not in data.columns:
        # Assume data has 'Close' column
        if 'Close' in data.columns:
            data = data.rename(columns={'Close': 'close'})
        else:
            return [], {}
    
    # Calculate SMAs
    data['fast_sma'] = data['close'].rolling(window=fast_period).mean()
    data['slow_sma'] = data['close'].rolling(window=slow_period).mean()
    
    # Generate signals
    data['signal'] = 0
    data.loc[data['fast_sma'] > data['slow_sma'], 'signal'] = 1
    data.loc[data['fast_sma'] < data['slow_sma'], 'signal'] = -1
    
    # Detect crossovers
    data['position_change'] = data['signal'].diff()
    
    # Execute trades on crossovers
    in_position = False
    entry_time = None
    entry_price = None
    
    for idx, row in data.iterrows():
        if pd.isna(row['position_change']):
            continue
        
        if row['position_change'] == 2 and not in_position:  # Buy signal
            in_position = True
            entry_time = idx
            entry_price = row['close']
        elif row['position_change'] == -2 and in_position:  # Sell signal
            engine.execute_trade(
                entry_time=entry_time,
                exit_time=idx,
                symbol=params.get('symbol', 'NIFTY'),
                side=OrderSide.BUY,
                entry_price=entry_price,
                exit_price=row['close']
            )
            in_position = False
    
    return engine.trades, engine.calculate_metrics()


@router.post("/walk-forward")
async def run_walk_forward_analysis(request: WalkForwardRequest):
    """
    Run walk-forward analysis on a strategy.
    
    Walk-forward analysis divides data into training and testing windows,
    optimizes parameters on training data, and validates on testing data.
    """
    from loguru import logger
    
    try:
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        # Load market data (placeholder - in production, load from database)
        # Generate sample data for demonstration
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        import numpy as np
        np.random.seed(42)
        
        # Generate realistic price data
        base_price = 18000
        returns = np.random.normal(0.0002, 0.015, len(date_range))
        prices = base_price * np.cumprod(1 + returns)
        
        data = pd.DataFrame({
            'close': prices,
            'open': prices * (1 + np.random.normal(0, 0.005, len(date_range))),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.01, len(date_range)))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.01, len(date_range)))),
            'volume': np.random.uniform(1000000, 5000000, len(date_range)),
        }, index=date_range)
        
        # Create walk-forward engine
        config = WalkForwardConfig(
            training_period_days=request.training_period_days,
            testing_period_days=request.testing_period_days,
            step_days=request.step_days,
            walk_type=WalkForwardType(request.walk_type),
            optimize_metric=request.optimize_metric,
            parameter_ranges={
                'fast_sma': [3, 5, 7, 10],
                'slow_sma': [15, 20, 30, 50],
                'symbol': [request.symbol],
            },
            initial_capital=request.initial_capital,
        )
        
        def strategy_runner(df, params, bt_config):
            return _sample_strategy_runner(df, params, bt_config)
        
        engine = WalkForwardEngine(config, strategy_runner)
        
        # Run walk-forward analysis
        result = engine.run(data)
        
        # Format response
        return {
            "status": "success",
            "combined_metrics": result.combined_metrics,
            "robustness": {
                "consistency_score": result.consistency_score,
                "efficiency_ratio": result.efficiency_ratio,
                "parameter_stability": result.parameter_stability,
            },
            "windows": [
                {
                    "window_id": w.window_id,
                    "training_period": f"{w.training_start.date()} - {w.training_end.date()}",
                    "testing_period": f"{w.testing_start.date()} - {w.testing_end.date()}",
                    "optimized_params": w.optimized_params,
                    "training_trades": w.training_trades,
                    "testing_trades": w.testing_trades,
                    "oos_return": w.testing_metrics.get("total_return_percent", 0),
                    "oos_sharpe": w.testing_metrics.get("sharpe_ratio", 0),
                }
                for w in result.windows
            ],
            "equity_curve": result.equity_curve,
            "total_trades": len(result.all_trades),
        }
        
    except Exception as e:
        logger.error(f"Walk-forward analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/walk-forward/summary")
async def get_walk_forward_summary():
    """Get explanation of walk-forward analysis methodology."""
    return {
        "description": "Walk-forward analysis is a robust method to validate trading strategies",
        "methodology": {
            "step_1": "Divide historical data into multiple training and testing windows",
            "step_2": "Optimize strategy parameters on each training window",
            "step_3": "Validate the optimized strategy on the subsequent testing window",
            "step_4": "Aggregate out-of-sample results to assess true strategy performance",
        },
        "metrics": {
            "consistency_score": "Percentage of testing windows that are profitable",
            "efficiency_ratio": "Ratio of out-of-sample to in-sample performance",
            "parameter_stability": "Stability of optimized parameters across windows",
        },
        "walk_types": {
            "rolling": "Training window slides forward, constant size",
            "anchored": "Training always starts from beginning, expands over time",
            "expanding": "Same as anchored",
        },
    }
