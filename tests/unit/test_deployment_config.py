import os
import pytest
from tools.deployment_config import (
    get_deployment_mode,
    is_dev_mode,
    is_prod_mode,
    get_data_path,
    get_db_path,
    should_preserve_dev_data,
    log_api_key_warning,
    get_deployment_mode_dict
)


def test_get_deployment_mode_default():
    """Test default deployment mode is PROD"""
    # Clear env to test default
    os.environ.pop("DEPLOYMENT_MODE", None)
    assert get_deployment_mode() == "PROD"


def test_get_deployment_mode_dev():
    """Test DEV mode detection"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_deployment_mode() == "DEV"
    assert is_dev_mode() == True
    assert is_prod_mode() == False


def test_get_deployment_mode_prod():
    """Test PROD mode detection"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_deployment_mode() == "PROD"
    assert is_dev_mode() == False
    assert is_prod_mode() == True


def test_get_data_path_prod():
    """Test production data path"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_data_path("./data/agent_data") == "./data/agent_data"


def test_get_data_path_dev():
    """Test dev data path substitution"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_data_path("./data/agent_data") == "./data/dev_agent_data"


def test_get_db_path_prod():
    """Test production database path"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_db_path("data/trading.db") == "data/trading.db"


def test_get_db_path_dev():
    """Test dev database path substitution"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_db_path("data/trading.db") == "data/trading_dev.db"
    assert get_db_path("data/jobs.db") == "data/jobs_dev.db"


def test_should_preserve_dev_data_default():
    """Test default preserve flag is False"""
    os.environ.pop("PRESERVE_DEV_DATA", None)
    assert should_preserve_dev_data() == False


def test_should_preserve_dev_data_true():
    """Test preserve flag can be enabled"""
    os.environ["PRESERVE_DEV_DATA"] = "true"
    assert should_preserve_dev_data() == True


def test_log_api_key_warning_in_dev(capsys):
    """Test warning logged when API keys present in DEV mode"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["OPENAI_API_KEY"] = "sk-test123"

    log_api_key_warning()

    captured = capsys.readouterr()
    assert "⚠️  WARNING: Production API keys detected in DEV mode" in captured.out
    assert "OPENAI_API_KEY" in captured.out


def test_get_deployment_mode_dict():
    """Test deployment mode dictionary generation"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["PRESERVE_DEV_DATA"] = "true"

    result = get_deployment_mode_dict()

    assert result["deployment_mode"] == "DEV"
    assert result["is_dev_mode"] == True
    assert result["preserve_dev_data"] == True
