#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the 200-article MNLM PoC corpus.

Usage: python scripts/build_mnlm_corpus.py

Output: docs/research/mnlm/poc/corpus_200.json

Each domain has 40 articles (10 seeds + 30 expansions).
Cross-domain structural pairs are annotated via monkey3_pair.
"""
from __future__ import annotations

import json
from pathlib import Path

CORPUS_PATH = Path("docs/research/mnlm/poc/corpus_200.json")

DOMAINS = {
    "physics": {
        "seeds": [
            "Bernoulli's principle",
            "Ohm's law",
            "Entropy",
            "Thermodynamics",
            "Fluid dynamics",
            "Maxwell's equations",
            "Special relativity",
            "Wave–particle duality",
            "Conservation of energy",
            "Electromagnetism",
        ],
        "expansion": [
            "Kinetic theory of gases",
            "Second law of thermodynamics",
            "Heat transfer",
            "Navier–Stokes equations",
            "Quantum mechanics",
            "Classical mechanics",
            "Newton's laws of motion",
            "Statistical mechanics",
            "Electromagnetic radiation",
            "Quantum field theory",
            "General relativity",
            "Speed of light",
            "Momentum",
            "Friction",
            "Gravity",
            "Magnetism",
            "Electric charge",
            "Electric current",
            "Thermal conduction",
            "Phase transition",
            "Brownian motion",
            "Laminar flow",
            "Turbulence",
            "Doppler effect",
            "Diffraction",
            "Interference (wave propagation)",
            "Optics",
            "Photon",
            "Electron",
            "Atomic theory",
        ],
    },
    "biology": {
        "seeds": [
            "Natural selection",
            "Cell membrane",
            "Action potential",
            "DNA replication",
            "Immune system",
            "Protein folding",
            "Homeostasis",
            "Synaptic plasticity",
            "Enzyme catalysis",
            "Capillary action",
        ],
        "expansion": [
            "Evolution",
            "Cell (biology)",
            "Mitosis",
            "Meiosis",
            "Photosynthesis",
            "Cellular respiration",
            "Gene expression",
            "Transcription (biology)",
            "Translation (biology)",
            "Central dogma of molecular biology",
            "Neurotransmission",
            "Neuron",
            "Synapse",
            "Cell cycle",
            "Lipid bilayer",
            "Active transport",
            "Passive transport",
            "Apoptosis",
            "Cell signaling",
            "Metabolism",
            "Glycolysis",
            "Krebs cycle",
            "Oxidative phosphorylation",
            "DNA",
            "RNA",
            "Mutation",
            "Genetic drift",
            "Speciation",
            "Ecology",
            "Population dynamics",
        ],
    },
    "mathematics": {
        "seeds": [
            "Graph theory",
            "Markov chain",
            "Fourier transform",
            "Fixed-point theorem",
            "Eigenvalues and eigenvectors",
            "Cellular automaton",
            "Information theory",
            "Bayes' theorem",
            "Topology",
            "Network theory",
        ],
        "expansion": [
            "Set theory",
            "Probability theory",
            "Linear algebra",
            "Calculus",
            "Differential equation",
            "Game theory",
            "Chaos theory",
            "Complex analysis",
            "Group theory",
            "Number theory",
            "Statistics",
            "Bayesian inference",
            "Entropy (information theory)",
            "Boolean algebra",
            "Combinatorics",
            "Category theory",
            "Graph coloring",
            "Random walk",
            "Central limit theorem",
            "Optimization (mathematics)",
            "Convex optimization",
            "Manifold",
            "Dimension",
            "Fractal",
            "Self-similarity",
            "Power law",
            "Statistical ensemble (mathematical physics)",
            "Dynamic system",
            "Perturbation theory",
            "Vector space",
        ],
    },
    "history": {
        "seeds": [
            "Industrial Revolution",
            "Scientific Revolution",
            "French Revolution",
            "Roman Empire",
            "Byzantine Empire",
            "Printing press",
            "Enlightenment (Age of Reason)",
            "Cold War",
            "Silk Road",
            "Renaissance",
        ],
        "expansion": [
            "Age of Discovery",
            "Industrialisation",
            "Columbian exchange",
            "Steam engine",
            "Factory system",
            "Mass production",
            "Feudalism",
            "Mercantilism",
            "Capitalism",
            "Protestant Reformation",
            "Spanish Empire",
            "British Empire",
            "Mongol Empire",
            "Ottoman Empire",
            "Han dynasty",
            "Tang dynasty",
            "Viking Age",
            "Bronze Age",
            "Iron Age",
            "Agricultural revolution",
            "Urbanization",
            "World War I",
            "World War II",
            "Treaty of Westphalia",
            "Congress of Vienna",
            "Decolonization",
            "Space Race",
            "Information Age",
            "Globalization",
            "Digital Revolution",
        ],
    },
    "philosophy": {
        "seeds": [
            "Epistemology",
            "Emergence",
            "Systems thinking",
            "Reductionism",
            "Analogy",
            "Cognitive dissonance",
            "Mental model",
            "Abstraction",
            "Causality",
            "Feedback",
        ],
        "expansion": [
            "Philosophy of science",
            "Ontology",
            "Metaphysics",
            "Logic",
            "Deductive reasoning",
            "Inductive reasoning",
            "Abductive reasoning",
            "Scientific method",
            "Paradigm",
            "Paradigm shift",
            "Heuristic",
            "Bayesian probability",
            "Confirmation bias",
            "Cognitive bias",
            "Rationality",
            "Bounded rationality",
            "Decision theory",
            "Complex system",
            "Self-organization",
            "Attractor",
            "Nonlinear system",
            "Agent-based model",
            "Distributed cognition",
            "Collective intelligence",
            "Swarm intelligence",
            "Connectionism",
            "Symbolic artificial intelligence",
            "Consciousness",
            "Free will",
            "Constructivism (philosophy of science)",
        ],
    },
}

# Cross-domain structural pairs from §1.3
MONKEY3_PAIRS: dict[str, str] = {
    "Bernoulli's principle": "Ohm's law",
    "Ohm's law": "Bernoulli's principle",
    "Natural selection": "Markov chain",
    "Markov chain": "Natural selection",
    "Entropy": "Entropy (information theory)",
    "Entropy (information theory)": "Entropy",
    "Immune system": "Feedback",
    "Feedback": "Immune system",
    "Industrial Revolution": "Cellular automaton",
    "Cellular automaton": "Industrial Revolution",
    "Synaptic plasticity": "Bayes' theorem",
    "Bayes' theorem": "Synaptic plasticity",
    "Roman Empire": "Network theory",
    "Network theory": "Roman Empire",
    "Printing press": "Graph theory",
    "Graph theory": "Printing press",
    "Protein folding": "Fixed-point theorem",
    "Fixed-point theorem": "Protein folding",
    "Fluid dynamics": "Eigenvalues and eigenvectors",
    "Eigenvalues and eigenvectors": "Fluid dynamics",
}

# Articles that are part of cross-domain pairs but might not be a seed
EXTRA_PAIR_ARTICLES = [
    "Entropy (information theory)",
]


def build_corpus() -> list[dict]:
    corpus: list[dict] = []
    seen_titles: set[str] = set()

    for domain, info in DOMAINS.items():
        titles = info["seeds"] + info["expansion"]
        for title in titles:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            monkey3_pair = MONKEY3_PAIRS.get(title)
            corpus.append({
                "title": title,
                "domain": domain,
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_').replace('–', '-')}",
                "monkey3_pair": monkey3_pair,
            })

    # Ensure extra pair articles are added even if not in any domain's list
    for title in EXTRA_PAIR_ARTICLES:
        if title not in seen_titles:
            seen_titles.add(title)
            monkey3_pair = MONKEY3_PAIRS.get(title)
            corpus.append({
                "title": title,
                "domain": "mathematics",  # information theory is mathematical
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "monkey3_pair": monkey3_pair,
            })

    return corpus


def main() -> None:
    corpus = build_corpus()
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(corpus)} articles to {CORPUS_PATH}")


if __name__ == "__main__":
    main()
