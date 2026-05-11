"""
Mini-Monkey-3 Emergent-Knowledge Evaluator (mnlm_poc_brief.md §1.3).

10 cross-domain structural pairs, qualitatively rated by 2 human raters
on a 0–3 Likert scale. Tests the project's central thesis: can the MNLM
synthesise cross-source structure that text-RAG cannot reach.

The 10 pairs are the cross-domain structural pairs from corpus_200.json
§1.3. Each pair tests whether the MNLM can infer structural isomorphism
across two unrelated domains.
"""

from __future__ import annotations

import random
from pathlib import Path

# The 10 Monkey-3 cross-domain pairs from §1.3 of the PoC brief
MONKEY3_PAIRS: list[dict[str, str]] = [
    {
        "pair_id": 1,
        "domain_a": "Physics (fluid)",
        "concept_a": "Bernoulli's principle",
        "domain_b": "Physics (electrical)",
        "concept_b": "Ohm's law",
        "structural_isomorphism": "Pressure/voltage drives flow against resistance",
    },
    {
        "pair_id": 2,
        "domain_a": "Biology",
        "concept_a": "Natural selection",
        "domain_b": "Mathematics",
        "concept_b": "Markov chain",
        "structural_isomorphism": "State transitions with differential fitness/probability",
    },
    {
        "pair_id": 3,
        "domain_a": "Physics (thermodynamics)",
        "concept_a": "Entropy",
        "domain_b": "Mathematics",
        "concept_b": "Entropy (information theory)",
        "structural_isomorphism": "Disorder / uncertainty as a state function",
    },
    {
        "pair_id": 4,
        "domain_a": "Biology",
        "concept_a": "Immune system",
        "domain_b": "Philosophy/Cognition",
        "concept_b": "Feedback",
        "structural_isomorphism": "Adaptive response loop with memory",
    },
    {
        "pair_id": 5,
        "domain_a": "History",
        "concept_a": "Industrial Revolution",
        "domain_b": "Mathematics",
        "concept_b": "Cellular automaton",
        "structural_isomorphism": "Local rules propagating systemic phase transition",
    },
    {
        "pair_id": 6,
        "domain_a": "Biology",
        "concept_a": "Synaptic plasticity",
        "domain_b": "Mathematics",
        "concept_b": "Bayes' theorem",
        "structural_isomorphism": "Belief/weight update proportional to evidence",
    },
    {
        "pair_id": 7,
        "domain_a": "History",
        "concept_a": "Roman Empire",
        "domain_b": "Mathematics",
        "concept_b": "Network theory",
        "structural_isomorphism": "Hub-and-spoke topology, single-point-of-failure dynamics",
    },
    {
        "pair_id": 8,
        "domain_a": "History",
        "concept_a": "Printing press",
        "domain_b": "Mathematics",
        "concept_b": "Graph theory",
        "structural_isomorphism": "Accelerated diffusion across sparse→dense graphs",
    },
    {
        "pair_id": 9,
        "domain_a": "Biology",
        "concept_a": "Protein folding",
        "domain_b": "Mathematics",
        "concept_b": "Fixed-point theorem",
        "structural_isomorphism": "System converging to minimum-energy stable state",
    },
    {
        "pair_id": 10,
        "domain_a": "Physics (fluid)",
        "concept_a": "Fluid dynamics",
        "domain_b": "Mathematics",
        "concept_b": "Eigenvalues and eigenvectors",
        "structural_isomorphism": "Stable flow modes as principal directions",
    },
]

LIKERT_LABELS = {
    0: "No correspondence — answer unrelated or hallucinated",
    1: "Weak correspondence — tangential relation but misses the isomorphism",
    2: "Moderate correspondence — partial structural match, some gaps",
    3: "Strong correspondence — correctly identifies the structural isomorphism",
}


class MiniMonkey3:
    """Mini-Monkey-3 emergent-knowledge evaluator.

    Generates rating sheets for 2 human raters, collects results,
    and computes inter-rater reliability.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self._pairs = MONKEY3_PAIRS
        self._ratings: dict[str, list[dict]] = {}

    def pairs(self) -> list[dict]:
        return self._pairs

    def generate_rating_sheet(
        self,
        output_path: str | Path = "docs/research/mnlm/poc/mini_monkey3_rating_sheet.md",
    ) -> str:
        """Generate a human-readable rating sheet for the 10 pairs.

        Each pair presents the two concepts and asks the rater to judge
        the MNLM output on a 0–3 Likert scale.
        """
        lines = [
            "# Mini-Monkey-3 Rating Sheet",
            "",
            "Rate each pair on a 0–3 Likert scale:",
            "",
        ]
        for label, desc in sorted(LIKERT_LABELS.items()):
            lines.append(f"- **{label}**: {desc}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for pair in self._pairs:
            lines.extend(
                [
                    f"## Pair {pair['pair_id']}: {pair['concept_a']} ↔ {pair['concept_b']}",
                    "",
                    f"- **Domain A**: {pair['domain_a']}",
                    f"- **Concept A**: {pair['concept_a']}",
                    f"- **Domain B**: {pair['domain_b']}",
                    f"- **Concept B**: {pair['concept_b']}",
                    f"- **Structural isomorphism**: {pair['structural_isomorphism']}",
                    "",
                    "### MNLM output:",
                    "",
                    "_[To be filled – MNLM response for this pair]_",
                    "",
                    "### Baseline (text-RAG 1.5B) output:",
                    "",
                    "_[To be filled – text-RAG response]_",
                    "",
                    "### Rating (0–3):",
                    "",
                    "- **Rater 1**: __ / 3",
                    "- **Rater 2**: __ / 3",
                    "",
                    "### Notes:",
                    "",
                    "_",
                    "",
                    "---",
                    "",
                ]
            )

        content = "\n".join(lines)
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"Rating sheet written to {out_path}")
        return content

    def record_rating(
        self,
        pair_id: int,
        rater_id: str,
        score: int,
        notes: str = "",
    ) -> None:
        """Record one rater's score for one pair."""
        if rater_id not in self._ratings:
            self._ratings[rater_id] = []
        self._ratings[rater_id].append(
            {
                "pair_id": pair_id,
                "score": score,
                "notes": notes,
            }
        )

    def compute_summary(
        self,
        output_path: str | Path = "docs/research/mnlm/poc/mini_monkey3_results.md",
    ) -> dict:
        """Compute inter-rater reliability and mean ratings.

        Returns dict with per-pair and aggregate scores.
        Also writes a human-readable Markdown summary.
        """
        rater_ids = list(self._ratings.keys())
        if len(rater_ids) < 2:
            print(f"Warning: only {len(rater_ids)} rater(s) — need 2 for full evaluation")

        # Build per-pair scores
        per_pair: dict[int, list[int]] = {}
        for _rater_id, ratings in self._ratings.items():
            for r in ratings:
                per_pair.setdefault(r["pair_id"], []).append(r["score"])

        # Compute mean per pair and overall
        pair_results = []
        total_scores = 0
        total_count = 0
        for pair in self._pairs:
            pid = pair["pair_id"]
            scores = per_pair.get(pid, [])
            mean = sum(scores) / max(len(scores), 1)
            pair_results.append(
                {
                    "pair_id": pid,
                    "concept_a": pair["concept_a"],
                    "concept_b": pair["concept_b"],
                    "isomorphism": pair["structural_isomorphism"],
                    "scores": scores,
                    "mean_score": round(mean, 2),
                }
            )
            total_scores += sum(scores)
            total_count += len(scores)

        overall_mean = total_scores / max(total_count, 1)

        # Simple agreement: % of pairs where scores within 1 point
        agreements = 0
        total_compared = 0
        for pr in pair_results:
            if len(pr["scores"]) >= 2:
                total_compared += 1
                if abs(pr["scores"][0] - pr["scores"][1]) <= 1:
                    agreements += 1

        agreement_pct = agreements / max(total_compared, 1)

        # Build output
        output = {
            "num_pairs": len(self._pairs),
            "num_raters": len(rater_ids),
            "rater_ids": rater_ids,
            "overall_mean_score": round(overall_mean, 2),
            "agreement_within_1": round(agreement_pct, 2),
            "pair_results": pair_results,
            "likert_scale": LIKERT_LABELS,
        }

        # Write Markdown
        lines = [
            "# Mini-Monkey-3 Results",
            "",
            f"- **Pairs evaluated**: {len(self._pairs)}",
            f"- **Raters**: {', '.join(rater_ids)}",
            f"- **Overall mean score**: {overall_mean:.2f} / 3",
            f"- **Agreement (within 1 point)**: {agreement_pct:.0%}",
            "",
            "## Per-pair results",
            "",
            "| Pair | Concept A | Concept B | Scores | Mean |",
            "|------|-----------|-----------|--------|------|",
        ]
        for pr in pair_results:
            scores_str = ", ".join(str(s) for s in pr["scores"])
            lines.append(
                f"| {pr['pair_id']} | {pr['concept_a']} | {pr['concept_b']} "
                f"| {scores_str} | {pr['mean_score']} |"
            )

        lines.extend(
            [
                "",
                "## Likert scale",
                "",
            ]
        )
        for label, desc in sorted(LIKERT_LABELS.items()):
            lines.append(f"- **{label}**: {desc}")
        lines.append("")

        content = "\n".join(lines)
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"Results written to {out_path}")

        return output
