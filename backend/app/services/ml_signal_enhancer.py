"""
ML Signal Enhancement Service

Uses machine learning to enhance trading signals:
- Feature extraction from technical indicators
- Signal probability scoring using trained models
- Regime detection (trending/ranging/volatile)
- Adaptive position sizing based on model confidence

Models:
- XGBoost for signal classification
- Random Forest for feature importance
- LSTM for sequence prediction (optional)
"""

import asyncio
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


class SignalConfidence(str, Enum):
    """ML-enhanced signal confidence levels."""
    VERY_HIGH = "very_high"  # >80% probability
    HIGH = "high"            # 70-80%
    MODERATE = "moderate"    # 60-70%
    LOW = "low"              # 50-60%
    SKIP = "skip"            # <50%


@dataclass
class EnhancedSignal:
    """Signal with ML enhancements."""
    original_signal: Dict[str, Any]
    ml_probability: float
    confidence: SignalConfidence
    regime: MarketRegime
    feature_importance: Dict[str, float]
    recommended_size_multiplier: float
    risk_score: float  # 0-1, higher = riskier
    supporting_factors: List[str]
    opposing_factors: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ModelMetrics:
    """Metrics for a trained model."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    win_rate_improvement: float
    last_trained: datetime
    training_samples: int
    feature_count: int


class MLSignalEnhancer:
    """
    Machine Learning Signal Enhancement Service.
    
    Enhances traditional technical signals with ML-based probability scoring
    and regime detection.
    """
    
    # Feature categories
    PRICE_FEATURES = [
        'returns_1', 'returns_5', 'returns_10', 'returns_20',
        'high_low_range', 'close_open_range', 'body_size',
        'upper_shadow', 'lower_shadow', 'gap_up', 'gap_down'
    ]
    
    MOMENTUM_FEATURES = [
        'rsi_14', 'rsi_7', 'rsi_21', 'rsi_slope',
        'macd', 'macd_signal', 'macd_hist', 'macd_cross',
        'stoch_k', 'stoch_d', 'stoch_cross',
        'cci', 'williams_r', 'mfi', 'roc'
    ]
    
    TREND_FEATURES = [
        'ema_9', 'ema_21', 'ema_50', 'ema_200',
        'sma_20', 'sma_50', 'sma_200',
        'ema_9_21_cross', 'ema_21_50_cross', 'price_above_sma200',
        'adx', 'plus_di', 'minus_di', 'trend_strength'
    ]
    
    VOLATILITY_FEATURES = [
        'atr_14', 'atr_normalized', 'bb_width', 'bb_position',
        'keltner_width', 'historical_vol_10', 'historical_vol_20',
        'realized_vol', 'vol_regime'
    ]
    
    VOLUME_FEATURES = [
        'volume_sma_ratio', 'volume_ema_ratio', 'obv_slope',
        'vwap_distance', 'volume_trend', 'accumulation_dist'
    ]
    
    def __init__(
        self,
        model_dir: str = "models",
        min_confidence: float = 0.55,
        retrain_interval_days: int = 7,
        lookback_days: int = 252
    ):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.min_confidence = min_confidence
        self.retrain_interval_days = retrain_interval_days
        self.lookback_days = lookback_days
        
        # Models
        self.signal_classifier: Optional[GradientBoostingClassifier] = None
        self.regime_classifier: Optional[RandomForestClassifier] = None
        self.scaler = StandardScaler()
        
        # Model metrics
        self.signal_metrics: Optional[ModelMetrics] = None
        self.regime_metrics: Optional[ModelMetrics] = None
        
        # Feature importance cache
        self.feature_importance: Dict[str, float] = {}
        
        # Load existing models if available
        self._load_models()
    
    def _load_models(self) -> None:
        """Load pre-trained models from disk."""
        signal_path = self.model_dir / "signal_classifier.pkl"
        regime_path = self.model_dir / "regime_classifier.pkl"
        scaler_path = self.model_dir / "scaler.pkl"
        
        try:
            if signal_path.exists():
                with open(signal_path, 'rb') as f:
                    self.signal_classifier = pickle.load(f)
                logger.info("Loaded signal classifier model")
            
            if regime_path.exists():
                with open(regime_path, 'rb') as f:
                    self.regime_classifier = pickle.load(f)
                logger.info("Loaded regime classifier model")
            
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info("Loaded feature scaler")
                
        except Exception as e:
            logger.warning(f"Could not load models: {e}")
    
    def _save_models(self) -> None:
        """Save trained models to disk."""
        try:
            if self.signal_classifier:
                with open(self.model_dir / "signal_classifier.pkl", 'wb') as f:
                    pickle.dump(self.signal_classifier, f)
            
            if self.regime_classifier:
                with open(self.model_dir / "regime_classifier.pkl", 'wb') as f:
                    pickle.dump(self.regime_classifier, f)
            
            with open(self.model_dir / "scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            
            logger.info("Saved models to disk")
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
    
    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract ML features from OHLCV data.
        
        Args:
            df: DataFrame with columns [open, high, low, close, volume]
            
        Returns:
            DataFrame with extracted features
        """
        features = pd.DataFrame(index=df.index)
        
        # Price features
        features['returns_1'] = df['close'].pct_change(1)
        features['returns_5'] = df['close'].pct_change(5)
        features['returns_10'] = df['close'].pct_change(10)
        features['returns_20'] = df['close'].pct_change(20)
        features['high_low_range'] = (df['high'] - df['low']) / df['close']
        features['close_open_range'] = (df['close'] - df['open']) / df['open']
        features['body_size'] = abs(df['close'] - df['open']) / (df['high'] - df['low'] + 1e-10)
        features['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['high'] - df['low'] + 1e-10)
        features['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['high'] - df['low'] + 1e-10)
        features['gap_up'] = (df['open'] > df['close'].shift(1)).astype(float)
        features['gap_down'] = (df['open'] < df['close'].shift(1)).astype(float)
        
        # Momentum features
        features['rsi_14'] = self._calculate_rsi(df['close'], 14)
        features['rsi_7'] = self._calculate_rsi(df['close'], 7)
        features['rsi_21'] = self._calculate_rsi(df['close'], 21)
        features['rsi_slope'] = features['rsi_14'].diff(3)
        
        macd, signal, hist = self._calculate_macd(df['close'])
        features['macd'] = macd
        features['macd_signal'] = signal
        features['macd_hist'] = hist
        features['macd_cross'] = (macd > signal).astype(float).diff()
        
        stoch_k, stoch_d = self._calculate_stochastic(df, 14, 3)
        features['stoch_k'] = stoch_k
        features['stoch_d'] = stoch_d
        features['stoch_cross'] = (stoch_k > stoch_d).astype(float).diff()
        
        features['cci'] = self._calculate_cci(df, 20)
        features['williams_r'] = self._calculate_williams_r(df, 14)
        features['mfi'] = self._calculate_mfi(df, 14)
        features['roc'] = df['close'].pct_change(12) * 100
        
        # Trend features
        features['ema_9'] = df['close'].ewm(span=9).mean() / df['close'] - 1
        features['ema_21'] = df['close'].ewm(span=21).mean() / df['close'] - 1
        features['ema_50'] = df['close'].ewm(span=50).mean() / df['close'] - 1
        features['ema_200'] = df['close'].ewm(span=200).mean() / df['close'] - 1
        features['sma_20'] = df['close'].rolling(20).mean() / df['close'] - 1
        features['sma_50'] = df['close'].rolling(50).mean() / df['close'] - 1
        features['sma_200'] = df['close'].rolling(200).mean() / df['close'] - 1
        
        ema_9 = df['close'].ewm(span=9).mean()
        ema_21 = df['close'].ewm(span=21).mean()
        ema_50 = df['close'].ewm(span=50).mean()
        features['ema_9_21_cross'] = (ema_9 > ema_21).astype(float).diff()
        features['ema_21_50_cross'] = (ema_21 > ema_50).astype(float).diff()
        features['price_above_sma200'] = (df['close'] > df['close'].rolling(200).mean()).astype(float)
        
        adx, plus_di, minus_di = self._calculate_adx(df, 14)
        features['adx'] = adx
        features['plus_di'] = plus_di
        features['minus_di'] = minus_di
        features['trend_strength'] = adx * (1 if plus_di.iloc[-1] > minus_di.iloc[-1] else -1) if len(adx) > 0 else 0
        
        # Volatility features
        features['atr_14'] = self._calculate_atr(df, 14)
        features['atr_normalized'] = features['atr_14'] / df['close']
        
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger(df['close'], 20, 2)
        features['bb_width'] = (bb_upper - bb_lower) / bb_middle
        features['bb_position'] = (df['close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)
        
        features['historical_vol_10'] = df['close'].pct_change().rolling(10).std() * np.sqrt(252)
        features['historical_vol_20'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        features['realized_vol'] = df['close'].pct_change().rolling(5).std() * np.sqrt(252)
        features['vol_regime'] = (features['historical_vol_10'] > features['historical_vol_20']).astype(float)
        
        # Volume features
        features['volume_sma_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        features['volume_ema_ratio'] = df['volume'] / df['volume'].ewm(span=20).mean()
        features['obv_slope'] = self._calculate_obv(df).diff(5)
        features['vwap_distance'] = (df['close'] - self._calculate_vwap(df)) / df['close']
        features['volume_trend'] = df['volume'].diff(5) / df['volume'].rolling(20).mean()
        features['accumulation_dist'] = self._calculate_accumulation_distribution(df)
        
        return features.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD."""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        histogram = macd - signal_line
        return macd, signal_line, histogram
    
    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int, d_period: int) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic oscillator."""
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        stoch_k = 100 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
        stoch_d = stoch_k.rolling(window=d_period).mean()
        return stoch_k, stoch_d
    
    def _calculate_cci(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate CCI."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        return (typical_price - sma) / (0.015 * mad + 1e-10)
    
    def _calculate_williams_r(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Williams %R."""
        high_max = df['high'].rolling(window=period).max()
        low_min = df['low'].rolling(window=period).min()
        return -100 * (high_max - df['close']) / (high_max - low_min + 1e-10)
    
    def _calculate_mfi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Money Flow Index."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        raw_money_flow = typical_price * df['volume']
        
        positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
        
        positive_mf = positive_flow.rolling(window=period).sum()
        negative_mf = negative_flow.rolling(window=period).sum()
        
        mfi = 100 - (100 / (1 + positive_mf / (negative_mf + 1e-10)))
        return mfi
    
    def _calculate_adx(self, df: pd.DataFrame, period: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate ADX."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = low.diff().abs()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * plus_dm.rolling(window=period).mean() / (atr + 1e-10)
        minus_di = 100 * minus_dm.rolling(window=period).mean() / (atr + 1e-10)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(window=period).mean()
        
        return adx, plus_di, minus_di
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate ATR."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean()
    
    def _calculate_bollinger(self, prices: pd.Series, period: int, std_dev: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    def _calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """Calculate On-Balance Volume."""
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return obv
    
    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    def _calculate_accumulation_distribution(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Accumulation/Distribution Line."""
        clv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'] + 1e-10)
        return (clv * df['volume']).cumsum()
    
    def create_labels(self, df: pd.DataFrame, forward_periods: int = 5, threshold: float = 0.01) -> pd.Series:
        """
        Create labels for supervised learning.
        
        Args:
            df: DataFrame with close prices
            forward_periods: Number of periods to look ahead
            threshold: Minimum return threshold for positive/negative label
            
        Returns:
            Series with labels: 1 (buy), -1 (sell), 0 (hold)
        """
        forward_return = df['close'].shift(-forward_periods) / df['close'] - 1
        
        labels = pd.Series(0, index=df.index)
        labels[forward_return > threshold] = 1   # Buy signal
        labels[forward_return < -threshold] = -1  # Sell signal
        
        return labels
    
    async def train_models(
        self,
        training_data: Dict[str, pd.DataFrame],
        forward_periods: int = 5,
        threshold: float = 0.01
    ) -> Dict[str, ModelMetrics]:
        """
        Train ML models on historical data.
        
        Args:
            training_data: Dict mapping symbol to OHLCV DataFrame
            forward_periods: Periods ahead for label creation
            threshold: Return threshold for labels
            
        Returns:
            Dict with model metrics
        """
        logger.info("Starting model training...")
        
        all_features = []
        all_labels = []
        
        for symbol, df in training_data.items():
            logger.info(f"Extracting features for {symbol}...")
            features = self.extract_features(df)
            labels = self.create_labels(df, forward_periods, threshold)
            
            # Remove rows with NaN
            valid_idx = ~(features.isna().any(axis=1) | labels.isna())
            features = features[valid_idx]
            labels = labels[valid_idx]
            
            all_features.append(features)
            all_labels.append(labels)
        
        # Combine all data
        X = pd.concat(all_features, ignore_index=True)
        y = pd.concat(all_labels, ignore_index=True)
        
        logger.info(f"Training on {len(X)} samples with {len(X.columns)} features")
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train signal classifier with time series cross-validation
        logger.info("Training signal classifier...")
        self.signal_classifier = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=50,
            min_samples_leaf=20,
            subsample=0.8,
            random_state=42
        )
        
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = cross_val_score(self.signal_classifier, X_scaled, y, cv=tscv, scoring='accuracy')
        
        self.signal_classifier.fit(X_scaled, y)
        
        # Get feature importance
        self.feature_importance = dict(zip(X.columns, self.signal_classifier.feature_importances_))
        
        # Calculate metrics
        y_pred = self.signal_classifier.predict(X_scaled)
        report = classification_report(y, y_pred, output_dict=True, zero_division=0)
        
        self.signal_metrics = ModelMetrics(
            accuracy=cv_scores.mean(),
            precision=report.get('weighted avg', {}).get('precision', 0),
            recall=report.get('weighted avg', {}).get('recall', 0),
            f1_score=report.get('weighted avg', {}).get('f1-score', 0),
            win_rate_improvement=0,  # Calculate separately
            last_trained=datetime.now(),
            training_samples=len(X),
            feature_count=len(X.columns)
        )
        
        # Train regime classifier
        logger.info("Training regime classifier...")
        regime_labels = self._create_regime_labels(pd.concat([d for d in training_data.values()], ignore_index=True))
        
        # Align regime labels with features
        regime_labels = regime_labels.iloc[-len(X):]
        
        self.regime_classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=50,
            random_state=42
        )
        self.regime_classifier.fit(X_scaled, regime_labels)
        
        # Save models
        self._save_models()
        
        logger.info(f"Model training complete. Signal accuracy: {self.signal_metrics.accuracy:.2%}")
        
        return {
            "signal_model": self.signal_metrics,
            "feature_importance": dict(sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:20])
        }
    
    def _create_regime_labels(self, df: pd.DataFrame) -> pd.Series:
        """Create market regime labels."""
        regimes = pd.Series(MarketRegime.RANGING.value, index=df.index)
        
        # Calculate regime indicators
        returns_20 = df['close'].pct_change(20)
        volatility = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        vol_median = volatility.median()
        
        # Trending up: positive returns, moderate volatility
        regimes[(returns_20 > 0.05) & (volatility < vol_median * 1.5)] = MarketRegime.TRENDING_UP.value
        
        # Trending down: negative returns, moderate volatility
        regimes[(returns_20 < -0.05) & (volatility < vol_median * 1.5)] = MarketRegime.TRENDING_DOWN.value
        
        # High volatility
        regimes[volatility > vol_median * 1.5] = MarketRegime.HIGH_VOLATILITY.value
        
        # Low volatility
        regimes[volatility < vol_median * 0.5] = MarketRegime.LOW_VOLATILITY.value
        
        return regimes
    
    async def enhance_signal(
        self,
        signal: Dict[str, Any],
        market_data: pd.DataFrame
    ) -> EnhancedSignal:
        """
        Enhance a trading signal with ML predictions.
        
        Args:
            signal: Original signal dict with type, symbol, price, etc.
            market_data: Recent OHLCV data for the symbol
            
        Returns:
            EnhancedSignal with ML probability and recommendations
        """
        if self.signal_classifier is None:
            logger.warning("Signal classifier not trained, using default enhancement")
            return EnhancedSignal(
                original_signal=signal,
                ml_probability=0.5,
                confidence=SignalConfidence.MODERATE,
                regime=MarketRegime.RANGING,
                feature_importance={},
                recommended_size_multiplier=1.0,
                risk_score=0.5,
                supporting_factors=["ML model not trained"],
                opposing_factors=[],
            )
        
        # Extract features from recent data
        features = self.extract_features(market_data)
        latest_features = features.iloc[-1:].values
        
        # Scale features
        scaled_features = self.scaler.transform(latest_features)
        
        # Get probability prediction
        proba = self.signal_classifier.predict_proba(scaled_features)[0]
        
        # Map signal type to class
        signal_type = signal.get('signal_type', signal.get('type', 'buy')).lower()
        if 'buy' in signal_type or 'long' in signal_type:
            target_class = 1
        elif 'sell' in signal_type or 'short' in signal_type:
            target_class = -1
        else:
            target_class = 0
        
        # Get probability for target class
        class_idx = list(self.signal_classifier.classes_).index(target_class) if target_class in self.signal_classifier.classes_ else 0
        ml_probability = proba[class_idx]
        
        # Determine confidence level
        if ml_probability >= 0.8:
            confidence = SignalConfidence.VERY_HIGH
        elif ml_probability >= 0.7:
            confidence = SignalConfidence.HIGH
        elif ml_probability >= 0.6:
            confidence = SignalConfidence.MODERATE
        elif ml_probability >= 0.5:
            confidence = SignalConfidence.LOW
        else:
            confidence = SignalConfidence.SKIP
        
        # Get regime prediction
        regime_pred = self.regime_classifier.predict(scaled_features)[0]
        regime = MarketRegime(regime_pred)
        
        # Calculate recommended size multiplier
        size_multiplier = self._calculate_size_multiplier(ml_probability, regime)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(features.iloc[-1], regime)
        
        # Identify supporting and opposing factors
        supporting, opposing = self._analyze_factors(features.iloc[-1], signal_type)
        
        return EnhancedSignal(
            original_signal=signal,
            ml_probability=ml_probability,
            confidence=confidence,
            regime=regime,
            feature_importance=dict(sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]),
            recommended_size_multiplier=size_multiplier,
            risk_score=risk_score,
            supporting_factors=supporting,
            opposing_factors=opposing,
        )
    
    def _calculate_size_multiplier(self, probability: float, regime: MarketRegime) -> float:
        """Calculate position size multiplier based on ML confidence and regime."""
        # Base multiplier from probability
        if probability >= 0.8:
            base = 1.5
        elif probability >= 0.7:
            base = 1.2
        elif probability >= 0.6:
            base = 1.0
        elif probability >= 0.5:
            base = 0.7
        else:
            base = 0.5
        
        # Regime adjustment
        regime_factor = {
            MarketRegime.TRENDING_UP: 1.2,
            MarketRegime.TRENDING_DOWN: 1.2,
            MarketRegime.RANGING: 0.8,
            MarketRegime.HIGH_VOLATILITY: 0.6,
            MarketRegime.LOW_VOLATILITY: 1.0,
        }.get(regime, 1.0)
        
        return round(base * regime_factor, 2)
    
    def _calculate_risk_score(self, features: pd.Series, regime: MarketRegime) -> float:
        """Calculate risk score (0-1, higher = riskier)."""
        risk = 0.5  # Base risk
        
        # High volatility increases risk
        if features.get('atr_normalized', 0) > features.get('atr_normalized', 0):
            risk += 0.1
        
        # Extreme RSI increases risk
        rsi = features.get('rsi_14', 50)
        if rsi > 80 or rsi < 20:
            risk += 0.15
        
        # High ADX with extreme DI increases risk
        adx = features.get('adx', 25)
        if adx > 40:
            risk += 0.1
        
        # Regime-based risk
        if regime == MarketRegime.HIGH_VOLATILITY:
            risk += 0.2
        elif regime == MarketRegime.RANGING:
            risk += 0.1
        
        return min(1.0, max(0.0, risk))
    
    def _analyze_factors(self, features: pd.Series, signal_type: str) -> Tuple[List[str], List[str]]:
        """Analyze supporting and opposing factors for a signal."""
        supporting = []
        opposing = []
        
        is_bullish = 'buy' in signal_type.lower() or 'long' in signal_type.lower()
        
        # RSI analysis
        rsi = features.get('rsi_14', 50)
        if is_bullish:
            if rsi < 30:
                supporting.append(f"RSI oversold ({rsi:.1f})")
            elif rsi > 70:
                opposing.append(f"RSI overbought ({rsi:.1f})")
        else:
            if rsi > 70:
                supporting.append(f"RSI overbought ({rsi:.1f})")
            elif rsi < 30:
                opposing.append(f"RSI oversold ({rsi:.1f})")
        
        # MACD analysis
        macd_hist = features.get('macd_hist', 0)
        if is_bullish:
            if macd_hist > 0:
                supporting.append("MACD histogram positive")
            else:
                opposing.append("MACD histogram negative")
        else:
            if macd_hist < 0:
                supporting.append("MACD histogram negative")
            else:
                opposing.append("MACD histogram positive")
        
        # Trend analysis
        price_above_sma200 = features.get('price_above_sma200', 0.5) > 0.5
        if is_bullish:
            if price_above_sma200:
                supporting.append("Price above 200 SMA")
            else:
                opposing.append("Price below 200 SMA")
        else:
            if not price_above_sma200:
                supporting.append("Price below 200 SMA")
            else:
                opposing.append("Price above 200 SMA")
        
        # Volume analysis
        vol_ratio = features.get('volume_sma_ratio', 1)
        if vol_ratio > 1.5:
            supporting.append(f"High volume ({vol_ratio:.1f}x avg)")
        elif vol_ratio < 0.5:
            opposing.append("Low volume")
        
        # ADX trend strength
        adx = features.get('adx', 25)
        if adx > 25:
            supporting.append(f"Strong trend (ADX {adx:.1f})")
        else:
            opposing.append(f"Weak trend (ADX {adx:.1f})")
        
        return supporting[:5], opposing[:5]
    
    async def batch_enhance_signals(
        self,
        signals: List[Dict[str, Any]],
        market_data: Dict[str, pd.DataFrame]
    ) -> List[EnhancedSignal]:
        """Enhance multiple signals in batch."""
        enhanced = []
        for signal in signals:
            symbol = signal.get('symbol', '')
            if symbol in market_data:
                enhanced_signal = await self.enhance_signal(signal, market_data[symbol])
                enhanced.append(enhanced_signal)
        return enhanced
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get current model status and metrics."""
        return {
            "signal_classifier_loaded": self.signal_classifier is not None,
            "regime_classifier_loaded": self.regime_classifier is not None,
            "signal_metrics": {
                "accuracy": self.signal_metrics.accuracy if self.signal_metrics else None,
                "precision": self.signal_metrics.precision if self.signal_metrics else None,
                "recall": self.signal_metrics.recall if self.signal_metrics else None,
                "f1_score": self.signal_metrics.f1_score if self.signal_metrics else None,
                "last_trained": self.signal_metrics.last_trained.isoformat() if self.signal_metrics else None,
                "training_samples": self.signal_metrics.training_samples if self.signal_metrics else None,
            },
            "top_features": dict(sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]) if self.feature_importance else {},
        }


# Singleton instance
_ml_enhancer: Optional[MLSignalEnhancer] = None


def get_ml_enhancer() -> MLSignalEnhancer:
    """Get or create ML signal enhancer singleton."""
    global _ml_enhancer
    if _ml_enhancer is None:
        _ml_enhancer = MLSignalEnhancer()
    return _ml_enhancer
