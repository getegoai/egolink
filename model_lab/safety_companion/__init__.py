"""Safety Companion M0 rule baseline and contract tools."""

from .src.baseline_router import RuleRouter, RouterConfig
from .src.feature_extractor import build_model_input

__all__ = ["RuleRouter", "RouterConfig", "build_model_input"]
__version__ = "0.1.0"
