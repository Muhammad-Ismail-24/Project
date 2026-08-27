def test_chat_empty_message(client):
    res = client.post("/api/chat", json={
        "message": ""
    })
    assert res.status_code in [400, 422]

def test_chat_too_long_message(client):
    res = client.post("/api/chat", json={
        "message": "A" * 2001
    })
    assert res.status_code in [400, 422]

def test_chat_history_too_long(client):
    # max_length for guest_history is 30
    res = client.post("/api/chat", json={
        "message": "Hello",
        "guest_history": [{"role": "user", "content": "hi"}] * 31
    })
    assert res.status_code == 422
