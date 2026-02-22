from typing import Dict, Type
from app.strategies.base import BaseStrategy
from app.strategies.straddle import ShortStraddleStrategy
from app.strategies.ema_option_buyer import EMAOptionBuyingStrategy
from app.strategies.emos_strategy import EMOSStrategy

class StrategyRegistry:
    """
    Registry to manage available strategies.
    In a real system, this would load from DB or dynamic modules.
    """
    _strategies = {
        "ShortStraddle": ShortStraddleStrategy,
        "EMAOptionBuying": EMAOptionBuyingStrategy,
        "EMOS": EMOSStrategy
    }

    @classmethod
    def get_strategy_class(cls, name: str):
        return cls._strategies.get(name)

    @classmethod
    def list_strategies(cls):
        return list(cls._strategies.keys())
