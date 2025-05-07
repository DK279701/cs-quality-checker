import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Debug Front Directions", layout="wide")
st.title("🛠️ Debug: wszystkie kierunki wiadomości z Front")

# ——— SIDEBAR: FRONT API & INBOXY —————————————————
front_token = st.sidebar.text_input("Front API Token", type="password")
if not front_token:
    st.sidebar.warning("Wklej Front API Token")
    st.stop()

# twardo podajemy te trzy inboxy:
INBOXES = {
    "Customer Service":   "inb_a3xxy",
    "Chat Airbnb - New":  "inb_d2uom",
    "Chat Booking - New": "inb_d2xee"
}
st.sidebar.markdown("**Inboxy:**")
for name, iid in INBOXES.items():
    st.sidebar.write(f"- {name} (`{iid}`)")

inbox_ids = list(INBOXES.values())

# ——— FETCH ALL MESSAGES (no filter) ———————————————
@st.cache_data(ttl=300)
def fetch_all(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []
    for inbox in inbox_ids:
        # paginacja konwersacji
        params = {"inbox_id": inbox, "page_size": 100}
        convs = []
        while True:
            r = requests.get(base, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            convs.extend(js.get("_results", []))
            if not js.get("_cursor"):
                break
            params["cursor"] = js["_cursor"]
        # każda konwersacja → wiadomości
        for c in convs:
            cid = c.get("id")
            r2 = requests.get(f"{base}/{cid}/messages", headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                rows.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": cid,
                    "Message ID":      m.get("id",""),
                    "Author":          (m.get("author") or {}).get("handle","<no author>") 
                                       if isinstance(m.get("author"), dict)
                                       else str(m.get("author")),
                    "Direction":       m.get("direction"),
                    "Body (excerpt)":  m.get("body","")[:100]
                })
    return pd.DataFrame(rows)

if st.button("▶️ Pobierz wszystkie wiadomości (bez filtrowania)"):
    with st.spinner("⏳ Pobieram…"):
        df = fetch_all(front_token, inbox_ids)

    st.success(f"Pobrano {len(df)} wiadomości.")
    st.subheader("Pierwsze 20 rekordów")
    st.dataframe(df.head(20))

    st.subheader("Unikalne wartości Direction i ich liczność")
    counts = df["Direction"].value_counts(dropna=False).rename_axis("direction").reset_index(name="count")
    st.table(counts)

    st.stop()  # na teraz debug—we stop przed analizą
