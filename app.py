import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup  # <-- do strippingu HTML

# ... [reszta importów i konfiguracji Streamlit] ...

@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []
    debug_auth = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            for conv in js.get("_results", []):
                cid = conv.get("id", "")
                r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    if m.get("is_inbound", True):
                        continue

                    # ---- stripping HTML z body
                    raw_body = m.get("body", "")
                    text = BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")

                    # ---- bezpieczne wyciągnięcie autora
                    raw_author = m.get("author")
                    if isinstance(raw_author, dict):
                        author = raw_author.get("handle") or raw_author.get("name") or "Unknown"
                    else:
                        author = str(raw_author) if raw_author else "Unknown"

                    # jeśli nadal Unknown, zapisujemy w debug
                    if author == "Unknown":
                        debug_auth.append(raw_author)

                    records.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id", ""),
                        "Author":          author,
                        "Extract":         text
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    df = pd.DataFrame(records)
    # dopiszemy debug do df (opcjonalnie możesz to wypisać osobno)
    df["_raw_author_debug"] = pd.Series(debug_auth + [None] * (len(df) - len(debug_auth)))
    return df

# --- dalej Twój główny flow: przycisk, filtrowanie, analiza GPT, raporty ...
