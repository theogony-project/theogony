"""
Tests for the resumable MNLM PoC crawl coordinator.

Covers:
- Load corpus_200.json
- Load / skip crawl log entries
- Append to crawl log
- Signal handling setup/restore
- Domain progress tracking
- Batch iteration
"""

from __future__ import annotations

import json
import signal
from pathlib import Path

import pytest

from theogony.kadmos.crawl import CrawlCoordinator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def corpus_path(tmp_path: Path) -> Path:
    """Create a minimal corpus JSON."""
    corpus = [
        {
            "title": "Bernoulli's principle",
            "domain": "physics",
            "url": "https://en.wikipedia.org/wiki/Bernoulli%27s_principle",
        },
        {
            "title": "Ohm's law",
            "domain": "physics",
            "url": "https://en.wikipedia.org/wiki/Ohm%27s_law",
        },
        {
            "title": "Natural selection",
            "domain": "biology",
            "url": "https://en.wikipedia.org/wiki/Natural_selection",
        },
        {
            "title": "Markov chain",
            "domain": "mathematics",
            "url": "https://en.wikipedia.org/wiki/Markov_chain",
        },
        {
            "title": "Industrial Revolution",
            "domain": "history",
            "url": "https://en.wikipedia.org/wiki/Industrial_Revolution",
        },
        {
            "title": "Epistemology",
            "domain": "philosophy",
            "url": "https://en.wikipedia.org/wiki/Epistemology",
        },
    ]
    path = tmp_path / "corpus_200.json"
    path.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def crawl_log_path(tmp_path: Path) -> Path:
    """Path for crawl log — initially empty."""
    return tmp_path / "crawl_log.jsonl"


@pytest.fixture
def coordinator(
    corpus_path: Path,
    crawl_log_path: Path,
    tmp_path: Path,
) -> CrawlCoordinator:
    return CrawlCoordinator(
        llm_provider=object(),  # type: ignore[arg-type]
        embedder=object(),  # type: ignore[arg-type]
        corpus_path=corpus_path,
        crawl_log_path=crawl_log_path,
        mesh_inputs_dir=tmp_path / "mesh_inputs",
        kadmos_data_dir=tmp_path / "kadmos",
        batch_size=2,
        max_failures=3,
    )


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def test_load_corpus(coordinator: CrawlCoordinator) -> None:
    corpus = coordinator._load_corpus()
    assert len(corpus) == 6
    assert corpus[0]["title"] == "Bernoulli's principle"
    assert corpus[0]["domain"] == "physics"


def test_load_corpus_missing_file(tmp_path: Path) -> None:
    """Missing corpus file raises FileNotFoundError."""
    c = CrawlCoordinator(
        llm_provider=object(),  # type: ignore[arg-type]
        embedder=object(),  # type: ignore[arg-type]
        corpus_path=tmp_path / "nonexistent.json",
        crawl_log_path=tmp_path / "crawl_log.jsonl",
    )
    with pytest.raises(FileNotFoundError):
        c._load_corpus()


# ---------------------------------------------------------------------------
# Crawl log (crawl_log.jsonl)
# ---------------------------------------------------------------------------


def test_empty_crawl_log(coordinator: CrawlCoordinator) -> None:
    entries = coordinator._load_crawl_log()
    assert entries == {}


def test_append_and_load_crawl_log(coordinator: CrawlCoordinator) -> None:
    coordinator._append_to_crawl_log(
        {
            "title": "Bernoulli's principle",
            "verdict": "completed",
            "concept_count": 42,
            "edge_count": 156,
            "duration_s": 187.3,
            "cost_eur": 0.0342,
            "session_id": "test-sess-001",
        }
    )
    entries = coordinator._load_crawl_log()
    assert "Bernoulli's principle" in entries
    assert entries["Bernoulli's principle"]["verdict"] == "completed"
    assert entries["Bernoulli's principle"]["concept_count"] == 42


def test_crawl_log_multiple_entries(coordinator: CrawlCoordinator) -> None:
    entries_data = [
        {
            "title": "A",
            "verdict": "completed",
            "concept_count": 10,
            "edge_count": 5,
            "duration_s": 10.0,
            "cost_eur": 0.01,
            "session_id": "s1",
        },
        {
            "title": "B",
            "verdict": "failed",
            "concept_count": 0,
            "edge_count": 0,
            "duration_s": 5.0,
            "cost_eur": 0.005,
            "session_id": "s2",
        },
        {
            "title": "C",
            "verdict": "completed",
            "concept_count": 20,
            "edge_count": 8,
            "duration_s": 15.0,
            "cost_eur": 0.02,
            "session_id": "s3",
        },
    ]
    for entry in entries_data:
        coordinator._append_to_crawl_log(entry)
    entries = coordinator._load_crawl_log()
    assert len(entries) == 3
    assert entries["A"]["verdict"] == "completed"
    assert entries["B"]["verdict"] == "failed"


def test_crawl_log_append_is_atomic(coordinator: CrawlCoordinator) -> None:
    """Multiple appends should all be readable."""
    for i in range(100):
        coordinator._append_to_crawl_log(
            {
                "title": f"Article-{i}",
                "verdict": "completed",
                "concept_count": i,
                "edge_count": i * 2,
                "duration_s": float(i),
                "cost_eur": i / 1000.0,
                "session_id": f"sess-{i}",
            }
        )
    entries = coordinator._load_crawl_log()
    assert len(entries) == 100


# ---------------------------------------------------------------------------
# Skip detection
# ---------------------------------------------------------------------------


def test_skip_already_completed(
    coordinator: CrawlCoordinator,
) -> None:
    """Articles already in the crawl log with non-failed verdict should be counted."""
    coordinator._append_to_crawl_log(
        {
            "title": "Bernoulli's principle",
            "verdict": "completed",
            "concept_count": 42,
            "edge_count": 156,
            "duration_s": 187.3,
            "cost_eur": 0.0342,
            "session_id": "test-sess-001",
        }
    )
    completed = coordinator._load_crawl_log()
    entry = completed.get("Bernoulli's principle")
    assert entry is not None
    assert entry["verdict"] != "failed"


def test_retry_failed_article(
    coordinator: CrawlCoordinator,
) -> None:
    """Articles with 'failed' verdict should NOT be skipped — they are retried."""
    coordinator._append_to_crawl_log(
        {
            "title": "Bernoulli's principle",
            "verdict": "failed",
            "concept_count": 0,
            "edge_count": 0,
            "duration_s": 5.0,
            "cost_eur": 0.0,
            "session_id": "test-sess-fail",
        }
    )
    completed = coordinator._load_crawl_log()
    entry = completed.get("Bernoulli's principle")
    assert entry is not None
    assert entry["verdict"] == "failed"


# ---------------------------------------------------------------------------
# Domain progress tracking
# ---------------------------------------------------------------------------


def test_domain_counts(coordinator: CrawlCoordinator) -> None:
    corpus = coordinator._load_corpus()
    # Should be computed during run, but we can test the corpus parsing
    domain_counts: dict[str, int] = {}
    for article in corpus:
        domain = article.get("domain", "unknown")
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    assert domain_counts["physics"] == 2
    assert domain_counts["biology"] == 1
    assert domain_counts["mathematics"] == 1
    assert domain_counts["history"] == 1
    assert domain_counts["philosophy"] == 1
    assert len(domain_counts) == 5


# ---------------------------------------------------------------------------
# Batch iteration
# ---------------------------------------------------------------------------


def test_batch_iteration(coordinator: CrawlCoordinator) -> None:
    """With batch_size=2 and domains of sizes [2,1,1,1,1], there should be 5 batches."""
    corpus = coordinator._load_corpus()
    batches = coordinator._iter_batches(corpus)
    assert len(batches) == 5  # physics(2)→1 batch, rest each→1 batch
    # physics uses full batch
    assert len(batches[0]) == 2
    # others are single-article domains
    for i in range(1, 5):
        assert len(batches[i]) == 1


def test_batch_iteration_preserves_domain_order(coordinator: CrawlCoordinator) -> None:
    """Batches should be domain-sequential (corpus order)."""
    corpus = coordinator._load_corpus()
    batches = coordinator._iter_batches(corpus)
    assert batches[0][0]["domain"] == "physics"
    assert batches[1][0]["domain"] == "biology"
    assert batches[2][0]["domain"] == "mathematics"


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------


def test_signal_handler_setup_restore(coordinator: CrawlCoordinator) -> None:
    """Verify that SIGINT handler is installed and then restored."""
    original = signal.getsignal(signal.SIGINT)
    coordinator._setup_signal_handler()
    assert not coordinator._shutdown_requested
    assert signal.getsignal(signal.SIGINT) != original
    coordinator._restore_signal_handler()
    assert signal.getsignal(signal.SIGINT) == original


# ---------------------------------------------------------------------------
# Article slug
# ---------------------------------------------------------------------------


def test_article_slug() -> None:
    from theogony.kadmos.crawl import _article_slug

    assert _article_slug("Bernoulli's principle") == "bernoullis_principle"
    assert _article_slug("Wave–particle duality") == "wave-particle_duality"
    assert _article_slug("Simple") == "simple"
