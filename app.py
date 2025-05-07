import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time

st.set_page_config(page_title="CS Quality Checker – Debug Fetch", layout="wide")
st.title("🛠️ Debug pobierania wiadomości z Front")

# ——— SIDEBAR: KLUCZE API —————————————————
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")

if not front_token or not openai_key:
    st.sidebar.warning("Wprowadź oba klucze API (Front i OpenAI) i kliknij przycisk.")
    st.stop()

# ——— STAŁE INBOXY —————————————————————
INBOX_IDS = ["inb_a3xxy", "inb_d2uom", "inb_d2xee"]
st.sidebar.markdown("**Inboxy (stałe):**")
for iid in INBOX_IDS:
    st.sidebar.write(f"- `{iid}`")

# ——— FETCH DEBUG —————————————————————
def fetch_all_messages_debug(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        try:
            # paginacja konwersacji
            while True:
                resp = requests.get(base_url, headers=headers, params=params)
                resp.raise_for_status()
                js = resp.json()
                convs = js.get("_results", [])
                # dla każdej konwersacji pobierz wiadomości
                for c in convs:
                    cid = c.get("id", "")
                    r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
                    r2.raise_for_status()
                    for m in r2.json().get("_results", []):
                        records.append({
                            "Inbox ID":        inbox,
                            "Conversation ID": cid,
                            "Message ID":      m.get("id", ""),
                            "Direction":       m.get("direction", ""),
                            "Author":          (m.get("author") or {}).get("handle", "") 
                                                if isinstance(m.get("author"), dict)
                                                else str(m.get("author") or ""),
                            "Extract":         m.get("body", "")
                        })
                cursor = js.get("_cursor")
                if not cursor:
                    break
                params["cursor"] = cursor

        except Exception as e:
            # Wyświetl dokładny błąd i zatrzymaj
            st.error(f"❌ Błąd w inbox `{inbox}`: {e}")
            st.stop()

    return pd.DataFrame(records)

# ——— GŁÓWNY PRZEBIEG —————————————————————
if st.button("▶️ Pobierz wszystkie wiadomości (debug)"):
    with st.spinner("⏳ Pobieranie…"):
        df = fetch_all_messages_debug(front_token, INBOX_IDS)

    # pokaż ile pobrano i pierwsze rekordy
    st.success(f"Pobrano łącznie {len(df)} rekordów (przed filtrem).")
    st.subheader("Pierwsze 10 rekordów")
    st.dataframe(df.head(10))

    # pokaż unikalne Direction
    st.subheader("Unikalne wartości `Direction` i ich liczność")
    if "Direction" in df.columns:
        counts = df["Direction"].fillna("<empty>").value_counts().rename_axis("direction").reset_index(name="count")
        st.table(counts)
    else:
        st.warning("Brak kolumny `Direction` w danych.")

    st.info("Sprawdź czy wśród pobranych rekordów występują oczekiwane dane i formaty. Po diagnostyce możesz przywrócić oryginalną funkcję fetch_all_messages oraz filtrowanie outbound.")

    st.stop()  # koniec debugowania—dalej nie idziemy póki nie naprawimy fetch
