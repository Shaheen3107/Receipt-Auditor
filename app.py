import hashlib
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from groq import APIConnectionError, AuthenticationError, Groq, RateLimitError
from PIL import Image

from receipt_extractor import ask_receipt

st.set_page_config(page_title="Receipt Auditor", page_icon="🧾", layout="wide")

SAMPLE_DIR = Path("samples")
MAX_SIDE = 2000          # shrink very large phone photos before sending them
DEMO_READS_PER_SESSION = 5   # reads allowed with the shared demo key (only if the owner set one)


def check_items(receipt):
    """Do the item prices add up? Returns (status, message). status is ok, warning or info."""
    items_sum = sum(item.price for item in receipt.items)
    if receipt.subtotal is not None:
        if items_sum == receipt.subtotal:
            return "ok", f"Items add up to the subtotal ({items_sum:,})."
        return "warning", (f"Items add up to {items_sum:,} but the subtotal is {receipt.subtotal:,}. "
                           "The AI may have misread a price, or the receipt has a discount. "
                           "Please check the photo.")
    if receipt.total is not None and items_sum == receipt.total:
        return "ok", f"Items add up to the total ({items_sum:,})."
    return "info", ("No subtotal on this receipt, so the items cannot be checked. "
                    "Tax or service charge may explain a gap.")


def demo_key():
    """The owner's shared key, set in Streamlit Secrets. None if there is no secret (then visitors use their own)."""
    try:
        return st.secrets.get("GROQ_API_KEY") or None
    except Exception:
        return None


# ── Sidebar: the visitor's own Groq key ──
with st.sidebar:
    st.header("🔑 Groq API key")
    api_key = st.text_input("Paste your key", type="password", value=os.environ.get("GROQ_API_KEY", ""))
    st.markdown("[Get a free key](https://console.groq.com/keys)")
    if demo_key():
        st.caption(f"No key? You can try {DEMO_READS_PER_SESSION} receipts with the shared demo key. "
                   "For more, paste your own.")
    st.caption("Your receipt photo is sent to Groq to be read. This app does not store it. "
               "Do not upload receipts you are not comfortable sharing with an API provider.")

# ── Header ──
st.title("🧾 Receipt Auditor")
st.markdown("Upload a receipt photo and a vision AI reads the items and totals. A simple check then tells you "
            "whether the numbers add up.")
st.caption("Tested on 50 receipts from the CORD dataset (Indonesian rupiah): exact total correct on 50 of 50. "
           "It may do worse on crumpled photos, other languages or other currencies.")
st.divider()

# ── Input: upload a photo, or pick a sample ──
left, right = st.columns(2)
image, source_name = None, None

with left:
    st.subheader("📎 Receipt photo")
    uploaded = st.file_uploader("Upload a JPG or PNG", type=["jpg", "jpeg", "png"])
    samples = sorted(p.name for p in SAMPLE_DIR.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}) \
        if SAMPLE_DIR.exists() else []
    chosen = st.selectbox("...or try a sample receipt", ["(none)"] + samples) if samples else "(none)"

    if uploaded is not None:
        image, source_name = Image.open(uploaded), uploaded.name
    elif chosen != "(none)":
        image, source_name = Image.open(SAMPLE_DIR / chosen), chosen

    if image is not None:
        st.image(image, caption=source_name, width=240)

with right:
    st.subheader("🔍 Result")

    if image is None:
        st.info("Upload a receipt photo (or pick a sample) and the result appears here.")
    else:
        # A photo is identified by its content, so the same photo is never read twice on a page refresh
        file_id = hashlib.md5(uploaded.getvalue()).hexdigest() if uploaded is not None else f"sample:{chosen}"
        stored = st.session_state.get("result")

        if stored is None or stored["file_id"] != file_id:
            user_key = api_key.strip()
            shared_key = demo_key()
            used = st.session_state.get("demo_reads", 0)
            using_demo = not user_key and shared_key is not None

            if not user_key and shared_key is None:
                st.info("Add your free Groq API key in the sidebar and the photo will be read.")
            elif using_demo and used >= DEMO_READS_PER_SESSION:
                st.warning("The demo reads are used up. Paste your own free Groq key in the sidebar to continue.")
            else:
                photo = image.copy()
                photo.thumbnail((MAX_SIDE, MAX_SIDE))
                stored = {"file_id": file_id, "receipt": None, "error": None}
                try:
                    with st.spinner("Reading the receipt..."):
                        stored["receipt"] = ask_receipt(Groq(api_key=user_key or shared_key), photo)
                    if using_demo:
                        st.session_state["demo_reads"] = used + 1
                except AuthenticationError:
                    stored["error"] = ("The demo key is not working right now. Paste your own free Groq key in the sidebar."
                                       if using_demo else "Groq rejected the API key. Check the key in the sidebar.")
                except RateLimitError:
                    stored["error"] = ("The shared demo allowance is used up for now. Paste your own free Groq key "
                                       "in the sidebar to continue."
                                       if using_demo else
                                       "Groq's free-tier limit was reached. Wait a few minutes and press 'Read again' "
                                       "(a daily limit may need longer).")
                except APIConnectionError:
                    stored["error"] = "Could not reach Groq. Check your internet connection and press 'Read again'."
                except Exception as problem:
                    stored["error"] = f"Something went wrong: {type(problem).__name__}. Press 'Read again' to retry."
                st.session_state["result"] = stored

        stored = st.session_state.get("result")
        if stored is not None and stored["file_id"] == file_id:
            receipt = stored["receipt"]
            if stored["error"]:
                st.error(stored["error"])
            elif receipt is None:
                st.error("The AI's answer was not valid after 3 tries. Try a clearer photo.")
            else:
                c1, c2 = st.columns([1, 2])
                c1.metric("Total", f"{receipt.total:,}" if receipt.total is not None else "not shown")
                c2.markdown(f"**Store:** {receipt.store_name or 'not shown'}  \n"
                            f"**Date:** {receipt.date or 'not shown'}")

                if receipt.items:
                    st.dataframe(pd.DataFrame([item.model_dump() for item in receipt.items]),
                                 width="stretch", hide_index=True)
                else:
                    st.write("No items found.")

                if receipt.subtotal is not None:
                    st.caption(f"Subtotal: {receipt.subtotal:,}")

                status, message = check_items(receipt)
                {"ok": st.success, "warning": st.warning, "info": st.info}[status](message)
                st.caption("The AI can make mistakes. Compare the result with the photo before relying on it.")

            # Clearing the stored result makes the next run read the photo again
            st.button("Read again", on_click=lambda: st.session_state.pop("result", None))
