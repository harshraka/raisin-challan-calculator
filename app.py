import json
import os
import re
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Challan Calculator", page_icon="🧾", layout="centered")
st.title("🧾 Raisin Challan Calculator")
st.caption("Upload a delivery challan photo. Check the AI-read figures before accepting the amount.")

st.info(
    "Rule: a fraction like 63/15 means 63 boxes × 15 kg each. "
    "A separate 1/13.3 means 1 box × 13.3 kg."
)

api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
if not api_key:
    st.warning("Add your Gemini API key in Streamlit Secrets (or set GEMINI_API_KEY locally) to enable photo reading.")

uploaded = st.file_uploader("Upload challan photo", type=["jpg", "jpeg", "png", "webp"])

def parse_decimal(value, field):
    try:
        cleaned = str(value).replace(",", "").replace("₹", "").strip()
        if not cleaned:
            raise ValueError
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Please enter a valid number for {field}.")

def extract_challan(image_bytes, mime_type, key):
    client = genai.Client(api_key=key)
    prompt = """
Read this handwritten delivery challan and return ONLY valid JSON, no markdown.
Use this exact schema:
{
  "date": "date written on challan or empty string",
  "customer": "customer name if readable or empty string",
  "lots": [
    {
      "lot_mark": "e.g. ALC-64",
      "declared_boxes": 64,
      "weight_entries": [
        {"boxes": 63, "kg_per_box": 15},
        {"boxes": 1, "kg_per_box": 13.3}
      ],
      "rate_per_kg": 250,
      "notes": "uncertainty or empty string"
    }
  ],
  "uncertain_fields": ["list any unclear fields"]
}
Interpretation rules:
- In the weight column, numerator is number of boxes and denominator is kg per box.
- Example: 63/15 means 63 boxes each weighing 15 kg; 1/13.3 means 1 box weighing 13.3 kg.
- The lot mark ALC-64 indicates 64 boxes for that lot; it is not the weight.
- Rate is in the last rate column and is per kilogram.
- Read handwriting conservatively. Do not invent unreadable numbers; use null and explain in notes/uncertain_fields.
- A lot may have multiple weight entries. Return all entries for that lot.
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
    )
    return json.loads(response.text)

if uploaded:
    st.image(uploaded, caption="Uploaded challan", use_container_width=True)
    if st.button("Read challan with AI", type="primary", disabled=not api_key):
        with st.spinner("Reading handwriting…"):
            try:
                st.session_state["extracted"] = extract_challan(
                    uploaded.getvalue(), uploaded.type or "image/jpeg", api_key
                )
                st.session_state["source_name"] = uploaded.name
            except Exception as e:
                st.error(f"Could not read the image: {e}")
                st.caption("Check that the API key is valid and the free-tier quota is available.")

if "extracted" in st.session_state:
    data = st.session_state["extracted"]
    st.subheader("1. Review extracted details")
    date = st.text_input("Challan date", value=str(data.get("date") or ""))
    customer = st.text_input("Customer name", value=str(data.get("customer") or ""))

    lots = data.get("lots", [])
    if not lots:
        st.warning("No lot rows were detected. Try a clearer, straight-on photo.")
    results = []
    for idx, lot in enumerate(lots):
        st.markdown(f"### Lot {idx + 1}")
        lot_mark = st.text_input("Lot mark", value=str(lot.get("lot_mark") or ""), key=f"mark_{idx}")
        declared_boxes = st.number_input(
            "Declared box count (from lot mark)", min_value=0, step=1,
            value=int(lot.get("declared_boxes") or 0), key=f"declared_{idx}"
        )
        rate_raw = lot.get("rate_per_kg")
        rate_default = float(rate_raw) if isinstance(rate_raw, (int, float)) else 0.0
        rate = st.number_input("Rate per kg (₹)", min_value=0.0, step=1.0,
                                value=rate_default, key=f"rate_{idx}")
        entries = lot.get("weight_entries") or []
        df = pd.DataFrame([
            {
                "Boxes": int(e.get("boxes") or 0),
                "Kg per box": float(e.get("kg_per_box") or 0),
            } for e in entries
        ], columns=["Boxes", "Kg per box"])
        edited = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, hide_index=True,
            column_config={
                "Boxes": st.column_config.NumberColumn(min_value=0, step=1),
                "Kg per box": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="%.3f"),
            },
            key=f"entries_{idx}"
        )
        total_boxes = int(pd.to_numeric(edited["Boxes"], errors="coerce").fillna(0).sum()) if len(edited) else 0
        total_weight = Decimal("0")
        for _, row in edited.iterrows():
            boxes = Decimal(str(row["Boxes"] or 0))
            kg = Decimal(str(row["Kg per box"] or 0))
            total_weight += boxes * kg
        amount = total_weight * Decimal(str(rate))
        if declared_boxes and total_boxes != declared_boxes:
            st.warning(f"Box-count check: weight entries add up to {total_boxes}, but the lot mark says {declared_boxes}. Verify before accepting.")
        st.metric("Total weight", f"{total_weight:,.3f} kg")
        st.metric("Lot amount", f"₹{amount:,.2f}")
        if lot.get("notes"):
            st.caption(f"AI note: {lot['notes']}")
        results.append({
            "Lot mark": lot_mark,
            "Boxes in entries": total_boxes,
            "Total weight (kg)": float(total_weight),
            "Rate (₹/kg)": float(rate),
            "Amount (₹)": float(amount),
        })

    if results:
        st.subheader("2. Summary")
        result_df = pd.DataFrame(results)
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        grand_total = sum(Decimal(str(r["Amount (₹)"])) for r in results)
        total_weight_all = sum(Decimal(str(r["Total weight (kg)"])) for r in results)
        st.success(f"Grand total: ₹{grand_total:,.2f}")
        st.write(f"Combined weight: **{total_weight_all:,.3f} kg**")
        st.download_button(
            "Download summary as CSV",
            data=result_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="challan_calculation.csv",
            mime="text/csv",
        )
        if data.get("uncertain_fields"):
            st.warning("Please double-check these fields: " + ", ".join(map(str, data["uncertain_fields"])))
        st.caption("Always verify the extracted handwriting and rate before using the amount for payment or accounting.")
        if st.button("Clear this challan"):
            for k in ["extracted", "source_name"]:
                st.session_state.pop(k, None)
            st.rerun()
