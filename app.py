import streamlit as st
import pandas as pd
import openai
import time

st.title("System premiowy – analiza jakości wiadomości (GPT-4)")

api_key = st.text_input("Wklej swój OpenAI API Key", type="password")
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

if api_key and uploaded_file:
    openai.api_key = api_key
    data = pd.read_csv(uploaded_file)

    st.success("Plik załadowany – rozpoczynam analizę...")

    progress = st.progress(0)
    status = st.empty()
    results = []

    for i, row in enumerate(data.itertuples()):
        agent = getattr(row, "Author", "")
        message = getattr(row, "Extract", "")
        msg_id = getattr(row, "Message_ID", "")

        if not message or pd.isna(message):
            continue

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od obsługi klienta. Oceń jakość wiadomości agenta pod kątem poprawności, zgodności z procedurami i tonu komunikacji."},
                    {"role": "user", "content": f"Wiadomość agenta: {message}"}
                ],
                temperature=0.3
            )
            feedback = response["choices"][0]["message"]["content"]

        except Exception as e:
            feedback = f"Błąd: {str(e)}"

        results.append({
            "Message ID": msg_id,
            "Agent": agent,
            "Original Message": message,
            "GPT Feedback": feedback
        })

        status.text(f"Analizuję wiadomość {i + 1} z {len(data)}")
        progress.progress((i + 1) / len(data))

    st.success("Analiza zakończona!")

    results_df = pd.DataFrame(results)
    st.dataframe(results_df)

    csv_download = results_df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz wyniki jako CSV", csv_download, "analiza.csv", "text/csv")
