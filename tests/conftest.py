"""Configuração global de testes."""
import os

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Garante que variáveis de ambiente mínimas existam em todos os testes."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("LINKEDIN_PERSON_URN", "urn:li:person:TEST")
