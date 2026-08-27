def test_protected_route_without_session(client):
    res = client.get("/user/saved-listings")
    assert res.status_code == 401

def test_auth_callback_missing_state(client):
    res = client.get("/auth/google/callback")
    # OAuth library should reject it because state is missing
    assert res.status_code == 400
