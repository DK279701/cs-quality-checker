import streamlit as st
import pandas as pd
import datetime
from transformers import pipeline

# Configure page
st.set_page_config(page_title="CS Quality (HF)", layout="centered")
st.title("🔍 CS Quality Checker (HuggingFace free API)")

# API token input
token = st.text_input("HuggingFace API token", type="password")
if not token:
    st.warning("Please provide your HuggingFace API token to load the model.")
    st.stop()

# Load model with error handling
try:
    generator = pipeline(
        task="text-generation",
        model="distilgpt2",
        tokenizer="distilgpt2",
        use_auth_token=token
    )
except Exception as e:
    st.error("Error loading model: " + str(e))
    st.stop()

# User inputs
kb = st.text_area("Knowledge Base", height=150)
msg = st.text_area("Agent Message", height=150)

# Analyze on button click
if st.button("Check Quality"):
    if not kb.strip() or not msg.strip():
        st.warning("Please fill both Knowledge Base and Agent Message.")
    else:
        prompt = f"""Check this agent message for compliance and quality based on the following knowledge base.\n\nKnowledge Base:\n{kb}\n\nAgent Message:\n{msg}\n\nRespond in Polish."""
        result = ""
        try:
            out = generator(prompt, max_length=256, num_return_sequences=1)[0]["generated_text"]
            st.markdown("**Analysis Result:**")
            st.write(out)
            result = out
        except Exception as e:
            st.error("Error during generation: " + str(e))

        # Save history
        history = st.session_state.get("history", [])
        history.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": msg,
            "result": result
        })
        st.session_state.history = history

# Display history and CSV download
if st.session_state.get("history"):
    st.markdown("---")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download history as CSV", csv, "history.csv", "text/csv")
