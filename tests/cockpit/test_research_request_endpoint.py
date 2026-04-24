"""POST /cockpit/api/research-request (Living Demo W10)."""

from __future__ import annotations

from pathlib import Path

from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import TriggerReason


def test_research_request_endpoint_emits_trigger_with_user_request_reason(
    cockpit_client,
    api_app,
    api_settings,
) -> None:
    gb = api_settings.curiosity.growth_bridge.model_copy(update={"enabled": True})
    curiosity = api_settings.curiosity.model_copy(update={"growth_bridge": gb})
    api_app.state.settings = api_settings.model_copy(update={"curiosity": curiosity})

    ask = cockpit_client.post(
        "/cockpit/api/ask",
        json={"q": "What is Pantheon?", "k": 5, "hops": 1, "thinking_max": 0},
    )
    assert ask.status_code == 200
    body = ask.json()
    run_id = body["run_id"]
    query = body["query"]

    r = cockpit_client.post(
        "/cockpit/api/research-request",
        json={"run_id": run_id, "query": query},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("trigger_id")

    curiosity_dir = Path(api_settings.run_reports_dir) / "curiosity"
    found = False
    for path in curiosity_dir.glob("*.json"):
        rep = CuriosityRunReport.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            rep.trigger.origin_query_run_id == run_id
            and rep.trigger.trigger_reason == TriggerReason.USER_REQUEST
        ):
            found = True
            break
    assert found


def test_research_request_endpoint_returns_null_when_bridge_disabled(
    cockpit_client,
    api_app,
    api_settings,
) -> None:
    gb = api_settings.curiosity.growth_bridge.model_copy(update={"enabled": False})
    curiosity = api_settings.curiosity.model_copy(update={"growth_bridge": gb})
    api_app.state.settings = api_settings.model_copy(update={"curiosity": curiosity})

    ask = cockpit_client.post(
        "/cockpit/api/ask",
        json={"q": "What is Pantheon?", "k": 5, "hops": 1, "thinking_max": 0},
    )
    assert ask.status_code == 200
    body = ask.json()
    r = cockpit_client.post(
        "/cockpit/api/research-request",
        json={"run_id": body["run_id"], "query": body["query"]},
    )
    assert r.status_code == 200
    assert r.json().get("trigger_id") is None
