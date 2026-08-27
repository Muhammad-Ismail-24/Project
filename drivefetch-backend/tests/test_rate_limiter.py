def test_rate_limiter(client):
    payload = {
        "car_segment_cc": 1300,
        "daily_commute_km": 50
    }
    
    got_429 = False
    headers = {}
    for _ in range(40):
        res = client.post("/api/calc/fuel", json=payload)
        if res.status_code == 429:
            got_429 = True
            headers = res.headers
            break
        assert res.status_code == 200

    assert got_429
    assert "retry-after" in (k.lower() for k in headers.keys())
