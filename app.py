import streamlit as st
import pandas as pd
import datetime
from openai import OpenAI

# Konfiguracja strony
st.set_page_config(page_title="CS Quality Checker (ChatGPT)", layout="centered")
st.title("🔍 CS Quality Checker (ChatGPT)")

# Wprowadzenie tokena OpenAI
openai_api_key = st.text_input("🔑 Wprowadź swój OpenAI API Key", type="password")
if not openai_api_key:
    st.warning("Proszę wprowadzić swój OpenAI API Key.")
    st.stop()

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=openai_api_key)

# Wgrywanie pliku z bazą wiedzy
uploaded_file = st.file_uploader("📄 Wgraj plik z bazą wiedzy (txt lub md)", type=["txt", "md"])
if uploaded_file is not None:
    try:
        kb = uploaded_file.read().decode("utf-8")
    except Exception as e:
        st.error(f"Błąd podczas odczytu pliku: {e}")
        st.stop()
else:
    kb = ""

# Wprowadzenie wiadomości agenta
msg = st.text_area("💬 Wprowadź wiadomość agenta", height=150)

# Przycisk do analizy
if st.button("🧪 Sprawdź jakość"):
    if not kb.strip():
        st.warning("Proszę wgrać plik z bazą wiedzy przed analizą.")
    elif not msg.strip():
        st.warning("Proszę wprowadzić wiadomość agenta.")
    else:
        # Tworzenie promptu dla ChatGPT
        prompt = (
            "Jesteś ekspertem ds. jakości w obsłudze klienta. "
            "Na podstawie poniższej bazy wiedzy oceń, czy wiadomość agenta jest zgodna z procedurami. "
            "Zwróć uwagę na ton, profesjonalizm i kompletność odpowiedzi.\n\n"
            f"Baza wiedzy:\n{kb}\n\n"
            f"Wiadomość agenta:\n{msg}\n\n"
            "Odpowiedz po polsku."
        )

        try:
            # Wywołanie API OpenAI
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Jesteś pomocnym asystentem."},
                    {"role": "user", "content": prompt}
                ]
            )
            out = response.choices[0].message.content
            st.markdown("### ✅ Wynik analizy")
            st.write(out)
        except Exception as e:
            st.error(f"Błąd podczas wywołania API OpenAI: {e}")
            out = ""

        # Zapis historii
        history = st.session_state.get("history", [])
        history.append({
            "Czas": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Wiadomość": msg,
            "Analiza": out
        })
        st.session_state.history = history

# Wyświetlenie historii i możliwość pobrania
if st.session_state.get("history"):
    st.markdown("---")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Pobierz historię CSV", csv, "historia.csv", "text/csv")
