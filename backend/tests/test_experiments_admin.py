from __future__ import annotations

import json

from backend.app.core.config import settings
from conftest import make_admin, register


def test_experiment_runs_real_searches_and_computes_metrics(client) -> None:
    headers = register(client)
    response = client.post(
        "/api/v1/experiments/runs",
        headers=headers,
        json={
            "name": "Murder statute lookup",
            "retrievers": ["bm25"],
            "k": 3,
            "queries": [
                {"query": "murder punished", "relevant_doc_ids": ["S1", "MISSING-DOC"]},
                {"query": "inherent powers High Court"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["summary"]["judged_query_count"] == 1
    assert body["summary"]["unknown_relevant_doc_ids"] == ["MISSING-DOC"]
    first = body["results"]["queries"][0]["systems"]["bm25"]
    assert first["ranking"][0]["doc_id"] == "S1"
    assert first["metrics"]["mrr"] == 1.0
    # Recall counts the relevant document that is absent from the corpus.
    assert first["metrics"]["recall@3"] == 0.5
    assert "metrics" not in body["results"]["queries"][1]["systems"]["bm25"]
    assert body["summary"]["systems"]["bm25"]["evaluated_queries"] == 1

    experiment_id = body["experiment_id"]
    listing = client.get("/api/v1/experiments/runs", headers=headers).json()
    assert listing["total"] == 1
    assert (
        client.get(f"/api/v1/experiments/runs/{experiment_id}", headers=headers).status_code == 200
    )


def test_experiments_are_private_and_deletable(client) -> None:
    owner = register(client, "owner")
    other = register(client, "other")
    experiment_id = client.post(
        "/api/v1/experiments/runs",
        headers=owner,
        json={"name": "Mine", "retrievers": ["bm25"], "queries": [{"query": "murder"}]},
    ).json()["experiment_id"]
    assert client.get(f"/api/v1/experiments/runs/{experiment_id}", headers=other).status_code == 404
    assert (
        client.delete(f"/api/v1/experiments/runs/{experiment_id}", headers=other).status_code == 404
    )
    assert (
        client.delete(f"/api/v1/experiments/runs/{experiment_id}", headers=owner).status_code == 204
    )
    assert client.get(f"/api/v1/experiments/runs/{experiment_id}", headers=owner).status_code == 404


def test_experiment_validation(client, monkeypatch) -> None:
    headers = register(client)
    disabled = client.post(
        "/api/v1/experiments/runs",
        headers=headers,
        json={"name": "Dense", "retrievers": ["dense"], "queries": [{"query": "murder"}]},
    )
    assert disabled.status_code == 422
    assert "dense" in disabled.json()["detail"]
    monkeypatch.setattr(settings, "experiment_max_queries", 2)
    too_many = client.post(
        "/api/v1/experiments/runs",
        headers=headers,
        json={
            "name": "Many",
            "retrievers": ["bm25"],
            "queries": [{"query": f"q{i}"} for i in range(3)],
        },
    )
    assert too_many.status_code == 422
    assert (
        client.post(
            "/api/v1/experiments/runs",
            headers=headers,
            json={"name": " ", "retrievers": ["bm25"], "queries": [{"query": "x"}]},
        ).status_code
        == 422
    )


def test_benchmark_runs_are_read_from_results_directory(client, tmp_path) -> None:
    headers = register(client)
    run = tmp_path / "results" / "aila-test"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text(
        json.dumps({"systems": {"bm25": {"map": 0.2}}}), encoding="utf-8"
    )
    runs = client.get("/api/v1/experiments/benchmarks", headers=headers).json()
    assert runs[0]["run_id"] == "aila-test"
    assert client.get(
        "/api/v1/experiments/benchmarks/..%2Fsecret", headers=headers
    ).status_code in {404, 422}
    assert client.get("/api/v1/experiments/benchmarks/missing", headers=headers).status_code == 404


def test_admin_overview_and_user_management(client) -> None:
    user = register(client)
    assert client.get("/api/v1/admin/overview", headers=user).status_code == 403
    assert client.get("/api/v1/admin/users", headers=user).status_code == 403
    admin = make_admin(client)
    client.post("/api/v1/search", headers=user, json={"query": "murder"})
    overview = client.get("/api/v1/admin/overview", headers=admin).json()
    assert overview["users"] == 2
    assert overview["corpus_documents"] == 3
    assert overview["system"]["database"] == "ok"
    assert overview["system"]["schema_revision"] == "0003_embedding_batches"
    assert any(row["event_type"] == "search" for row in overview["usage_last_24h"])
    assert "query" not in json.dumps(overview["usage_last_24h"])

    users = client.get("/api/v1/admin/users", headers=admin, params={"q": "research"}).json()
    assert [account["username"] for account in users["users"]] == ["researcher"]
    promoted = client.patch("/api/v1/admin/users/researcher", headers=admin, json={"role": "admin"})
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    assert (
        client.patch("/api/v1/admin/users/ghost", headers=admin, json={"role": "user"}).status_code
        == 404
    )


def test_admins_cannot_lock_themselves_out(client) -> None:
    admin = make_admin(client)
    assert (
        client.patch("/api/v1/admin/users/chief", headers=admin, json={"role": "user"}).status_code
        == 409
    )
    assert (
        client.patch(
            "/api/v1/admin/users/chief", headers=admin, json={"is_active": False}
        ).status_code
        == 409
    )


def test_bootstrap_admin_is_created_from_environment(tmp_path, monkeypatch) -> None:
    from backend.app.db.database import Database
    from backend.app.services.auth import authenticate, initialize_auth_store

    monkeypatch.setattr(settings, "initial_admin_username", "bootstrap")
    monkeypatch.setattr(settings, "initial_admin_password", "a-long-bootstrap-password")
    database = Database(f"sqlite:///{(tmp_path / 'boot.db').as_posix()}")
    initialize_auth_store(database)
    initialize_auth_store(database)  # Idempotent on restart.
    assert authenticate(database, "bootstrap", "a-long-bootstrap-password") == "admin"
    assert database.count_users() == 1
    database.close()
