import litellm

from app.cache import setup_cache
from app.llm_gateway import LLMGateway
from tests.conftest import TEST_KEYS

K1, K2 = TEST_KEYS


def _msgs(text: str):
    return [{"role": "system", "content": "sys"}, {"role": "user", "content": text}]


def test_cache_key_ignores_api_key(make_settings):
    setup_cache(make_settings())
    common = dict(model="groq/test-model", messages=_msgs("hi"), temperature=0, max_tokens=64)
    assert litellm.cache.get_cache_key(**common, api_key=K1) == litellm.cache.get_cache_key(**common, api_key=K2)
    # ...but model and messages are part of it
    assert litellm.cache.get_cache_key(**common) != litellm.cache.get_cache_key(
        **{**common, "messages": _msgs("hi!")}
    )
    assert litellm.cache.get_cache_key(**common) != litellm.cache.get_cache_key(**{**common, "model": "groq/other"})


async def test_disk_cache_hit_identical_reply_and_usage(make_settings, fake_llm):
    settings = make_settings()
    assert setup_cache(settings) == "disk"
    gw = LLMGateway(settings)
    live = await gw.complete(_msgs("What is the capital of France?"))
    hit = await gw.complete(_msgs("What is the capital of France?"))
    assert not live.cache_hit and hit.cache_hit
    assert hit.reply == live.reply
    assert (hit.input_tokens, hit.output_tokens) == (live.input_tokens, live.output_tokens)
    assert hit.key_id is None and hit.fallback_attempts == 0
    assert fake_llm.calls == [K1, K1]  # LiteLLM short-circuits inside acompletion


async def test_cache_hit_regardless_of_answering_key(make_settings, fake_llm):
    settings = make_settings()
    setup_cache(settings)
    gw = LLMGateway(settings)
    first = await gw.complete(_msgs("q"), simulated_failures={"key_1": 429})  # answered by key_2
    assert first.key_id == "key_2"
    again = await gw.complete(_msgs("q"))  # tried with key_1, served from cache
    assert again.cache_hit and again.reply == first.reply


async def test_different_message_is_never_cached(make_settings, fake_llm):
    settings = make_settings()
    setup_cache(settings)
    gw = LLMGateway(settings)
    await gw.complete(_msgs("alpha"))
    other = await gw.complete(_msgs("beta"))
    assert not other.cache_hit


async def test_disk_cache_survives_restart(make_settings, fake_llm):
    settings = make_settings()
    setup_cache(settings)
    live = await LLMGateway(settings).complete(_msgs("persist me"))
    litellm.cache = None
    setup_cache(settings)  # "restart": new Cache object over the same directory
    hit = await LLMGateway(settings).complete(_msgs("persist me"))
    assert hit.cache_hit and hit.reply == live.reply


async def test_simulation_bypasses_cache_read(make_settings, fake_llm):
    settings = make_settings()
    setup_cache(settings)
    gw = LLMGateway(settings)
    await gw.complete(_msgs("cached question"))
    res = await gw.complete(_msgs("cached question"), simulated_failures={"key_1": 429})
    assert not res.cache_hit and res.key_id == "key_2"


async def test_local_cache_type(make_settings, fake_llm):
    settings = make_settings(cache_type="local")
    assert setup_cache(settings) == "local"
    gw = LLMGateway(settings)
    await gw.complete(_msgs("x"))
    assert (await gw.complete(_msgs("x"))).cache_hit
