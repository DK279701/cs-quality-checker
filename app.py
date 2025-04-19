import streamlit as st
import openai
import pandas as pd
import datetime

from openai import OpenAI

st.set_page_config(page_title="Sprawdzanie jakości CS", layout="centered")

st.title("🕵️‍♂️ Sprawdzanie jakości wiadomości - Customer Service")
st.markdown("Wklej wiadomość agenta oraz bazę wiedzy, a sprawdzimy, czy wiadomość jest zgodna z procedurami.")

api_key = st.text_input("🔐 Twój klucz OpenAI API", type="password")
if not api_key:
    st.warning("Aby korzystać z aplikacji, wklej swój klucz OpenAI API powyżej.")
    st.stop()

client = OpenAI(api_key=api_key)

if "history" not in st.session_state:
    st.session_state.history = []

knowledge_base = st.text_area("📘 Wklej bazę wiedzy (możesz skopiować z Google Sites)", height=200)
message = st.text_area("💬 Wklej wiadomość agenta", height=200)

if st.button("🔍 Sprawdź wiadomość"):
    if not knowledge_base.strip() or not message.strip():
        st.error("Uzupełnij zarówno bazę wiedzy, jak i wiadomość agenta.")
    else:
        with st.spinner("Analizuję wiadomość..."):
            prompt = (
                "Jesteś ekspertem ds. jakości w obsłudze klienta. "
                "Na podstawie poniższej bazy wiedzy sprawdź, czy wiadomość agenta jest zgodna z procedurami. "
                "Jeśli nie, wskaż, co należy poprawić. Oceń także ogólną jakość wiadomości (ton, kompletność, profesjonalizm).\n\n"
                f"### Baza wiedzy:\n{knowledge_base}\n\n"
                f"### Wiadomość agenta:\n{message}\n\n"
                "Odpowiedz w języku polskim."
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                result = response.choices[0].message.content
                st.success("✅ Analiza zakończona:")
                st.markdown(result)

                st.session_state.history.append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "wiadomość": message,
                    "ocena": result
                })

            except Exception as e:
                st.error(f"Błąd podczas zapytania do OpenAI: {e}")

if st.session_state.history:
    st.markdown("---")
    st.markdown("### 🗂 Historia analiz (sesja)")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Pobierz jako CSV", csv, file_name="analizy_cs.csv", mime="text/csv")
