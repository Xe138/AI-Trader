"""Unit tests for model factory - provider-specific model creation"""

import pytest
from unittest.mock import Mock, patch
from agent.model_factory import create_model


class TestModelFactory:
    """Tests for create_model factory function"""

    @patch('agent.model_factory.ChatDeepSeek')
    def test_create_model_deepseek(self, mock_deepseek_class):
        """Test that DeepSeek models use ChatDeepSeek"""
        mock_model = Mock()
        mock_deepseek_class.return_value = mock_model

        result = create_model(
            basemodel="deepseek/deepseek-chat",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatDeepSeek was called with correct params
        mock_deepseek_class.assert_called_once_with(
            model="deepseek-chat",  # Extracted from "deepseek/deepseek-chat"
            api_key="test-key",
            base_url="https://api.deepseek.com",
            temperature=0.7,
            timeout=30
        )
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_openai(self, mock_openai_class):
        """Test that OpenAI models use ChatOpenAI"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="openai/gpt-4",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatOpenAI was called with correct params
        mock_openai_class.assert_called_once_with(
            model="openai/gpt-4",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.7,
            timeout=30
        )
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_anthropic(self, mock_openai_class):
        """Test that Anthropic models use ChatOpenAI (via compatibility)"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="anthropic/claude-sonnet-4.5",
            api_key="test-key",
            base_url="https://api.anthropic.com/v1",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatOpenAI was used (Anthropic via OpenAI-compatible endpoint)
        mock_openai_class.assert_called_once()
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_generic_provider(self, mock_openai_class):
        """Test that unknown providers default to ChatOpenAI"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="custom/custom-model",
            api_key="test-key",
            base_url="https://api.custom.com",
            temperature=0.7,
            timeout=30
        )

        # Should fall back to ChatOpenAI for unknown providers
        mock_openai_class.assert_called_once()
        assert result == mock_model

    def test_create_model_deepseek_extracts_model_name(self):
        """Test that DeepSeek model name is extracted correctly"""
        with patch('agent.model_factory.ChatDeepSeek') as mock_class:
            create_model(
                basemodel="deepseek/deepseek-chat-v3.1",
                api_key="key",
                base_url="url",
                temperature=0,
                timeout=30
            )

            # Check that model param is just "deepseek-chat-v3.1"
            call_kwargs = mock_class.call_args[1]
            assert call_kwargs['model'] == "deepseek-chat-v3.1"
