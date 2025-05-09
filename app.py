import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime

st.set_page_config(page_title="🔎 Krok 1b: Zakres dat wiadomości", layout="wide")
st.title("🔎 Krok 1b: Zakres dat ALL outbound wiadomości")

# — Sidebar: Front API Token —
token = st.sidebar.text_input("Front API Token", type="password")
if not token:
    st.sidebar.warning("Wpisz Front API Token.")
    st.stop()

INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]

@st.cache_data(ttl=300)
def fetch_all_no_date_filter(token, inbox_ids, prog):
    headers = {"Authorization": f"Bearer {token}"}
    rows = []
    total = len(inbox_ids)
    for idx, inbox in enumerate(inbox_ids, start=1):
        # paginacja konwersacji
        url_c = f"https://api2.frontapp.com/inboxes/{inbox}/conversations"
        params = {"limit": 100}
        convs = []
        while True:
            r = requests.get(url_c, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            convs.extend(js.get("_results", []))
            if not js.get("_cursor"):
                break
            params["cursor"] = js["_cursor"]

        # wiadomości w konwersacjach
        for c in convs:
            cid = c["id"]
            url_m = f"https://api2.frontapp.com/conversations/{cid}/messages"
            r2 = requests.get(url_m, headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                if m.get("is_inbound", True):
                    continue
                created = m.get("created_at")
                dt = pd.to_datetime(created, utc=True) if created else None
                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                rows.append({
                    "Created At": dt,
                    "Inbox":      inbox,
                    "Message ID": m["id"],
                    "Extract":    text
                })
        prog.progress(idx/total)
    return pd.DataFrame(rows)

# — UI —
fetch_prog = st.sidebar.progress(0.0)
if st.button("▶️ Pobierz WSZYSTKIE wiadomości"):
    with st.spinner("⏳ Pobieram bez filtra dat…"):
        df = fetch_all_no_date_filter(token, INBOX_IDS, fetch_prog)

    if df.empty:
        st.warning("Nie znaleziono żadnych outbound wiadomości.")
        st.stop()

    st.success(f"Pobrano łącznie {len(df)} wiadomości.")
    st.subheader("Pierwsze 10 rekordów")
    st.dataframe(df.head(10), use_container_width=True)

    # pokaż zakres dat
    valid = df["Created At"].dropna()
    if not valid.empty:
        st.write("📅 Najwcześniejsza data:", valid.min())
        st.write("📅 Najpóźniejsza data:  ", valid.max())
    else:
        st.info("Brak dat w rekordach (wszystkie created_at są puste).")

    st.write("— Po tej weryfikacji będziemy mogli dobrać odpowiedni filtr dat.")
