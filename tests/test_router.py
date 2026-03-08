from core.model_router import RuleBasedModelRouter


class _DummyModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def model_name(self) -> str:
        return self._name

    def generate(self, messages, temperature=0.7):
        return "ok"


def test_router_keyword_to_large():
    router = RuleBasedModelRouter(
        small_model=_DummyModel("small"),
        large_model=_DummyModel("large"),
        complexity_threshold=3,
        force_large_keywords=("架构",),
    )
    model = router.select_model("请帮我做一次系统架构设计")
    assert model.model_name == "large"


def test_router_default_small():
    router = RuleBasedModelRouter(
        small_model=_DummyModel("small"),
        large_model=_DummyModel("large"),
        complexity_threshold=3,
        force_large_keywords=("架构",),
    )
    model = router.select_model("你好")
    assert model.model_name == "small"
