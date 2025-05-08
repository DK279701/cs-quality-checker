import streamlit as st
import requests

st.title("🗂️ Sprawdź dostępne inboxy w Front")

token = st.text_input("Front API Token", type="password")
if token and st.button("▶️ Pobierz listę inboxów"):
    url = "https://api2.frontapp.com/inboxes"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("_results", [])
        st.write(f"Znaleziono {len(data)} inboxów:")
        for ib in data:
            st.write(f"- {ib.get('name')} — ID: `{ib.get('id')}`")
    except Exception as e:
        st.error(f"Błąd: {e}")
    st.stop()
