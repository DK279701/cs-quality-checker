import streamlit as st
import pandas as pd
import openai
import time

# Ustawienie tytułu
st.title("System premiowy – analiza jakości wiadomości")

# Wczytanie API key
openai_api_key = st.text_input("Wklej swój OpenAI API Key", type="password")

# Wczytanie pliku CSV
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

# Ustawienie modelu
model = "gpt-4"

if uploaded_file and openai_api_key:
    openai.api_key = openai_api_key
    data = pd.read_csv(uploaded_file)

    st.success("Plik CSV załadowany poprawnie. Rozpoczynam analizę...")

    # Pasek postępu
    progress_bar = st.progress(0)
    status_text = st.empty()

    results = []

    for i, row in enumerate(data.itertuples()):
        agent = getattr(row, "Author", "")
        message = getattr(row, "Extract", "")
        msg_id = getattr(row, "Message_ID", "")

        if not message or pd.isna(message):
            continue

        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od obsługi klienta. Oceń jakość wiadomości agenta pod kątem poprawności, zgodności z procedurami i tonu komunikacji."},
                    {"role": "user", "content": f"Wiadomość agenta: {message}"}
                ],
                temperature=0.3
            )

            reply = response.choices[0].message.content
            results.append({
                "Message ID": msg_id,
                "Agent": agent,
                "Original Message": message,
                "GPT Feedback": reply
            })

        except Exception as e:
            results.append({
                "Message ID": msg_id,
                "Agent": agent,
                "Original Message": message,
                "GPT Feedback": f"Błąd: {str(e)}"
            })

        # Aktualizacja postępu
        status_text.text(f"Analizuję wiadomość {i + 1} z {len(data)}...")
        progress_bar.progress((i + 1) / len(data))

    st.success("Analiza zakończona!")

    # Konwersja wyników do DataFrame
    results_df = pd.DataFrame(results)

    # Wyświetlenie tabeli
    st.dataframe(results_df)

    # Możliwość pobrania pliku CSV z wynikami
    csv_download = results_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Pobierz wyniki analizy jako CSV",
        data=csv_download,
        file_name="wyniki_analizy.csv",
        mime="text/csv"
    )
