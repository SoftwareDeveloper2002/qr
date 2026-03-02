def detect_device(user_agent: str):
    ua = (user_agent or "").lower()
    if "iphone" in ua or "android" in ua:
        return "mobile"
    if "windows" in ua:
        return "desktop"
    if "mac" in ua:
        return "mac"
    return "unknown"