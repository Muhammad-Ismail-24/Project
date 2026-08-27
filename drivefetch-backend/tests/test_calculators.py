def test_fuel_calculator(client):
    # normal request
    res = client.post("/api/calc/fuel", json={
        "car_segment_cc": 1300,
        "daily_commute_km": 50
    })
    assert res.status_code == 200

    # zero budget/zero daily commute
    res = client.post("/api/calc/fuel", json={
        "car_segment_cc": 1300,
        "daily_commute_km": 0
    })
    assert res.status_code == 200

    # negative values (ge=1 for CC, ge=0 for commute)
    res = client.post("/api/calc/fuel", json={
        "car_segment_cc": -1300,
        "daily_commute_km": 50
    })
    assert res.status_code == 422
    
    # string input where number expected
    res = client.post("/api/calc/fuel", json={
        "car_segment_cc": "thousand",
        "daily_commute_km": 50
    })
    assert res.status_code == 422
    
    # extremely large values
    res = client.post("/api/calc/fuel", json={
        "car_segment_cc": 999999999,
        "daily_commute_km": 999999999
    })
    assert res.status_code == 200

    # missing required fields
    res = client.post("/api/calc/fuel", json={
        "daily_commute_km": 50
    })
    assert res.status_code == 422

def test_transfer_fee(client):
    res = client.post("/api/calc/transfer-fee", json={
        "engine_cc": 1300,
        "is_filer": True
    })
    assert res.status_code == 200

    # negative engine cc
    res = client.post("/api/calc/transfer-fee", json={
        "engine_cc": -100,
        "is_filer": True
    })
    assert res.status_code == 422

    # missing required field
    res = client.post("/api/calc/transfer-fee", json={
        "is_filer": True
    })
    assert res.status_code == 422

def test_token_tax(client):
    res = client.post("/api/calc/token-tax", json={
        "engine_cc": 1500,
        "is_filer": True,
        "province": "Punjab"
    })
    assert res.status_code == 200
    
    res = client.post("/api/calc/token-tax", json={
        "engine_cc": -1,
        "is_filer": False,
        "province": "Sindh"
    })
    assert res.status_code == 422
