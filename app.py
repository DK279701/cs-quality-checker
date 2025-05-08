import requests

# Zamień poniżej na swój token API Front
FRONT_API_TOKEN = "YOUR_FRONT_API_TOKEN"

headers = {
    "Authorization": f"Bearer {FRONT_API_TOKEN}",
    "Accept": "application/json"
}

def get_teammates():
    url = "https://api2.frontapp.com/teammates"
    teammates_list = []
    
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        teammates_list.extend([
            {
                "id": t.get("id"),
                "email": t.get("email"),
                "username": t.get("username"),
                "first_name": t.get("first_name"),
                "last_name": t.get("last_name")
            }
            for t in data.get("_results", [])
        ])
        url = data.get("_pagination", {}).get("next")

    return teammates_list

# Przykład użycia:
teammates = get_teammates()
for person in teammates:
    print(f'{person["first_name"]} {person["last_name"]} ({person["email"]}) - ID: {person["id"]}')
