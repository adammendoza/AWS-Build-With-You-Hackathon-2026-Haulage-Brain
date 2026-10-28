from pathlib import Path

from load_quoting_swarm.config import load_fleet_config
from load_quoting_swarm.grounding import DemoGrounding
from load_quoting_swarm.inference import DemoInference
from load_quoting_swarm.memory import ScopedMemory
from load_quoting_swarm.pipeline import QuotePipeline


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_seeds_role_scoped_fleet_context() -> None:
    memory = ScopedMemory()
    fleet = load_fleet_config(ROOT / "config/fleet.demo.json")

    QuotePipeline(
        fleet=fleet,
        grounding=DemoGrounding(),
        inference=DemoInference(),
        memory=memory,
    )

    pricing = memory.recall(
        scope="/pricing", metadata_key="vehicle_type", metadata_value="Luton Van"
    )
    compliance = memory.recall(
        scope="/compliance", metadata_key="vehicle_type", metadata_value="Luton Van"
    )
    fleet_fit = memory.recall(
        scope="/fleet-fit", metadata_key="vehicle_type", metadata_value="Luton Van"
    )

    assert any("MPG" in item.value for item in pricing)
    assert any("max payload" in item.value for item in compliance)
    assert any("DEMO-LUTON-01" in item.value for item in fleet_fit)
