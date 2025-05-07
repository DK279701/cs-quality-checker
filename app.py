import requests
import pandas as pd
import streamlit as st
import asyncio

# Wprowadź swój Front API Token
API_TOKEN = "TWÓJ_FRONT_API_TOKEN"

# Ustawienia nagłówków żądania
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json"
}

# Funkcja do pobrania listy teammate'ów
def get_teammates():
    url = "https://api2.frontapp.com/teammates"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("_results", [])

# Funkcja do pobrania danych (przykładowa)
async def run_all(recs, progress, status):
    # Tutaj umieść swoją logikę asynchroniczną
    # Zwracana wartość powinna być listą wyników analizy
    return ["Przykładowy wynik analizy" for _ in recs]

# Główna funkcja aplikacji
def main():
    st.title("Analiza jakości obsługi klienta")

    # Pobranie listy teammate'ów
    try:
        teammates = get_teammates()
    except requests.exceptions.HTTPError as e:
        st.error(f"Błąd podczas pobierania listy użytkowników: {e}")
        return

    # Utworzenie DataFrame z danymi teammate'ów
    df_teammates = pd.DataFrame([
        {
            "ID": t["id"],
            "Imię": t["first_name"],
            "Nazwisko": t["last_name"],
            "Email": t["email"],
            "Nazwa użytkownika": t["username"]
        }
        for t in teammates
    ])

    st.subheader("Lista użytkowników")
    st.dataframe(df_teammates)

    # Wybór użytkowników do wykluczenia
    exclude_usernames = st.multiselect(
        "Wybierz użytkowników do wykluczenia z analizy:",
        options=df_teammates["Nazwa użytkownika"].tolist()
    )

    # Przykładowe dane do analizy (zastąp swoimi danymi)
    recs = [
        {"author": "jakub_buryta", "message": "Przykładowa wiadomość 1"},
        {"author": "anna_k", "message": "Przykładowa wiadomość 2"},
        {"author": "piotr_nowak", "message": "Przykładowa wiadomość 3"}
    ]

    # Filtrowanie danych na podstawie wykluczonych użytkowników
    filtered_recs = [rec for rec in recs if rec["author"] not in exclude_usernames]

    st.subheader("Dane do analizy")
    st.write(filtered_recs)

    # Przycisk do uruchomienia analizy
    if st.button("Uruchom analizę"):
        progress = st.progress(0)
        status = st.empty()
        try:
            feedback = asyncio.run(run_all(filtered_recs, progress, status))
            st.subheader("Wyniki analizy")
            st.write(feedback)
        except Exception as e:
            st.error(f"Wystąpił błąd podczas analizy: {e}")

if __name__ == "__main__":
    main()
