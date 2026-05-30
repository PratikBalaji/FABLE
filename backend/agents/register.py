"""Wire agent roles into the global bus singleton."""
from ..core.bus import bus
from ..router.model_router import router
from .roles import AnalystAgent, CriticAgent, SynthesizerAgent


def register_all() -> None:
    analyst = AnalystAgent(router)
    critic = CriticAgent(router)
    synthesizer = SynthesizerAgent(router)

    bus.register("analyst", analyst)
    bus.register("critic", critic)
    bus.register("synthesizer", synthesizer)
