import json
def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
def loads(s: str):
    import json as _j
    return _j.loads(s)
