"""Prompt Manager for Comet AI Templates

This module loads and manages structured prompt templates for Comet AI integration.
Templates are stored in the prompts/templates directory and can be formatted with
parameters for dynamic content.

Usage:
    from app.comet.prompt_manager import PromptManager
    
    pm = PromptManager()
    prompt = pm.format_prompt(
        "signal_analysis",
        symbol="NIFTY",
        signal_type="BULLISH",
        entry_price=22000,
        current_price=22050,
        timeframe="15m",
        indicators="RSI: 65",
        market_context="Strong uptrend"
    )
"""

from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger


class PromptManager:
    """Load and manage Comet AI prompt templates"""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """Initialize PromptManager
        
        Args:
            prompts_dir: Custom directory for prompt templates.
                        Defaults to backend/prompts/templates/
        """
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            # Default: backend/prompts/templates/
            self.prompts_dir = Path(__file__).parent.parent.parent / "prompts" / "templates"
        
        logger.info(f"PromptManager initialized with directory: {self.prompts_dir}")
        
        # Validate directory exists
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")
            logger.info("Creating prompts directory...")
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
    
    def load_template(self, template_name: str) -> str:
        """Load a prompt template by name
        
        Args:
            template_name: Name of the template file (without .txt extension)
        
        Returns:
            Template content as string, or empty string if not found
        
        Example:
            template = pm.load_template("signal_analysis")
        """
        template_path = self.prompts_dir / f"{template_name}.txt"
        
        if not template_path.exists():
            logger.error(f"Template not found: {template_name} at {template_path}")
            return ""
        
        try:
            content = template_path.read_text(encoding='utf-8')
            logger.debug(f"Loaded template: {template_name} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {e}")
            return ""
    
    def format_prompt(self, template_name: str, **kwargs) -> str:
        """Load and format a prompt template with parameters
        
        Args:
            template_name: Name of the template to use
            **kwargs: Parameters to substitute in the template
        
        Returns:
            Formatted prompt string ready for Comet AI
        
        Example:
            prompt = pm.format_prompt(
                "signal_analysis",
                symbol="NIFTY",
                signal_type="BULLISH",
                entry_price=22000,
                current_price=22050,
                timeframe="15m",
                indicators="RSI: 65, MACD: Bullish",
                market_context="Strong uptrend"
            )
        """
        template = self.load_template(template_name)
        
        if not template:
            logger.warning(f"Empty or missing template: {template_name}")
            return ""
        
        try:
            # Format template with provided parameters
            formatted = template.format(**kwargs)
            logger.debug(f"Formatted template: {template_name}")
            return formatted
        except KeyError as e:
            logger.error(f"Missing required parameter in template {template_name}: {e}")
            logger.info(f"Provided parameters: {list(kwargs.keys())}")
            return ""
        except Exception as e:
            logger.error(f"Error formatting template {template_name}: {e}")
            return ""
    
    def list_templates(self) -> list[str]:
        """List all available template names
        
        Returns:
            List of template names (without .txt extension)
        
        Example:
            templates = pm.list_templates()
            # ['signal_analysis', 'risk_assessment', 'market_context', 'trade_plan']
        """
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")
            return []
        
        try:
            template_files = list(self.prompts_dir.glob("*.txt"))
            template_names = [f.stem for f in template_files]
            logger.info(f"Found {len(template_names)} templates: {template_names}")
            return sorted(template_names)
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []
    
    def validate_template(self, template_name: str, required_params: list[str]) -> tuple[bool, list[str]]:
        """Validate that a template contains all required parameters
        
        Args:
            template_name: Name of the template to validate
            required_params: List of required parameter names
        
        Returns:
            Tuple of (is_valid, missing_params)
        
        Example:
            valid, missing = pm.validate_template(
                "signal_analysis",
                ["symbol", "signal_type", "entry_price"]
            )
        """
        template = self.load_template(template_name)
        
        if not template:
            return False, required_params
        
        missing_params = []
        for param in required_params:
            placeholder = f"{{{param}}}"
            if placeholder not in template:
                missing_params.append(param)
        
        is_valid = len(missing_params) == 0
        
        if is_valid:
            logger.debug(f"Template {template_name} validated successfully")
        else:
            logger.warning(f"Template {template_name} missing parameters: {missing_params}")
        
        return is_valid, missing_params
    
    def get_template_params(self, template_name: str) -> list[str]:
        """Extract all parameter placeholders from a template
        
        Args:
            template_name: Name of the template
        
        Returns:
            List of parameter names found in the template
        
        Example:
            params = pm.get_template_params("signal_analysis")
            # ['symbol', 'signal_type', 'entry_price', 'current_price', ...]
        """
        import re
        
        template = self.load_template(template_name)
        
        if not template:
            return []
        
        # Find all {parameter_name} patterns
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, template)
        
        # Remove duplicates and sort
        params = sorted(set(matches))
        
        logger.debug(f"Template {template_name} has {len(params)} parameters: {params}")
        return params


# Singleton instance for convenience
_prompt_manager = None

def get_prompt_manager() -> PromptManager:
    """Get global PromptManager instance (singleton)
    
    Returns:
        Shared PromptManager instance
    
    Example:
        pm = get_prompt_manager()
        prompt = pm.format_prompt("signal_analysis", ...)
    """
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
