import streamlit as st
import pandas as pd
from openai import OpenAI
import time

st.title("System premiowy – analiza jakości wiadomości (GPT-4)")

api_key = st.text_input("Wklej swój OpenAI API Key", type="password")
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

if api_key and uploaded_file:
    client = OpenAI(api_key=api_key)
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
            response = client.chat.completions.create(
                model="gpt
