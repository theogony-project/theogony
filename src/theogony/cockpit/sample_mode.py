"""Sample-only caps for Iris cockpit (PHX-0074)."""

from __future__ import annotations

from theogony.config.settings import Settings


def cluster_drill_member_cap(settings: Settings) -> int:
    return settings.cockpit.cluster_drill_max_members


def effective_search_limit(settings: Settings) -> int:
    if settings.cockpit.sample_only:
        return settings.cockpit.sample_top_n_nodes
    return 50


def effective_cluster_list_limit(settings: Settings) -> int | None:
    if settings.cockpit.sample_only:
        return settings.cockpit.sample_top_n_nodes
    return None


def effective_report_limit(settings: Settings) -> int:
    if settings.cockpit.sample_only:
        return settings.cockpit.sample_recent_n_reports
    return 200
