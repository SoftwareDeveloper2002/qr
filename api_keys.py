import json
import uuid
import os
from fastapi import HTTPException, Request

KEY_STORE = "analytics/api_keys.json"

os.makedirs("analytics", exist_ok=True)

def load_keys():
    if not os.path.exists(KEY_STORE):
        return {}
    try:
        with open(KEY_STORE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_keys(data):
    with open(KEY_STORE, "w") as f:
        json.dump(data, f)

def create_api_key(owner, limit):
    store = load_keys()
    key = str(uuid.uuid4())
    store[key] = {
        "owner": owner,
        "limit": limit,
        "used": 0,
        "created": datetime.datetime.now().isoformat()
    }
    save_keys(store)
    return key

def check_api_key(request: Request):
    key = request.headers.get("x-api-key")
    if not key:
        raise HTTPException(status_code=401, detail="API key required")

    store = load_keys()
    record = store.get(key)

    if not record:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if record["used"] >= record["limit"]:
        raise HTTPException(status_code=429, detail="API limit exceeded")

    record["used"] += 1
    store[key] = record
    save_keys(store)