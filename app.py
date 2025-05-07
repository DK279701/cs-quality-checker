import requests

# Wprowadź swój Front API Token
API_TOKEN = "TWÓJ_FRONT_API_TOKEN"

# Ustawienia nagłówków żądania
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json"
}

# Endpoint API do pobrania listy teammate'ów
url = "https://api2.frontapp.com/teammates"

# Wykonanie żądania GET
response = requests.get(url, headers=headers)
response.raise_for_status()

# Przetworzenie odpowiedzi JSON
teammates = response.json().get("_results", [])

# Wyświetlenie informacji o każdym teammate
for t in teammates:
    print(f"{t['first_name']} {t['last_name']} ({t['username']}) — {t['email']} — ID: {t['id']}")
