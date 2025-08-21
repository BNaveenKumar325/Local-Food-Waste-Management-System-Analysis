
import os
import re
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus

# =============================
# Configuration
# =============================
DATA_PATH = "Cleaned Data.csv"  # Keep your CSV next to app.py
REQUIRED_COLUMNS = {
    "id": ["id", "record_id", "sr_no", "sno", "index"],
    "city": ["city", "location", "area", "district", "place", "town"],
    "name": ["provider", "provider_name", "name", "organisation", "organization", "org", "ngo", "restaurant"],
    "role": ["role", "type", "entity", "party", "stakeholder"],  # expected values: Provider/Receiver (case-insensitive)
    "food_type": ["food_type", "food", "category", "cuisine"],
    "meal_type": ["meal_type", "meal", "course"],  # optional
    "phone": ["phone", "mobile", "contact", "contact_number", "phone_no", "phone_number"],
    "email": ["email", "mail", "email_id"],
    "address": ["address", "addr", "street"],
    "notes": ["notes", "remarks", "comment", "comments", "description"],
}

DEFAULT_COLUMNS = ["id","city","name","role","food_type","meal_type","phone","email","address","notes"]

# =============================
# Helpers
# =============================
def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())

def try_match_column(df_cols, candidates):
    nmap = {normalize(c): c for c in df_cols}
    for cand in candidates:
        key = normalize(cand)
        if key in nmap:
            return nmap[key]
    # try fuzzy contains
    for col in df_cols:
        if any(normalize(alias) in normalize(col) for alias in candidates):
            return col
    return None

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    dfc = df.copy()
    # Build column mapping
    mapping = {}
    for target, aliases in REQUIRED_COLUMNS.items():
        src = try_match_column(dfc.columns, aliases)
        mapping[target] = src

    # Interactive mapping if missing
    missing = [k for k, v in mapping.items() if v is None and k in ["city","name","role","food_type","phone"]]
    if missing:
        st.warning("Some required columns were not found. Map them below.")
        for k in missing:
            mapping[k] = st.selectbox(
                f"Select column for **{k}**",
                options=[None] + list(dfc.columns),
                key=f"map_{k}",
            )
        if any(mapping[k] is None for k in missing):
            st.stop()

    # Create unified dataframe
    unified = pd.DataFrame()
    for target in DEFAULT_COLUMNS:
        src = mapping.get(target)
        if src in dfc.columns:
            unified[target] = dfc[src]
        else:
            unified[target] = ""

    # Coerce ID
    if unified["id"].isna().all() or (unified["id"] == "").all():
        # generate ids
        unified["id"] = range(1, len(unified) + 1)
    else:
        # ensure uniqueness
        unified["id"] = pd.factorize(unified["id"])[0] + 1

    # Normalize role values
    def normalize_role(v):
        t = str(v).strip().lower()
        if "receiv" in t or t in {"receiver","acceptor","beneficiary"}:
            return "Receiver"
        return "Provider" if t else "Provider"

    unified["role"] = unified["role"].apply(normalize_role)

    # Clean phone
    unified["phone"] = unified["phone"].astype(str).apply(lambda x: re.sub(r"\D+", "", x))
    # Fill NaNs
    unified = unified.fillna("")
    return unified

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.info(f"'{path}' not found. A new file will be created on first Save.")
        return pd.DataFrame(columns=DEFAULT_COLUMNS)
    try:
        df = pd.read_csv(path)
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="latin-1")
    return df

def save_data(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)

def whatsapp_link(phone: str, msg: str) -> str:
    phone_digits = re.sub(r"\D+", "", str(phone))
    return f"https://wa.me/{phone_digits}?text={quote_plus(msg)}"

def tel_link(phone: str) -> str:
    phone_digits = re.sub(r"\D+", "", str(phone))
    return f"tel:{phone_digits}"

def mailto_link(email: str, subject: str, body: str) -> str:
    return f"mailto:{email}?subject={quote_plus(subject)}&body={quote_plus(body)}"

# =============================
# App
# =============================
st.set_page_config(page_title="Food Donation Directory", page_icon="🍲", layout="wide")

st.title("🍲 Food Donation Directory")
st.caption("Filter records, contact providers/receivers, and manage data (CRUD).")

# Load & normalize data
raw_df = load_data(DATA_PATH)
if raw_df.empty and not os.path.exists(DATA_PATH):
    st.info("Start by adding your first record in the '➕ Add New' tab.")

with st.expander("📑 Preview & Column Mapping (optional)", expanded=False):
    if not raw_df.empty:
        st.dataframe(raw_df.head(20), use_container_width=True)
    st.caption("If your column names differ, the app will try to auto-map. Use the mapping UI if prompted below.")

df = ensure_schema(raw_df)

# Persist in session for safe editing
if "data" not in st.session_state:
    st.session_state.data = df.copy()
if "next_id" not in st.session_state:
    st.session_state.next_id = (st.session_state.data["id"].max() or 0) + 1

tab_filter, tab_add, tab_edit = st.tabs(["🔎 Filter & Contact", "➕ Add New", "✏️ Edit / Delete"])

# -----------------------------
# Filter & Contact
# -----------------------------
with tab_filter:
    left, right = st.columns([1,3])
    with left:
        cities = sorted([c for c in st.session_state.data["city"].dropna().astype(str).unique() if c])
        providers = sorted([c for c in st.session_state.data["name"].dropna().astype(str).unique() if c])
        food_types = sorted([c for c in st.session_state.data["food_type"].dropna().astype(str).unique() if c])
        roles = ["Provider", "Receiver"]

        st.subheader("Filters")
        f_city = st.multiselect("City", cities)
        f_name = st.multiselect("Name / Organisation", providers)
        f_food = st.multiselect("Food Type", food_types)
        f_role = st.multiselect("Role", roles, default=roles)

        temp = st.session_state.data.copy()
        if f_city: temp = temp[temp["city"].isin(f_city)]
        if f_name: temp = temp[temp["name"].isin(f_name)]
        if f_food: temp = temp[temp["food_type"].isin(f_food)]
        if f_role: temp = temp[temp["role"].isin(f_role)]

        st.markdown("---")
        st.download_button("⬇️ Download filtered CSV", data=temp.to_csv(index=False), file_name="filtered_food_directory.csv", mime="text/csv")

    with right:
        st.subheader("Results")
        if len(temp) == 0:
            st.warning("No records found. Adjust filters.")
        else:
            # Show table with contact actions
            def contact_buttons(row):
                phone = str(row["phone"])
                email = str(row["email"])
                who = f'{row["name"]} ({row["role"]}) in {row["city"]}'
                default_msg = f"Hello {row['name']}, reaching out via the Food Donation Directory."
                w_url = whatsapp_link(phone, default_msg) if phone else ""
                t_url = tel_link(phone) if phone else ""
                m_url = mailto_link(email, "Food Donation Coordination", default_msg) if email else ""
                parts = []
                if phone:
                    parts.append(f"[Call]({t_url})")
                    parts.append(f"[WhatsApp]({w_url})")
                if email:
                    parts.append(f"[Email]({m_url})")
                return " • ".join(parts) if parts else ""

            view = temp[["id","name","role","city","food_type","meal_type","phone","email","address","notes"]].copy()
            view["contact"] = temp.apply(contact_buttons, axis=1)
            st.dataframe(view, use_container_width=True, column_config={
                "contact": st.column_config.Column("Contact", help="Call / WhatsApp / Email"),
            })

# -----------------------------
# Add New
# -----------------------------
with tab_add:
    st.subheader("Add a New Record")
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Name / Organisation *")
            role = st.selectbox("Role *", ["Provider", "Receiver"])
            city = st.text_input("City *")
        with c2:
            food_type = st.text_input("Food Type *", placeholder="e.g., Veg meals, Biryani, Bread, Packaged")
            meal_type = st.text_input("Meal Type", placeholder="e.g., Breakfast/Lunch/Dinner")
            phone = st.text_input("Phone", placeholder="Digits only or will be cleaned")
        with c3:
            email = st.text_input("Email", placeholder="example@domain.com")
            address = st.text_area("Address", height=90)
        notes = st.text_area("Notes", placeholder="Any special instructions or capacity, timing etc.", height=80)

        submitted = st.form_submit_button("➕ Add Record")
        if submitted:
            if not name or not role or not city or not food_type:
                st.error("Please fill all required fields (*)")
            else:
                rid = int(st.session_state.next_id)
                st.session_state.next_id += 1
                new_row = {
                    "id": rid,
                    "city": city.strip(),
                    "name": name.strip(),
                    "role": role,
                    "food_type": food_type.strip(),
                    "meal_type": meal_type.strip(),
                    "phone": re.sub(r"\D+", "", phone),
                    "email": email.strip(),
                    "address": address.strip(),
                    "notes": notes.strip(),
                }
                st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame([new_row])], ignore_index=True)
                save_data(st.session_state.data[DEFAULT_COLUMNS], DATA_PATH)
                st.success(f"Record added (ID #{rid}) and saved to '{DATA_PATH}'.")

# -----------------------------
# Edit / Delete
# -----------------------------
with tab_edit:
    st.subheader("Edit or Delete Records")
    data = st.session_state.data.sort_values("id").reset_index(drop=True)
    st.caption("Tip: Select a row by ID to edit; use the delete area to remove records.")

    # Select record to edit
    ids = data["id"].tolist()
    sel_id = st.selectbox("Select ID to edit", options=ids if ids else [None])
    if sel_id is not None:
        row = data[data["id"] == sel_id].iloc[0]
        with st.form("edit_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                name_e = st.text_input("Name / Organisation *", row["name"])
                role_e = st.selectbox("Role *", ["Provider", "Receiver"], index=0 if row["role"] == "Provider" else 1)
                city_e = st.text_input("City *", row["city"])
            with c2:
                food_type_e = st.text_input("Food Type *", row["food_type"])
                meal_type_e = st.text_input("Meal Type", row["meal_type"])
                phone_e = st.text_input("Phone", row["phone"])
            with c3:
                email_e = st.text_input("Email", row["email"])
                address_e = st.text_area("Address", row["address"], height=90)
            notes_e = st.text_area("Notes", row["notes"], height=80)

            save_btn = st.form_submit_button("💾 Save Changes")
            if save_btn:
                if not name_e or not city_e or not food_type_e:
                    st.error("Please fill all required fields (*)")
                else:
                    st.session_state.data.loc[st.session_state.data["id"] == sel_id, DEFAULT_COLUMNS] = [
                        sel_id,
                        city_e.strip(),
                        name_e.strip(),
                        role_e,
                        food_type_e.strip(),
                        meal_type_e.strip(),
                        re.sub(r"\D+", "", phone_e),
                        email_e.strip(),
                        address_e.strip(),
                        notes_e.strip(),
                    ]
                    save_data(st.session_state.data[DEFAULT_COLUMNS], DATA_PATH)
                    st.success(f"Saved changes for ID #{sel_id}.")

    st.markdown("---")
    st.subheader("Delete Records")
    del_ids = st.multiselect("Choose IDs to delete", options=ids, help="Hold Ctrl/Cmd to select multiple")
    if st.button("🗑️ Delete Selected"):
        if del_ids:
            st.session_state.data = st.session_state.data[~st.session_state.data["id"].isin(del_ids)].copy()
            save_data(st.session_state.data[DEFAULT_COLUMNS], DATA_PATH)
            st.success(f"Deleted IDs: {del_ids}")
        else:
            st.info("No IDs selected.")

st.markdown("---")
colA, colB = st.columns([1,1])
with colA:
    if st.button("💾 Save All Changes"):
        save_data(st.session_state.data[DEFAULT_COLUMNS], DATA_PATH)
        st.success(f"All changes saved to '{DATA_PATH}'.")
with colB:
    st.download_button("⬇️ Download full CSV", data=st.session_state.data[DEFAULT_COLUMNS].to_csv(index=False), file_name="food_directory_full.csv", mime="text/csv")


