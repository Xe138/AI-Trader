"""
Deployment mode configuration utilities

Handles PROD vs DEV mode differentiation including:
- Data path isolation
- Database path isolation
- API key validation warnings
- Deployment mode detection
"""

import os
from typing import Optional


def get_deployment_mode() -> str:
    """
    Get current deployment mode

    Returns:
        "PROD" or "DEV" (defaults to PROD if not set)
    """
    mode = os.getenv("DEPLOYMENT_MODE", "PROD").upper()
    if mode not in ["PROD", "DEV"]:
        print(f"⚠️  Invalid DEPLOYMENT_MODE '{mode}', defaulting to PROD")
        return "PROD"
    return mode


def is_dev_mode() -> bool:
    """Check if running in DEV mode"""
    return get_deployment_mode() == "DEV"


def is_prod_mode() -> bool:
    """Check if running in PROD mode"""
    return get_deployment_mode() == "PROD"


def get_data_path(base_path: str) -> str:
    """
    Get data path based on deployment mode

    Args:
        base_path: Base data path (e.g., "./data/agent_data")

    Returns:
        Modified path for DEV mode or original for PROD

    Example:
        PROD: "./data/agent_data" -> "./data/agent_data"
        DEV:  "./data/agent_data" -> "./data/dev_agent_data"
    """
    if is_dev_mode():
        # Replace agent_data with dev_agent_data
        return base_path.replace("agent_data", "dev_agent_data")
    return base_path


def get_db_path(base_db_path: str) -> str:
    """
    Get database path based on deployment mode

    Args:
        base_db_path: Base database path (e.g., "data/trading.db")

    Returns:
        Modified path for DEV mode or original for PROD

    Example:
        PROD: "data/trading.db" -> "data/trading.db"
        DEV:  "data/trading.db" -> "data/trading_dev.db"

    Note:
        This function is idempotent - calling it multiple times on the same
        path will not add multiple _dev suffixes.
    """
    if is_dev_mode():
        # Check if already has _dev suffix (idempotent)
        if "_dev.db" in base_db_path:
            return base_db_path

        # Insert _dev before .db extension
        if base_db_path.endswith(".db"):
            return base_db_path[:-3] + "_dev.db"
        return base_db_path + "_dev"
    return base_db_path


def should_preserve_dev_data() -> bool:
    """
    Check if dev data should be preserved between runs

    Returns:
        True if PRESERVE_DEV_DATA=true, False otherwise
    """
    preserve = os.getenv("PRESERVE_DEV_DATA", "false").lower()
    return preserve in ["true", "1", "yes"]


def log_api_key_warning() -> None:
    """
    Log warning if production API keys are detected in DEV mode

    Checks for common API key environment variables and warns if found.
    """
    if not is_dev_mode():
        return

    # List of API key environment variables to check
    api_key_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ALPHAADVANTAGE_API_KEY",
        "JINA_API_KEY"
    ]

    detected_keys = []
    for var in api_key_vars:
        value = os.getenv(var)
        if value and value != "" and "your_" not in value.lower():
            detected_keys.append(var)

    if detected_keys:
        print("⚠️  WARNING: Production API keys detected in DEV mode")
        print(f"   Detected: {', '.join(detected_keys)}")
        print("   These keys will NOT be used - mock AI responses will be returned")
        print("   This is expected if you're testing dev mode with existing .env file")


def log_dev_mode_startup_warning() -> None:
    """
    Display prominent warning when server starts in DEV mode

    Warns users that:
    - AI calls will be simulated/mocked
    - Data may not be retained between runs
    - This is a development environment
    """
    if not is_dev_mode():
        return

    preserve_data = should_preserve_dev_data()

    print()
    print("=" * 70)
    print("⚠️  " + "DEVELOPMENT MODE WARNING".center(64) + "  ⚠️")
    print("=" * 70)
    print()
    print("  🚧 This server is running in DEVELOPMENT mode (DEPLOYMENT_MODE=DEV)")
    print()
    print("  📌 IMPORTANT:")
    print("     • AI API calls will be SIMULATED (mock responses)")
    print("     • No real AI model costs will be incurred")
    if preserve_data:
        print("     • Dev data WILL BE PRESERVED between runs (PRESERVE_DEV_DATA=true)")
    else:
        print("     • Dev data WILL BE RESET on each startup (PRESERVE_DEV_DATA=false)")
    print("     • Using isolated dev database and data paths")
    print()
    print("  💡 To use PRODUCTION mode:")
    print("     Set environment variable: DEPLOYMENT_MODE=PROD")
    print()
    print("=" * 70)
    print()


def get_deployment_mode_dict() -> dict:
    """
    Get deployment mode information as dictionary (for API responses)

    Returns:
        Dictionary with deployment mode metadata
    """
    return {
        "deployment_mode": get_deployment_mode(),
        "is_dev_mode": is_dev_mode(),
        "preserve_dev_data": should_preserve_dev_data() if is_dev_mode() else None
    }
