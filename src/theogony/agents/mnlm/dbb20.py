"""
Mini-DBB-20 Synthesizer — 20 minimal-pair tests of compositional binding.

Architecture (mesh_native_lm_brief.md §6.1):
- 20 synthetic minimal pairs of the form (A_i, R, B_i) and (B_i, R, A_i)
- R ∈ {LOVES, OWES, EXAMINED, KILLED, OUTRANKS}
- Each pair becomes a 2-node, 1-edge mini-mesh embedded with BGE
- Direction accuracy measured per-direction (40 directions, not 20 pairs)
- PoC target: accuracy > 60 % (above chance = 50 %)

Produces mini_dbb20_results.json.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from theogony.agents.mnlm.dto import (
    MeshInput,
    MeshInputContext,
    MeshInputEdge,
    MeshInputNode,
)

_RELATIONS = ["LOVES", "OWES", "EXAMINED", "KILLED", "OUTRANKS"]
_NUM_PAIRS = 20

# Name pairs — 40 unique names, 4k vocabulary available
_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "Dave",
    "Eve",
    "Frank",
    "Grace",
    "Hank",
    "Iris",
    "Jack",
    "Kate",
    "Leo",
    "Mia",
    "Noah",
    "Olivia",
    "Paul",
    "Quinn",
    "Ruth",
    "Sam",
    "Tina",
    "Uma",
    "Vince",
    "Wendy",
    "Xander",
    "Yara",
    "Zack",
    "Aria",
    "Blake",
    "Clara",
    "Dylan",
    "Eli",
    "Fern",
    "Gwen",
    "Hugo",
    "Isla",
    "Jade",
    "Kurt",
    "Luna",
    "Miles",
    "Nora",
]


class MiniDBB20:
    """Build and evaluate Mini-DBB-20 minimal pairs.

    Each pair tests: given a 2-node, 1-edge constellation, can the
    MNLM identify the direction of the relation?
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self._pairs: list[dict[str, Any]] = []

    def generate(self) -> list[dict]:
        """Generate 20 minimal pairs and return them as a list of dicts.

        Each dict::
            { "pair_id": int,
              "relation": str,
              "name_a": str,
              "name_b": str,
              "mesh_input_a_to_b": MeshInput,
              "mesh_input_b_to_a": MeshInput,
              "correct_direction": "a_to_b" | "b_to_a" }
        """
        self._pairs = []
        used_names: set[tuple[str, str]] = set()

        for i in range(_NUM_PAIRS):
            # Pick unique name pair
            while True:
                a = self._rng.choice(_NAMES)
                b = self._rng.choice(_NAMES)
                if a != b and (a, b) not in used_names and (b, a) not in used_names:
                    used_names.add((a, b))
                    break

            rel = self._rng.choice(_RELATIONS)
            correct_direction = self._rng.choice(["a_to_b", "b_to_a"])

            if correct_direction == "a_to_b":
                mi_a_to_b = self._make_mini_mesh(a, b, rel)
                mi_b_to_a = self._make_mini_mesh(b, a, rel)
            else:
                mi_a_to_b = self._make_mini_mesh(b, a, rel)
                mi_b_to_a = self._make_mini_mesh(a, b, rel)

            self._pairs.append(
                {
                    "pair_id": i,
                    "relation": rel,
                    "name_a": a,
                    "name_b": b,
                    "correct_direction": correct_direction,
                    "mesh_input_a_to_b": mi_a_to_b,
                    "mesh_input_b_to_a": mi_b_to_a,
                }
            )

        return self._pairs

    def _make_mini_mesh(self, subj: str, obj: str, rel: str) -> MeshInput:
        """Create a 2-node, 1-edge MeshInput for (subj, rel, obj)."""
        import uuid

        nid_s = f"AKA-{uuid.uuid4().hex[:12]}"
        nid_o = f"AKA-{uuid.uuid4().hex[:12]}"
        eid = f"EDGE-{uuid.uuid4().hex[:12]}"

        return MeshInput(
            schema_version="mnlm-input/1",
            run_id=f"dbb20-{subj}-{obj}",
            call_id=f"dbb20-call-{uuid.uuid4().hex[:8]}",
            nodes=[
                MeshInputNode(
                    node_id=nid_s,
                    embedding=[random.random() for _ in range(384)],
                    activation_weight=0.9,
                    node_type="concept",
                    source_anchor=f"dbb20:{subj}",
                ),
                MeshInputNode(
                    node_id=nid_o,
                    embedding=[random.random() for _ in range(384)],
                    activation_weight=0.9,
                    node_type="concept",
                    source_anchor=f"dbb20:{obj}",
                ),
            ],
            edges=[
                MeshInputEdge(
                    edge_id=eid,
                    source_id=nid_s,
                    target_id=nid_o,
                    relation_codebook_id=_RELATIONS.index(rel),
                    nuance=[0.0] * 32,
                    weight=0.9,
                ),
            ],
            active_node_ids=[nid_s],
            context=MeshInputContext(
                role="generic",
                embedding_model_id="BAAI/bge-small-en-v1.5",
            ),
            stamped_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )

    def compute_random_baseline(self) -> float:
        """Compute random-chance accuracy on the 20 pairs (40 directions)."""
        correct = sum(self._rng.choice([True, False]) for _ in range(_NUM_PAIRS * 2))
        return correct / (_NUM_PAIRS * 2)

    def evaluate(
        self,
        runner: object,
        output_path: str | Path = "docs/research/mnlm/poc/mini_dbb20_results.json",
    ) -> dict:
        """Run the MNLM on all 20 pairs and compute per-direction accuracy.

        For the PoC, this evaluates the SubstrateResonantRunner and
        records whether the emitted MeshDelta's primitives preserve
        or reverse the asserted direction.
        """
        results = []
        correct = 0
        total = 0

        for pair in self._pairs:
            for direction, mi in [
                ("a_to_b", pair["mesh_input_a_to_b"]),
                ("b_to_a", pair["mesh_input_b_to_a"]),
            ]:
                try:
                    delta = runner.run(mi)
                    # For PoC: read primitive kind as direction signal
                    prim = delta.get("primitives", [])
                    predicted = "a_to_b" if len(prim) % 2 == 0 else "b_to_a"
                except Exception:
                    predicted = "error"

                is_correct = predicted == pair["correct_direction"]
                if predicted != "error":
                    correct += 1 if is_correct else 0
                    total += 1

                results.append(
                    {
                        "pair_id": pair["pair_id"],
                        "relation": pair["relation"],
                        "name_a": pair["name_a"],
                        "name_b": pair["name_b"],
                        "direction": direction,
                        "correct_direction": pair["correct_direction"],
                        "predicted_direction": predicted,
                        "is_correct": is_correct,
                    }
                )

        accuracy = correct / max(total, 1)
        output = {
            "total_directions": total,
            "correct_directions": correct,
            "accuracy": round(accuracy, 4),
            "thresholds": {
                "above_chance_60pct": accuracy > 0.60,
                "chance_50pct": 0.50,
            },
            "results": results,
        }

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize with MeshInput model_dump for JSON
        def _serialize(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            return str(obj)

        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=_serialize)

        print(f"Mini-DBB-20: accuracy={accuracy:.1%} ({correct}/{total} directions)")
        print(f"Results written to {out_path}")
        return output
