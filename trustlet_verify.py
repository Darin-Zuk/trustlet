import streamlit as st

st.set_page_config(page_title="Trustlet - Email Verified")

APP_URL = "https://trustlet.streamlit.app"

st.title("✅ Email Verified")

st.markdown(
    """
    <p style="font-size:18px;">
    Your email has been successfully verified.
    </p>
    """,
    unsafe_allow_html=True
)

st.info(
    "🆕 **If you just signed up as a new user:**\n\n"
    "- Please wait for an existing Trustlet member to approve your application.\n"
    "- You will receive another email once your membership is approved (it might go to your SPAM folder).\n"
)

st.success(
    "🔑 **If you were resetting your password or logging in with a magic link:**\n\n"
    "- You can now continue directly to Trustlet."
)

# Always include a button back to main app
if st.button("🚀 Go to Trustlet"):
    st.markdown(f"[Click here to open Trustlet]({APP_URL})", unsafe_allow_html=True)
