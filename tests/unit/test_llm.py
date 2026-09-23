from __future__ import annotations

import pytest
import respx
from httpx import Response

from agevolamatch.matching.engine import match_incentive
from agevolamatch.matching.llm.base import LLMProvider
from agevolamatch.matching.llm.factory import get_llm_provider
from agevolamatch.matching.llm.ollama_provider import DEFAULT_HOST, OllamaProvider
from agevolamatch.matching.llm.openai_compatible_provider import (
    DEFAULT_BASE_URL,
    OpenAICompatibleProvider,
)
from agevolamatch.matching.llm.requirements import (
    enrich_with_llm_requirements,
    extract_requirements,
)
from agevolamatch.models.company_profile import AtecoCode, CompanyProfile
from agevolamatch.models.enums import CompanySize, Region


class FakeProvider(LLMProvider):
    def __init__(self, response: str = "", raises: bool = False):
        self.response = response
        self.raises = raises
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.raises:
            raise RuntimeError("boom")
        return self.response


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "ateco_codes": [AtecoCode(code="62.01")],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


class TestFactory:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("AGEVOLAMATCH_LLM_PROVIDER", raising=False)
        assert get_llm_provider() is None

    def test_empty_string_is_treated_as_disabled(self, monkeypatch):
        monkeypatch.setenv("AGEVOLAMATCH_LLM_PROVIDER", "")
        assert get_llm_provider() is None

    def test_ollama_selected(self, monkeypatch):
        monkeypatch.setenv("AGEVOLAMATCH_LLM_PROVIDER", "ollama")
        assert isinstance(get_llm_provider(), OllamaProvider)

    def test_openai_selected(self, monkeypatch):
        monkeypatch.setenv("AGEVOLAMATCH_LLM_PROVIDER", "openai")
        assert isinstance(get_llm_provider(), OpenAICompatibleProvider)

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("AGEVOLAMATCH_LLM_PROVIDER", "not-a-real-provider")
        with pytest.raises(ValueError, match="Unknown"):
            get_llm_provider()


class TestExtractRequirements:
    def test_empty_description_returns_no_requirements_without_calling_provider(self):
        provider = FakeProvider()
        assert extract_requirements(provider, "") == []
        assert provider.prompts == []

    def test_parses_bullet_list(self):
        provider = FakeProvider(response="- Impresa costituita da meno di 5 anni\n- Sede in Lazio\n")
        result = extract_requirements(provider, "Some incentive description")
        assert result == ["Impresa costituita da meno di 5 anni", "Sede in Lazio"]

    def test_parses_numbered_list(self):
        provider = FakeProvider(response="1. Requisito A\n2) Requisito B")
        result = extract_requirements(provider, "description")
        assert result == ["Requisito A", "Requisito B"]

    def test_no_requirements_marker_returns_empty_list(self):
        provider = FakeProvider(response="Nessun requisito aggiuntivo rilevato")
        assert extract_requirements(provider, "description") == []

    def test_caps_at_max_items(self):
        lines = "\n".join(f"- Requisito {i}" for i in range(10))
        provider = FakeProvider(response=lines)
        result = extract_requirements(provider, "description", max_items=3)
        assert len(result) == 3


class TestProviderConfigReadPerInstance:
    """Regression test: defaults must be read from the environment at
    instantiation time (dataclass field(default_factory=...)), not once at
    module-import time (a plain `= os.environ.get(...)` default) - the latter
    would freeze whatever the env var was when the module first happened to
    be imported, ignoring a later .env load or a changed setting."""

    def test_ollama_picks_up_env_var_set_after_import(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://custom-host:1234")
        assert OllamaProvider().host == "http://custom-host:1234"

    def test_openai_picks_up_env_var_set_after_import(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "some-key-set-later")
        assert OpenAICompatibleProvider().api_key == "some-key-set-later"


class TestOllamaProviderHttp:
    @respx.mock
    def test_complete_calls_generate_endpoint(self):
        route = respx.post(f"{DEFAULT_HOST}/api/generate").mock(
            return_value=Response(200, json={"response": "- Some requirement"})
        )
        provider = OllamaProvider(host=DEFAULT_HOST)
        result = provider.complete("prompt")
        assert route.called
        assert result == "- Some requirement"


class TestOpenAICompatibleProviderHttp:
    def test_raises_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        provider = OpenAICompatibleProvider(api_key="")
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            provider.complete("prompt")

    @respx.mock
    def test_complete_calls_chat_completions_endpoint(self):
        respx.post(f"{DEFAULT_BASE_URL}/chat/completions").mock(
            return_value=Response(
                200, json={"choices": [{"message": {"content": "- Some requirement"}}]}
            )
        )
        provider = OpenAICompatibleProvider(api_key="fake-key", base_url=DEFAULT_BASE_URL)
        result = provider.complete("prompt")
        assert result == "- Some requirement"


class TestEnrichWithLlmRequirements:
    def test_appends_llm_prefixed_unverifiable_items(self, incentive_factory):
        incentive = incentive_factory(ateco_all_sectors=True, description="Some free text description")
        result = match_incentive(incentive, make_profile())
        provider = FakeProvider(response="- Requisito extra detectado")

        enriched = enrich_with_llm_requirements([result], provider)

        assert any("[LLM] Requisito extra detectado" in u for u in enriched[0].explanation.unverifiable)
        # original result is untouched (pydantic models are copied, not mutated)
        assert not any("[LLM]" in u for u in result.explanation.unverifiable)

    def test_ineligible_results_are_never_sent_to_the_llm(self, incentive_factory):
        incentive = incentive_factory(regions=["Sicilia"])  # region mismatch -> ineligible
        result = match_incentive(incentive, make_profile())
        provider = FakeProvider(response="- Should not appear")

        enriched = enrich_with_llm_requirements([result], provider)

        assert provider.prompts == []
        assert enriched[0] == result

    def test_respects_top_n_limit(self, incentive_factory):
        results = [
            match_incentive(incentive_factory(source_id=str(i), ateco_all_sectors=True, description="text"), make_profile())
            for i in range(5)
        ]
        provider = FakeProvider(response="- X")

        enrich_with_llm_requirements(results, provider, top_n=2)

        assert len(provider.prompts) == 2

    def test_provider_failure_is_logged_and_does_not_raise(self, incentive_factory):
        incentive = incentive_factory(ateco_all_sectors=True, description="text")
        result = match_incentive(incentive, make_profile())
        provider = FakeProvider(raises=True)

        enriched = enrich_with_llm_requirements([result], provider)

        assert enriched[0] == result  # unchanged, no crash

    def test_no_description_skips_the_call_but_does_not_crash(self, incentive_factory):
        incentive = incentive_factory(ateco_all_sectors=True, description=None)
        result = match_incentive(incentive, make_profile())
        provider = FakeProvider(response="- X")

        enriched = enrich_with_llm_requirements([result], provider)

        assert enriched[0].explanation.unverifiable == result.explanation.unverifiable
