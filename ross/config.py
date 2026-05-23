"""Central env/config. Loads .env once. No magic."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_RAW = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)

# LLM
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_FAST = os.getenv("ROSS_MODEL_FAST", "google/gemini-2.5-flash")
# "deep" model for the reasoning agents (issue spotter / strategist / adversary
# / harvey). Default = Flash WITH thinking (fast + smart). Set to gemini-2.5-pro
# for maximum depth at the cost of latency.
MODEL_DEEP = os.getenv("ROSS_MODEL_DEEP", "google/gemini-2.5-flash")
# reasoning effort for the deep agents: low | medium | high
DEEP_EFFORT = os.getenv("ROSS_DEEP_EFFORT", "low")

# ClickHouse
CH = dict(
    host=os.getenv("CLICKHOUSE_HOST", ""),
    port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
    username=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", ""),
    database=os.getenv("CLICKHOUSE_DATABASE", "ross"),
    secure=os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true",
)

COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN", "")
NIMBLE_API_KEY = os.getenv("NIMBLE_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")  # Tier-2 web fetch (domain-restricted)
DD_API_KEY = os.getenv("DD_API_KEY", "")
DD_SITE = os.getenv("DD_SITE", "datadoghq.com")

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384-dim, local, ONNX
EMBED_DIM = 384
