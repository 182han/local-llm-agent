"""
赵怡涵 C4D · 本地大模型 Agent 技能
Local LLM agent skill: a local Gemma model builds interactive maps.

Public surface
--------------
    PlaceAgent          the agent itself (structured JSON + native tool calling)
    OllamaClient        dependency-free client for a local Ollama server
    render_leaflet_map  self-contained interactive Leaflet HTML renderer
    device_profile      real machine facts
"""

from .ollama_client import ChatResult, OllamaClient, OllamaError, check_server
from .place_agent import GenerationResult, PlaceAgent, ToolLoopResult
from .map_renderer import render_leaflet_map
from .tools import Marker, Session, device_profile
from .geo import haversine_m, spread_km, cluster_radius_km

__version__ = "1.0.0"
__all__ = [
    "PlaceAgent", "GenerationResult", "ToolLoopResult",
    "OllamaClient", "OllamaError", "ChatResult", "check_server",
    "render_leaflet_map", "Marker", "Session", "device_profile",
    "haversine_m", "spread_km", "cluster_radius_km", "__version__",
]
