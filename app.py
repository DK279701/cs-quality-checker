import streamlit as st
import pandas as pd
import datetime
from huggingface_hub.inference_api import InferenceApi

# –––––– konfiguracja strony
st.set_page_config(page_title="CS Quality (HF Inference)", layout="centered")
st.title("🔍 CS Quality Checker (Hugging Face free API)")

# –––––– wprowadzenie tokena HF
token = st.text_input("Wklej token HF", type="password")
if not token:
    st.warning("Potrzebny jest token HF, aby ładować model.")
    st.stop()

# –––––– inicjalizacja klienta Inference API
try:
    client = InferenceApi(repo_id="gpt2", token=token)
except Exception as e:
    st.error("Nie udało się załadować klienta HF:\n" + str(e))
    st.stop()

# –––––– wejście od użytkownika
kb = st.text_area("Baza wiedzy (tekst)", height=150)
msg = st.text_area("Wiadomość agenta", height=150)

# –––––– analiza po naciśnięciu
if st.button("Sprawdź jakość"):
    if not kb.strip() or not msg.strip():
        st.warning("Uzupełnij oba pola: baza wiedzy i wiadomość.")
    else:
        prompt = (
            "Jesteś ekspertem ds. jakości w obsłudze klienta.\n"
            "Sprawdź tę wiadomość agenta pod kątem zgodności z procedurami " 
            "opisanymi w poniższej bazie wiedzy. " 
            "Zwróć uwagę na ton, profesjonalizm i kompletność.\n\n"
            f"Baza wiedzy:\n{kb}\n\n"
            f"Wiadomość agenta:\n{msg}\n\n"
            "Odpowiedz po polsku."
        )

        try:
            # wywołanie HF Inference API – darmowe do pewnych limitów
            result = client(inputs=prompt)
            # HF zwykle zwraca listę generowanych tekstów
            out_text = result[0]['generated_text'] if isinstance(result, list) else str(result)
            st.markdown("**Wynik analizy:**")
            st.write(out_text)
        except Exception as e:
            st.error("Błąd podczas wywołania API HF:\n" + str(e))
            out_text = ""

        # zapis historii
        history = st.session_state.get("history", [])
        history.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": msg,
            "analysis": out_text
        })
        st.session_state.history = history

# –––––– wyświetlenie i eksport historii
if st.session_state.get("history"):
    st.markdown("---")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz historię CSV", csv, "history.csv", "text/csv")
