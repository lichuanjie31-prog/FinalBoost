from test_auth import bearer, client_for, register


def test_question_bank_contract_is_exposed_without_fake_success(tmp_path):
    with client_for(tmp_path) as client:
        auth_result = register(client)
        auth = bearer(auth_result)

        assert auth_result["user"]["role"] == "student"
        assert client.get("/api/v1/subjects", headers=auth).status_code == 501
        assert client.post(
            "/api/v1/subjects/private",
            json={"name": "计算机图形学专题"},
            headers={**auth, "Idempotency-Key": "contract-test"},
        ).status_code == 501

        schema = client.get("/openapi.json").json()
        expected = {
            "/api/v1/subjects",
            "/api/v1/subjects/private",
            "/api/v1/subjects/system",
            "/api/v1/papers",
            "/api/v1/papers/private",
            "/api/v1/papers/private/{paper_id}",
            "/api/v1/papers/private/{paper_id}/file",
            "/api/v1/admin/papers",
            "/api/v1/admin/papers/{paper_id}",
            "/api/v1/admin/papers/{paper_id}/file",
            "/api/v1/admin/papers/{paper_id}/publish",
            "/api/v1/admin/papers/{paper_id}/unpublish",
            "/api/v1/public/papers",
            "/api/v1/public/papers/{paper_id}/copy",
        }
        assert expected <= set(schema["paths"])
