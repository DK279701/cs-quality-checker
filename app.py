import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

st.title("🚧 Debug: Pobierz pierwsze 20 wiadomości z 3 inboxów")

token = st.text_input("Front API Token", type="password")
if not token:
    st.stop()

INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

all_msgs = []
for inbox in INBOX_IDS:
    # Używamy endpointu /messages z parametrem direction=outbound
    # zamiast ręcznego odpytywania conversations, to będzie najszybsze
    url = "https://api2.frontapp.com/messages"
    params = {
        "inbox_id": inbox,
        "direction": "outbound",
        "page_size": 20
    }
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        st.error(f"❌ Błąd {resp.status_code} dla inbox `{inbox}`:\n{resp.text}")
        continue
    data = resp.json().get("_results", [])
    st.write(f"**Inbox {inbox}** – znaleziono {len(data)} wiadomości:")
    for m in data:
        txt = BeautifulSoup(m.get("body",""), "html.parser").get_text().replace("\n"," ")
        st.write(f"- `{m.get('id')}` · inbound={m.get('is_inbound')} · {txt[:80]}…")
    all_msgs.extend(data)

st.write(f"— razem pobrano {len(all_msgs)} rekordów.")
