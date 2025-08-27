import streamlit as st
from supabase import create_client, Client
import json
from datetime import datetime
import resend
import traceback
import html
import requests
# ----------------------------------
# Page setup
# ----------------------------------
st.set_page_config(page_title="Trustlet", layout="wide")

# ----------------------------------
# Supabase setup
# - Prefer Streamlit secrets; fallback to local JSON if you used that earlier
#   (edit the file path if your local JSON lives elsewhere)
# ----------------------------------

resend.api_key = st.secrets["resend"]["api_key"]
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------
# Session state
# ----------------------------------
if "user" not in st.session_state:
    st.session_state.user = None

# ----------------------------------
# Helpers
# ----------------------------------
def signup(name: str, email: str, password: str, inviter_email: str):
    """
    Invite-only signup:
    - Verifies inviter exists and is_active
    - Creates Auth user (fails cleanly if email already exists in Auth)
    - Inserts users row (inactive), with invited_by set
    - Sends a message of type 'invite_request' to inviter
    """
    # 1) Check inviter exists and is active
    inviter = supabase.table("users").select("*") \
        .eq("email", inviter_email).eq("is_active", True).execute()
    if not inviter.data:
        return False, "Inviter email not found or inactive."
    inviter_id = inviter.data[0]["id"]

    # 2) Create Auth user
    resp = supabase.auth.sign_up({"email": email, "password": password})
    if not resp.user:
        return False, "This email is already registered. Please log in instead."

    auth_user_id = resp.user.get("id") if isinstance(resp.user, dict) else getattr(resp.user, "id", None)
    if not auth_user_id:
        return False, "Signup failed: no auth user id returned."

    # 3) Insert/Upsert app user (inactive until approved)
    supabase.table("users").upsert({
        "id": auth_user_id,
        "name": name,
        "email": email,
        "invited_by": inviter_id,
        "is_active": False
    }, on_conflict="id").execute()

    # 4) Create invite request message to inviter
    create_message(
        sender_id=response.user.id,
        receiver_id=inviter.data[0]["id"],
        content=f"{name} ({email}) has requested to join Trustlet.",
        message_type="invite_request",
        status="pending"
    )

    return True, "Signup successful! Check your inbox for an email from SupaBase Auth. You will receive another email when the nominated Existing User accepts your application."

def login(email: str, password: str):
    """
    Login via Supabase Auth; enforce users.is_active.
    Store simple dict in session (id, email, name).
    """
    response = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    if response.user:
        auth_user_id = response.user.get("id") if isinstance(response.user, dict) else getattr(response.user, "id", None)
        if not auth_user_id:
            return None
        user_row = supabase.table("users").select("*").eq("id", auth_user_id).execute()
        if user_row.data and user_row.data[0]["is_active"]:
            return {
                "id": auth_user_id,
                "email": email,
                "name": user_row.data[0]["name"]
            }
    return None

def send_email(to_email: str, subject: str, body: str):
    try:
        payload = {
            "from": st.secrets["resend"]["from_email"],
            "to": to_email,
            "subject": subject,
            "html": body
        }
        st.write("📤 Email payload:", payload)  # Debug payload
        result = resend.Emails.send(payload)
        st.write("📧 Email API result:", result)
    except Exception as e:
        st.error(f"Email failed: {e}")
        st.text(traceback.format_exc())

def send_email_debug(to_email, subject, body):
    payload = {
        "from": st.secrets["resend"]["from_email"],
        "to": [to_email],
        "subject": subject,
        "html": body
    }
    headers = {
        "Authorization": f"Bearer {st.secrets['resend']['api_key']}",
        "Content-Type": "application/json"
    }
    resp = requests.post("https://api.resend.com/emails", json=payload, headers=headers)
    st.write("Raw API response:", resp.status_code, resp.text)

def create_message(sender_id, receiver_id, content,
                   message_type="normal", listing_id=None,
                   status="sent", parent_message_id=None):
    # Build message dict
    msg = {
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "content": content,
        "message_type": message_type,
        "status": status,
        "is_active": True
    }
    if listing_id:
        msg["listing_id"] = listing_id
    if parent_message_id:
        msg["parent_message_id"] = parent_message_id  # ✅ include here

    # Insert into DB
    supabase.table("messages").insert(msg).execute()

    # Send email to recipient (only if found)
    recipient = supabase.table("users").select("email").eq("id", receiver_id).execute()
    if recipient.data:
        import html
        safe_content = html.escape(content).replace("\n", "<br>")
        send_email(
        #send_email_debug(
            to_email=recipient.data[0]["email"],
            subject=f"New Trustlet {message_type} message",
            body=f"<p>You have a new message:</p><p>{safe_content}</p>"
        )

ams_neighbourhood_options = ["Oost", "ZuidOost", "Centrum", "Westerpark", "Oud-West", "Oud-Zuid", "Noord"]
# ----------------------------------
# UI
# ----------------------------------

# ---------- Login / Signup ----------
if st.session_state.user is None:
    st.write('Welcome to Trustlet, the app for trusted lets.')
    menu = ["Login", "Sign Up"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Sign Up":
        st.subheader("Create an account")
        st.write('Requires an existing user to accept your application')
        name = st.text_input("Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        inviter_email = st.text_input("Existing User Email")
        if st.button("Sign Up"):
            success, msg = signup(name, email, password, inviter_email)
            if success:
                st.success(msg)
            else:
                st.error(msg)

    elif choice == "Login":
        st.subheader("Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = login(email, password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Login failed or account inactive")

# ---------- Logged-in UI ----------
else:
    user = st.session_state.user


    with st.sidebar:
        st.markdown("### Trustlet")
        st.write(f"Logged in as {user['email']}")
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()

    action = st.sidebar.selectbox(
        "Choose Action",
        ["Browse Listings", "Add/Remove Listings", "Messages"]
    )

    # ------------------- Browse Listings -------------------
    if action == "Browse Listings":
        st.subheader("Available Listings")

        # ---- Filters ----
        col1, col2 = st.columns(2)
        with col1:
            home_type = st.selectbox("Home Type", ["All", "Room only", "Entire home"])
            desired_start = st.date_input("Earliest start date", value=None)
            desired_end = st.date_input("Latest end date", value=None)
        with col2:
            max_cost = st.number_input("Max cost (€)", min_value=0, value=0)
            suburbs = st.multiselect(
                "Neighborhood(s)",
                ams_neighbourhood_options,  # just the list, no "All"
                default=[]  # start empty
            )

        # ---- Query base ----
        query = supabase.table("listings").select("*").eq("is_active", True)

        # Apply filters
        if suburbs:  # only apply if user picked something
            query = query.in_("location", suburbs)
        if home_type != "All":
            query = query.eq("home_type", home_type)
        if max_cost > 0:
            query = query.lte("cost", max_cost)
        if desired_start and desired_end:
            query = query.lte("start_date", desired_end.isoformat())
            query = query.gte("end_date", desired_start.isoformat())
        elif desired_start:
            # show listings that end after the desired_start
            query = query.gte("end_date", desired_start.isoformat())
        elif desired_end:
            # show listings that start before the desired_end
            query = query.lte("start_date", desired_end.isoformat())

        listings = query.order("start_date", desc=True).execute()

        # ---- Results ----
        if not listings.data:
            st.info("No listings match your filters.")
        else:
            for listing in listings.data or []:
                # Fetch lister info
                lister = supabase.table("users").select("name, created_at, invited_by").eq("id", listing["user_id"]).execute()
                lister_name = lister.data[0]["name"] if lister.data else "Unknown"
                created_at = lister.data[0]["created_at"] if lister.data else None

                member_since = ""
                if created_at:
                    member_since = datetime.fromisoformat(created_at.replace("Z","")).strftime("%b %Y")

                st.write(f"**{listing['title']}**")
                st.caption(f"Listed by {lister_name}. Member since {member_since}")

                st.write(f"🏠 {listing.get('home_type','')} — {listing.get('bedrooms', 1)} bedroom(s)")
                st.write(f"Location: {listing.get('street_name','')}, {listing['location']}")
                st.write(f"Cost: €{listing['cost']}")
                st.write(f"Available: {listing['start_date']} → {listing['end_date']}")
                if listing.get("photo_link"):
                    st.write(f"Photos: {listing['photo_link']}")

                # Show a button first
                if st.button("Send Message", key=f"btn_open_{listing['id']}"):
                    st.session_state[f"show_msg_{listing['id']}"] = True

                # If activated, show the form
                if st.session_state.get(f"show_msg_{listing['id']}", False):
                    st.info("Send a message to the owner (your email address will be sent)")
                    message_text = st.text_area(
                        f"Message for listing '{listing['title']}'",
                        key=f"msg_{listing['id']}",
                        placeholder="Introduce yourself, dates, etc."
                    )
                    if st.button("Submit", key=f"send_{listing['id']}"):
                        create_message(
                            sender_id=user['id'],
                            receiver_id=listing['user_id'],
                            listing_id=listing['id'],
                            content=f"Inquiry about '{listing['title']}'\n\n{message_text}",
                            message_type="normal"
                        )
                        st.success("Message sent!")

                        # Hide the form again after sending
                        st.session_state[f"show_msg_{listing['id']}"] = False

                st.markdown("---")
    # ------------------- Add/Remove Listings -------------------
    elif action == "Add/Remove Listings":
        st.subheader("Add a new listing")

        title = st.text_input("Title", placeholder="Cozy 1BR near Jordaan")
        home_type = st.selectbox("Home Type", ["Room only", "Entire home"])
        bedrooms = st.number_input("Number of bedrooms", min_value=1, step=1)
        street_name = st.text_input("Street name")
        location = st.selectbox("Neighborhood", ams_neighbourhood_options)
        cost = st.number_input("Cost (€)", min_value=0)
        start_date = st.date_input("Start Date")
        end_date = st.date_input("End Date")
        photo_link = st.text_input("Photo Link (Google Drive / Dropbox)")

        if st.button("Submit Listing"):
            supabase.table("listings").insert({
                "user_id": user['id'],
                "title": (title or "").strip() or "Untitled listing",
                "home_type": home_type,
                "bedrooms": bedrooms,
                "location": location,
                "street_name": street_name,
                "cost": cost,
                "start_date": start_date.isoformat(),  # fix: date -> string
                "end_date": end_date.isoformat(),      # fix: date -> string
                "photo_link": photo_link,
                "is_active": True
            }).execute()
            st.success("Listing added!")

        st.markdown("---")
        st.subheader("Your listings (activate/deactivate)")

        mine = supabase.table("listings").select("*").eq("user_id", user['id']).order("created_at", desc=True).execute()
        if not mine.data:
            st.info("You have no listings yet.")
        else:
            for lst in mine.data:
                cols = st.columns([3, 2, 2, 2, 2])
                with cols[0]:
                    st.write(f"**{lst['title']}**")
                    st.caption(f"{lst.get('home_type','')} — {lst.get('bedrooms',1)} BR — {lst['location']}")
                with cols[1]:
                    st.write(f"€{lst['cost']}")
                with cols[2]:
                    st.write(f"{lst['start_date']} → {lst['end_date']}")
                with cols[3]:
                    st.write("Active ✅" if lst['is_active'] else "Inactive ⛔")
                with cols[4]:
                    if lst['is_active']:
                        if st.button("Deactivate", key=f"deact_{lst['id']}"):
                            supabase.table("listings").update({"is_active": False}).eq("id", lst["id"]).execute()
                            st.success("Listing deactivated")
                            st.rerun()
                    else:
                        if st.button("Activate", key=f"act_{lst['id']}"):
                            supabase.table("listings").update({"is_active": True}).eq("id", lst["id"]).execute()
                            st.success("Listing activated")
                            st.rerun()

    # ------------------- Messages (includes approvals) -------------------
    elif action == "Messages":
        st.subheader("Inbox")

        # Only fetch active messages; handled invite requests will be hidden by status != 'pending'
        inbox = supabase.table("messages").select("*") \
            .eq("receiver_id", user['id']).eq("is_active", True) \
            .order("sent_at", desc=True).execute()

        for msg in inbox.data or []:
            # Sender info
            sender = supabase.table("users").select("name,email").eq("id", msg['sender_id']).execute()
            sender_name = sender.data[0]["name"] if sender.data else "Unknown"
            sender_email = sender.data[0]["email"] if sender.data else "Unknown"

            # INVITE REQUESTS
            if msg.get("message_type") == "invite_request":
                # Only show pending requests
                if msg.get("status") != "pending":
                    continue

                st.write(f"Membership request from {sender_name} ({sender_email})")
                c1, c2, c3 = st.columns(3)

                with c1:
                    if st.button(f"Approve {sender_email}", key=f"approve_{msg['id']}"):
                        # Activate user + update invite request
                        supabase.table("users").update({"is_active": True}) \
                            .eq("id", msg["sender_id"]).execute()
                        supabase.table("messages").update({"status": "approved"}) \
                            .eq("id", msg["id"]).execute()

                        # Insert a welcome system message
                        create_message(
                            sender_id=user['id'],
                            receiver_id=msg["sender_id"],
                            content="✅ Your membership request has been approved. Welcome to Trustlet!",
                            message_type="system",
                            status="sent"
                        )
                        st.success(f"Approved {sender_email}")
                        st.rerun()

                with c2:
                    if st.button(f"Reject {sender_email}", key=f"reject_{msg['id']}"):
                        # Optional: delete the user entirely on rejection
                        supabase.table("users").update({"is_active": False}).eq("id", msg["sender_id"]).execute()
                        supabase.table("messages").update({"status": "rejected"}).eq("id", msg["id"]).execute()
                        st.info(f"Rejected {sender_email}")
                        st.rerun()

                with c3:
                    if st.button("Delete", key=f"del_{msg['id']}"):
                        supabase.table("messages").update({"is_active": False}) \
                            .eq("id", msg["id"]).execute()
                        st.success("Removed from inbox")
                        st.rerun()

            # NORMAL MESSAGE (or any non-invite message)
            else:
                # Show listing title context if present
                title_line = ""
                if msg.get("listing_id"):
                    lst = supabase.table("listings").select("title").eq("id", msg["listing_id"]).execute()
                    if lst.data:
                        title_line = f" — regarding **{lst.data[0]['title']}**"

                st.write(f"From: {sender_name} ({sender_email}){title_line}")
                st.write(msg["content"])

                # Reply + Delete actions
                reply_text = st.text_area("Reply", key=f"reply_{msg['id']}", placeholder="Type your reply…")
                r1, r2 = st.columns(2)
                with r1:
                    if st.button("Reply", key=f"send_reply_{msg['id']}"):
                        create_message(
                            sender_id=user['id'],
                            receiver_id=msg['sender_id'],
                            listing_id=msg.get("listing_id"),
                            content=reply_text,
                            message_type="reply",
                            parent_message_id=msg["id"]
                        )
                        st.success("Reply sent")
                        st.rerun()
                with r2:
                    if st.button("Delete", key=f"delete_{msg['id']}"):
                        supabase.table("messages").update({"is_active": False}).eq("id", msg["id"]).execute()
                        st.success("Message removed from inbox")
                        st.rerun()

            st.markdown("---")
