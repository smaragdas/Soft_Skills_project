import sys, json, hashlib

# ---- config: αγνόησε πεδία του result που δεν θες να επηρεάζουν το hash ----
IGNORE_RESULT_KEYS = {"debug"}  # π.χ. debug έχει volatile info

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def normalize_api(api_json, request_meta=None):
    """
    Αν έχει api_json['result'], το παίρνουμε.
    Αλλιώς, θεωρούμε ότι το api_json ΕΙΝΑΙ το result (όπως στο δικό σου API).
    Επιστρέφουμε {"request_meta": <meta ή {}>, "result": <result_filtered> }.
    """
    # 1) result node
    if isinstance(api_json, dict) and "result" in api_json:
        result = api_json["result"]
        meta = api_json.get("meta") or api_json.get("request_meta") or request_meta or {}
    else:
        result = api_json  # wrapperless
        meta = request_meta or api_json.get("meta") or {}

    # 2) φιλτράρουμε keys αν χρειάζεται
    if isinstance(result, dict) and IGNORE_RESULT_KEYS:
        result = {k: v for k, v in result.items() if k not in IGNORE_RESULT_KEYS}

    return {"request_meta": meta, "result": result}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python verify_smoke_test.py <api_response.json> <expected_hash.txt> [request_meta.json]")
        sys.exit(1)

    api_path, hash_path = sys.argv[1], sys.argv[2]
    req_meta = None
    if len(sys.argv) >= 4:
        try:
            req_meta = load_json(sys.argv[3])
        except Exception:
            req_meta = None

    api_json = load_json(api_path)
    with open(hash_path, "r", encoding="utf-8-sig") as f:
        expected_hash = f.read().strip()

    normalized = normalize_api(api_json, request_meta=req_meta)
    got_hash = hashlib.sha256(canonical(normalized).encode("utf-8")).hexdigest()

    print("Expected:", expected_hash)
    print("Got     :", got_hash)
    if got_hash == expected_hash:
        print("✅ MATCH")
        sys.exit(0)
    else:
        print("❌ MISMATCH")
        # βοηθητικό print για διάγνωση
        print("Normalized used for hashing:")
        print(json.dumps(normalized, indent=2, ensure_ascii=False))
        sys.exit(3)
