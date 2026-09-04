import pytest

from orca_keychron.orca_status import OrcaStatusError, parse_orca_agents


def test_parse_orca_agents_flattens_worktrees_and_filters_states():
    payload = {
        "ok": True,
        "result": {
            "worktrees": [
                {
                    "worktreeId": "repo::/one",
                    "hostId": "local",
                    "agents": [
                        {"paneKey": "pane-1", "state": "working", "agentType": "codex"},
                        {"paneKey": "pane-2", "state": "invalid", "agentType": "claude"},
                    ],
                },
                {
                    "worktreeId": "repo::/two",
                    "hostId": "ssh:prod",
                    "agents": [{"paneKey": "pane-3", "state": "done"}],
                },
                {
                    "agents": [{"paneKey": "pane-4", "state": "working"}],
                },
            ]
        },
    }

    agents = parse_orca_agents(payload)

    assert [(agent.pane_key, agent.state, agent.host_id) for agent in agents] == [
        ("pane-1", "working", "local"),
        ("pane-3", "done", "ssh:prod"),
    ]
    assert parse_orca_agents(payload, ["local"]) == [agents[0]]


def test_parse_orca_agents_rejects_non_success_response():
    with pytest.raises(OrcaStatusError):
        parse_orca_agents({"ok": False})
