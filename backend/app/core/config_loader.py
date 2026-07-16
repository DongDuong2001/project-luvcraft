import yaml
import os
import logging

logger = logging.getLogger(__name__)

def load_collectors_config(config_path: str = "app/conf/collectors.yaml") -> dict:
    """
    Extensibility Requirement:
    Loads source definitions (subreddits, feeds, platforms) from external YAML configuration.
    """
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}. Using defaults.")
        return {}
    
    with open(config_path, 'r') as file:
        try:
            config = yaml.safe_load(file)
            logger.info("Successfully loaded external collector configurations.")
            return config
        except yaml.YAMLError as exc:
            logger.error(f"Error parsing YAML config: {exc}")
            return {}

# Global variable to hold the loaded configuration
COLLECTORS_CONFIG = load_collectors_config()
