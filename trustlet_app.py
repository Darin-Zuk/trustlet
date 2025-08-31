import streamlit as st
from supabase import create_client, Client
import json
from datetime import datetime
import resend
import traceback
import html
import requests
import streamlit.components.v1 as components




# ----------------------------------
# Page setup
# ----------------------------------
st.set_page_config(page_title="Trustlet", layout="wide")


# Hide Streamlit footer and "Fork/GitHub" badge
hide_streamlit_style = """
    <style>
    /* What already worked */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    div[class*="stToolbar"] {visibility: hidden !important;}
    div[class*="stDecoration"] {visibility: hidden !important;}
    div[class*="viewerBadge"] {visibility: hidden !important;}

    /* Brute force: hide any fixed bottom bars */
    div[style*="position: fixed"][style*="bottom: 0"] {
        display: none !important;
    }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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


APP_URL = "https://trustlet.streamlit.app"
BETA_MAX_USERS = 50
# ----------------------------------
# Helpers
# ----------------------------------
def signup(name, email, password, inviter_email):
    if not name or not email or not password or not inviter_email:
        return False, "All fields (Name, Email, Password, Existing User Email) are required."

    try:
        inviter = supabase.table("users").select("*").eq("email", inviter_email).eq("is_active", True).execute()
        if not inviter.data:
            return False, "Inviter email not found or inactive."

        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "email_redirect_to": "https://trustlet-verify.streamlit.app"
            }
        })

        # Normalize user ID (same as login)
        auth_user_id = response.user.get("id") if isinstance(response.user, dict) else getattr(response.user, "id", None)
        if not auth_user_id:
            return False, "Signup failed: could not retrieve user ID (account may already exist)."

        # Check for duplicate email error
        if hasattr(response, "error") and response.error:
            if "already registered" in str(response.error).lower():
                return False, "This email is already registered. Please log in instead."
            return False, f"Signup failed: {response.error}"

        # Insert into users
        supabase.table("users").insert({
            "id": auth_user_id,
            "name": name,
            "email": email,
            "invited_by": inviter.data[0]["id"],
            "is_active": False
        }).execute()

        # Create invite request message
        create_message(
            sender_id=auth_user_id,
            receiver_id=inviter.data[0]["id"],
            content=f"{name} ({email}) has requested to join Trustlet. Check your inbox in the app to approve.",
            message_type="invite_request",
            status="pending"   # <-- FIXi dont 
        )

        return True, "Signup successful! Check your inbox for an email from SupaBase Auth. You will receive another email when the nominated Existing User accepts your application."

    except Exception as e:
        return False, f"An error occurred during signup: {str(e)}"


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
            "from": f"Trustlet Team <{st.secrets['resend']['from_email']}>",
            "to": [to_email],
            "subject": subject,
            "html": body
        }
        #st.write("📤 Email payload:", payload)  # Debug payload
        result = resend.Emails.send(payload)
        #st.write("📧 Email API result:", result)
    except Exception as e:
        st.error(f"Email failed: {e}")
        st.text(traceback.format_exc())



def build_email(message_type, context=None, content=""):
    if message_type == "invite_request":
        return (
            "New membership request on Trustlet",
            f"<p>{content}</p>"
            f"<p>To view or respond, please visit your "
            f"<a href='{APP_URL}'>Trustlet inbox</a>.</p>"
        )
    elif message_type == "inquiry":
        sender_name = context.get("sender_name", "A Trustlet member")
        listing_title = context.get("listing_title", "your listing")

        return (
            f"New inquiry about your listing '{listing_title}'",
            f"""
            <h3>📩 New Inquiry</h3>
            <p><strong>From:</strong> {sender_name}</p>
            
            <p><em>{content}</em></p>

            <hr>
            <p>To reply or view details, go to your 
            <a href="{APP_URL}">Trustlet inbox</a>.</p>
            """
        )

    elif message_type == "reply":
        sender_name = context.get("sender_name", "A Trustlet member")

        return (
            "You received a reply on Trustlet",
            f"""
            <h3>💬 New Reply</h3>
            <p><strong>From:</strong> {sender_name}</p>

            <p><em>{content}</em></p>


            <hr>
            <p>To reply or view the full conversation, go to your 
            <a href="{APP_URL}">Trustlet inbox</a>.</p>
            """
        )
        
    elif message_type == "system":
        return (
            "Trustlet notification",
            f"<p>{content}</p>"
            f"<p>You can view this update in your "
            f"<a href='{APP_URL}'>Trustlet inbox</a>.</p>"
        )
    else:
        return (
            "New message in Trustlet inbox",
            f"<p>{content}</p>"
            f"<p>Check your <a href='{APP_URL}'>Trustlet inbox</a> for details.</p>"
        )





def create_message(
    sender_id,
    receiver_id,
    content,
    message_type="uncategorized",
    status="sent",
    context=None,
    email_subject=None,
    email_body=None,
    listing_id=None
):
    """
    Create a message in the database and send an email notification.

    - Inserts the message into `messages`
    - Builds email subject/body via build_email

    """
    if context is None:
        context = {}

    try:
        # Insert into database
        msg = (
            supabase.table("messages")
            .insert(
                {
                    "sender_id": sender_id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "message_type": message_type,
                    "status": status,
                    "listing_id": listing_id,
                }
            )
            .execute()
        )
        if not msg.data:
            st.error("❌ Failed to create message in database.")
            return None

        # Lookup receiver email
        receiver = (
            supabase.table("users")
            .select("email, name")
            .eq("id", receiver_id)
            .execute()
        )
        if not receiver.data:
            st.warning("⚠️ Receiver not found in users table.")
            return msg.data[0]

        to_email = receiver.data[0]["email"]



        # Always include sender name in context
        sender = (
            supabase.table("users")
            .select("name")
            .eq("id", sender_id)
            .execute()
        )
        if sender.data:
            context["sender_name"] = sender.data[0]["name"]

        # Build email subject + body
        subject, body = build_email(message_type, context, content)

        # Allow overrides
        subject = email_subject or subject
        body = email_body or body

        # Send email
        send_email(to_email, subject, body)

        return msg.data[0]

    except Exception as e:
        st.error(f"❌ Error creating message: {str(e)}")
        return None



ams_neighbourhood_options = ["Oost", "ZuidOost", "Centrum", "Westerpark", "Oud-West", "Oud-Zuid", "Noord"]
# ----------------------------------
# UI
# ----------------------------------

# ---------- Login / Signup ----------
if st.session_state.user is None:
    st.write('Welcome to Trustlet, the app for trusted lets.')

    st.markdown(
        "[👉 What is Trustlet?](https://docs.google.com/document/d/1M4ftORvdUBx-xdMUpaCEBxdBLGTBWj7VDNk9jtv0LQg/edit?tab=t.0)",
        unsafe_allow_html=True
    )

    menu = ["Sign Up","Login"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Sign Up":
        st.subheader("Create an account")
        st.write('Requires an existing user to accept your application')

        # Compute whether the beta is full
        beta_resp = supabase.table("users").select("id", count="exact").execute()
        beta_count = getattr(beta_resp, "count", None)
        if beta_count is None:
            beta_count = len(beta_resp.data or [])
        is_full = beta_count >= BETA_MAX_USERS

        name = st.text_input("Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        inviter_email = st.text_input("Existing User Email")

        if is_full:
            st.warning(f"🚧 Beta limit reached ({beta_count}/{BETA_MAX_USERS}). Sign-ups are temporarily closed.")
        # Disable the button if full
        if st.button("Sign Up", disabled=is_full):
            with st.spinner("⏳ Signing you up... please wait"):
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
            if not email or not password:
                st.error("⚠️ Please enter both email and password.")
            else:
                try:
                    response = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })

                    if not response.user:
                        st.error("❌ Invalid email or password.")
                    else:
                        auth_user_id = response.user.get("id") if isinstance(response.user, dict) else getattr(response.user, "id", None)
                        if not auth_user_id:
                            st.error("❌ Could not retrieve user ID.")
                        else:
                            user_row = supabase.table("users").select("*").eq("id", auth_user_id).execute()
                            if not user_row.data:
                                st.error("❌ User not found in Trustlet database.")
                            elif not user_row.data[0].get("is_active"):
                                st.warning("⏳ Your account exists but has not yet been activated by an inviter.")
                            else:
                                st.session_state.user = user_row.data[0]
                                st.success("✅ Logged in successfully!")
                                st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

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

        listings = query.order("start_date", desc=False).execute()

        # ---- Results ----
        count = len(listings.data or [])

        if count == 0:
            st.info("No listings match your filters.")
        else:
            st.success(f"{count} listing{'s' if count > 1 else ''} available")

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


                # Parse dates (assuming they are in "YYYY-MM-DD" format)
                start = datetime.strptime(listing["start_date"], "%Y-%m-%d").date()
                end = datetime.strptime(listing["end_date"], "%Y-%m-%d").date()

                nights = (end - start).days
                total_cost = listing["cost"]
                per_night = total_cost / nights if nights > 0 else total_cost

                st.write(f"Cost: €{total_cost} (€{per_night:.2f} per night)")


                #date format to dd/mm for listings
                start_fmt = datetime.strptime(listing['start_date'], "%Y-%m-%d").strftime("%d/%m/%y")
                end_fmt = datetime.strptime(listing['end_date'], "%Y-%m-%d").strftime("%d/%m/%y")

                st.write(f"Available: {start_fmt} → {end_fmt}")
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
                            message_type="inquiry"
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
            .order("created_at", desc=True).execute()

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
                            status="sent",
                            email_subject="🎉 Welcome to Trustlet – Your membership has been approved!",
                            email_body=f"""
                                <p>Hi there,</p>
                                <p>Good news – your membership request has been <strong>approved</strong> 🎉</p>
                                <p>You can now <a href="https://trustlet.streamlit.app">log in to Trustlet</a>.</p>
                                <p>The Trustlet Team</p>
                            """
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
                        )
                        st.success("Reply sent")
                        st.rerun()
                with r2:
                    if st.button("Delete", key=f"delete_{msg['id']}"):
                        supabase.table("messages").update({"is_active": False}).eq("id", msg["id"]).execute()
                        st.success("Message removed from inbox")
                        st.rerun()

            st.markdown("---")

#st.markdown("---")
st.caption("💬 For any issues, email admin@amstrustlet.app")