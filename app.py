import streamlit as st
import pandas as pd
import openai
import time
import asyncio
import aiohttp
from datetime import datetime

st.set_page_config(page_title="Analiza jakości wiadomości", layout="wide")
st.title("📊 Narzędzie do analizy jakości wiadomości")

# API key
api_key = st.text_input("🔑 Wprowadź swój OpenAI API Key", type="password")
if not api_key:
    st.warning("⚠️ Wprowadź swój OpenAI API Key, aby rozpocząć analizę.")
    st.stop()

openai.api_key = api_key

uploaded_file = st.file_uploader("📎 Wgraj plik CSV z wiadomościami", type=["csv"])

if not uploaded_file:
    st.info("Wgraj plik CSV, aby rozpocząć.")
    st.stop()

# Wczytanie pliku CSV z obsługą błędów
try:
    df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8")
except Exception as e:
    st.error(f"Błąd podczas wczytywania pliku CSV: {e}")
    st.stop()

if 'Extract' not in df.columns or 'Author' not in df.columns:
    st.error("Plik CSV musi zawierać kolumny: 'Extract' oraz 'Author'")
    st.stop()

# Wybranie zakresu analizy
agents = sorted(df['Author'].dropna().unique())
selected_agent = st.selectbox("👤 Wybierz agenta do analizy (lub 'Wszyscy')", options=["Wszyscy"] + list(agents))

if selected_agent != "Wszyscy":
    df = df[df['Author'] == selected_agent]

# Limit wiadomości do analizy (np. dla testów)
max_messages = st.slider("🔢 Maksymalna liczba wiadomości do analizy", 10, 1000, 50)
df = df.head(max_messages)

messages = df['Extract'].fillna("").tolist()
authors = df['Author'].fillna("Nieznany").tolist()

# Prompt + analiza
system_prompt = (
    "Jesteś Managerem Customer Service w firmie Bookinghost. "
    "Twoim zadaniem jest ocenić jakość wiadomości wysyłanych przez zespół obsługi klienta. "
    "Skup się na uprzejmości, poprawności językowej, trafności odpowiedzi i zgodności z wiedzą firmową. "
    "Twoja odpowiedź powinna być zwięzła i zawierać:\n"
    "- Ogólną ocenę jakości (np. skala 1–5 lub opisowa)\n"
    "- Argumentację tej oceny\n"
    "- Bulletpointy z szybkim feedbackiem"
)

async def analyze_message(session, message, author):
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Oceń poniższą wiadomość pracownika '{author}':\n\n{message}"}
            ],
            "temperature": 0.4,
        }
        async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
            response = await resp.json()
            return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Błąd analizy: {e}"

async def run_analysis():
    async with aiohttp.ClientSession() as session:
        tasks = [analyze_message(session, msg, auth) for msg, auth in zip(messages, authors)]
        return await asyncio.gather(*tasks)

if st.button("▶️ Rozpocznij analizę"):
    with st.spinner("Analizuję wiadomości..."):
        start_time = time.time()
        results = asyncio.run(run_analysis())
        elapsed = round(time.time() - start_time, 2)

        df["Ocena jakości"] = results
        st.success(f"✅ Analiza zakończona w {elapsed} sekundy")

        # Podsumowanie zespołu
        st.subheader("📈 Raport zbiorczy")
        summary = df.groupby("Author")["Ocena jakości"].apply(lambda x: f"{len(x)} wiadomości").reset_index(name="Liczba wiadomości")
        st.dataframe(summary)

        # Pobranie wyników
        st.subheader("📤 Pobierz wyniki")
        st.download_button(
            label="📥 Pobierz CSV z ocenami",
            data=df.to_csv(index=False, sep=";").encode("utf-8"),
            file_name="analiza_wiadomosci.csv",
            mime="text/csv"
        )

        # Szczegóły analizy
        st.subheader("📝 Szczegółowa analiza wiadomości")
        for idx, row in df.iterrows():
            st.markdown(f"**Agent:** {row['Author']}")
            st.markdown(f"**Wiadomość:** {row['Extract']}")
            st.markdown(f"**Ocena:**\n{row['Ocena jakości']}")
            st.markdown("---")
