import requests

def geo_from_ip(ip):
    try:
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "country": data.get("country_name"),
                "city": data.get("city"),
                "region": data.get("region")
            }
    except:
        pass
    return {
        "country": "Unknown",
        "city": "Unknown",
        "region": "Unknown"
    }