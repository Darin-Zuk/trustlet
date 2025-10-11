# send_announcement.py
# Run with:  python send_announcement.py

import os
from supabase import create_client
import resend
import time

# -------------------------------
# Config
# -------------------------------

# This is the single address you want to receive the test,
# even though we'll fetch *all* users first.

RETRY_LIST = {
}

RETRY_LIST = {
    "zukermandarin@gmail.com",
    "zukermandarin+test@gmail.com",
    "zukermandarin+test2@gmail.com"
}


# Users to never email (paste any you want to skip)
EXCLUSION_LIST = {
    # "dont-email-me@example.com",
}

# Delay between sends (seconds)
SEND_DELAY = 2.0

# Credentials (use env vars; or hardcode here if you prefer)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "admin@amstrustlet.app")
FROM_NAME = os.environ.get("FROM_NAME", "Trustlet Team")

if not (SUPABASE_URL and SUPABASE_KEY and RESEND_API_KEY):
    raise RuntimeError(
        "Missing credentials. Set SUPABASE_URL, SUPABASE_KEY, and RESEND_API_KEY "
        "as environment variables before running this script."
    )

# -------------------------------
# Init clients
# -------------------------------
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
resend.api_key = RESEND_API_KEY

def send_email(to_email: str, subject: str, body_html: str):
    resend.Emails.send({
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": body_html
    })

# -------------------------------
# Email content
# -------------------------------
SUBJECT = "New feature alert and share request"

# Use [to_email] as the placeholder we’ll replace per recipient
BODY_TEMPLATE = """
<p>Dear early adopter of Trustlet,</p>

<p>It's time to expand our <b>Trustlet Tribe</b>! &lt;&lt;pause for cringe&gt;&gt;</p>

<p>Here is some text you can send to your Amsterdam groups if you feel like it:
<em>"My amazing friend developed a free app (https://trustlet.streamlit.app/) linking together Amsterdam lets and visitors within a friends of friends network. Use my email as the inviter [to_email]."</em></p>

<p>I've also just added what I think is a very important feature - <b>New Listing Alerts</b>.
This is so that users can be notified if a listing is added that matches their filters, instead of needing to re-check the app.
You can find it under "Browse Listings".</p>

<p>Have a lovely weekend<br>
Zuk</p>

<p><small>P.S I will only rarely send an email like this to all users, but if you never want to receive anything like it again, reply with "Nee Bedankt".</small></p>
"""

def render_body_for(to_email: str) -> str:
    """Personalize the BODY_TEMPLATE with the recipient's email."""
    return BODY_TEMPLATE.replace("[to_email]", to_email)

# -------------------------------
# Build recipient list
# -------------------------------
# 1) Fetch ALL active users
if RETRY_LIST:
    # Retry mode: only the addresses pasted above
    recipients = sorted({e.strip().lower() for e in RETRY_LIST if e.strip()})
else:
    # Normal mode: fetch all active users, minus exclusions
    resp = supabase.table("users").select("email").eq("is_active", True).execute()
    emails = [
        (row["email"] or "").strip().lower()
        for row in (resp.data or [])
        if row.get("email")
    ]
    exclude = {e.strip().lower() for e in EXCLUSION_LIST}
    recipients = sorted({e for e in emails if e not in exclude})
    #print(1==1)


# -------------------------------
# Send loop
# -------------------------------
print(f"Total recipients: {len(recipients)}")
for idx, email in enumerate(recipients, start=1):
    try:
        body = render_body_for(email)
        send_email(email, SUBJECT, body)
        print(f"[{idx}/{len(recipients)}] ✅ Sent to {email}")
    except Exception as e:
        print(f"[{idx}/{len(recipients)}] ❌ FAILED for {email}: {e}")
    time.sleep(SEND_DELAY)

print("Done.")