import litellm
import pytest

from app.llm_gateway import AllProvidersUnavailable, LLMGateway, make_simulated_error
from tests.conftest import TEST_KEYS

MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
K1, K2 = TEST_KEYS


def _rate_limit():
    return litellm.RateLimitError(message="quota", llm_provider="groq", model="groq/test-model")


async def test_first_key_answers(make_settings, fake_llm):
    gw = LLMGateway(make_settings(), cache_enabled=False)
    res = await gw.complete(MSGS)
    assert res.key_id == "key_1" and res.fallback_attempts == 0 and not res.cache_hit
    assert fake_llm.calls == [K1]


@pytest.mark.parametrize(
    "exc",
    [
        litellm.RateLimitError(message="429", llm_provider="groq", model="m"),
        litellm.InternalServerError(message="500", llm_provider="groq", model="m"),
        litellm.ServiceUnavailableError(message="503", llm_provider="groq", model="m"),
        litellm.APIError(status_code=502, message="502", llm_provider="groq", model="m"),
        litellm.Timeout(message="timeout", model="m", llm_provider="groq"),
        litellm.APIConnectionError(message="conn", llm_provider="groq", model="m"),
        litellm.AuthenticationError(message="401", llm_provider="groq", model="m"),
        litellm.BadRequestError(message="quota exceeded", model="m", llm_provider="groq"),
    ],
    ids=lambda e: type(e).__name__,
)
async def test_failover_on_provider_errors(make_settings, fake_llm, exc):
    fake_llm.behaviours[K1] = exc
    gw = LLMGateway(make_settings(), cache_enabled=False)
    res = await gw.complete(MSGS)
    assert res.key_id == "key_2" and res.fallback_attempts == 1
    assert fake_llm.calls == [K1, K2]


async def test_empty_reply_fails_over(make_settings, fake_llm):
    fake_llm.behaviours[K1] = "empty"
    gw = LLMGateway(make_settings(), cache_enabled=False)
    res = await gw.complete(MSGS)
    assert res.key_id == "key_2" and res.reply


async def test_all_keys_fail(make_settings, fake_llm):
    fake_llm.behaviours = {K1: _rate_limit(), K2: _rate_limit()}
    gw = LLMGateway(make_settings(), cache_enabled=False)
    with pytest.raises(AllProvidersUnavailable):
        await gw.complete(MSGS)
    assert fake_llm.calls == [K1, K2]  # bounded: exactly one attempt per key


async def test_simulated_failure_never_calls_failed_key(make_settings, fake_llm):
    gw = LLMGateway(make_settings(), cache_enabled=False)
    res = await gw.complete(MSGS, simulated_failures={"key_1": 429})
    assert res.key_id == "key_2" and res.fallback_attempts == 1
    assert fake_llm.calls == [K2]


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_simulated_errors_are_litellm_exceptions(status):
    exc = make_simulated_error(status, "groq/test-model", "key_1")
    assert exc.status_code == status
    assert isinstance(exc, litellm.exceptions.APIError | litellm.RateLimitError | litellm.InternalServerError
                      | litellm.ServiceUnavailableError)


async def test_cooldown_skips_rate_limited_key(make_settings, fake_llm):
    fake_llm.behaviours[K1] = _rate_limit()
    gw = LLMGateway(make_settings(key_cooldown_seconds=60), cache_enabled=False)
    await gw.complete(MSGS)  # key_1 fails -> cooldown
    fake_llm.calls.clear()
    fake_llm.behaviours.clear()
    res = await gw.complete(MSGS)
    assert fake_llm.calls == [K2]  # key_1 skipped while cooling down
    assert res.key_id == "key_2" and res.fallback_attempts == 1


async def test_cooldown_last_resort_when_all_cooling(make_settings, fake_llm):
    fake_llm.behaviours = {K1: _rate_limit(), K2: _rate_limit()}
    gw = LLMGateway(make_settings(key_cooldown_seconds=60), cache_enabled=False)
    with pytest.raises(AllProvidersUnavailable):
        await gw.complete(MSGS)
    fake_llm.behaviours.clear()
    res = await gw.complete(MSGS)  # both cooling -> still tried as a last resort
    assert res.key_id == "key_1"


async def test_simulation_ignores_cooldown(make_settings, fake_llm):
    fake_llm.behaviours[K1] = _rate_limit()
    gw = LLMGateway(make_settings(key_cooldown_seconds=60), cache_enabled=False)
    await gw.complete(MSGS)  # real 429 puts key_1 on cooldown
    fake_llm.behaviours.clear()
    fake_llm.calls.clear()
    res = await gw.complete(MSGS, simulated_failures={"key_2": 500})
    assert res.key_id == "key_1" and res.fallback_attempts == 0  # contract table unaffected


def test_redaction_hides_keys(make_settings):
    gw = LLMGateway(make_settings(), cache_enabled=False)
    assert K1 not in gw._redact(f"https://api.example.com/?key={K1}")
