import json, os, time
from decimal import Decimal
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Raisin Register Calculator", page_icon="🧾", layout="wide")
st.title("🧾 Raisin Challan & Register Calculator")
st.write("Upload a challan or full register photo. Review every extracted row before using the totals.")
st.info("Rules: numerator = box count; denominator = kg per box. A blank numerator means remaining boxes only when exactly one fraction has a blank numerator. HCR-55/50 means lot identity HCR-55 with 50 actual boxes.")

key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
if not key:
    st.warning("Add GEMINI_API_KEY in Streamlit Secrets to enable AI reading.")
upload = st.file_uploader("Upload challan or register photo", type=["jpg","jpeg","png","webp"])

def dec(v, default=None):
    if v is None or (isinstance(v, float) and pd.isna(v)): return default
    s = str(v).replace(",", "").replace("₹", "").strip()
    if not s or s.lower() in {"none","null","nan"}: return default
    try: return Decimal(s)
    except Exception: return default

def read_image(data, mime, api_key):
    client = genai.Client(api_key=api_key)
    prompt = r"""
Read all lot rows on this handwritten raisin register/challan photo. Return ONLY valid JSON:
{
 "date":"",
 "customer":"",
 "lots":[{
  "original_mark":"HCR-55/50",
  "lot_identity":"HCR-55",
  "declared_boxes":50,
  "box_count_source":"suffix or Boxes column or lot mark",
  "weight_entries":[{"boxes":2,"kg_per_box":12.5},{"boxes":3,"kg_per_box":14},{"boxes":null,"kg_per_box":15}],
  "rate_per_kg":250,
  "notes":""
 }],
 "uncertain_fields":[]
}
Rules:
- Read every non-empty lot row top-to-bottom; don't stop after a few rows and don't invent blank rows.
- Numerator in each weight fraction is number of boxes; denominator is kg per box. 63/15 means 63 boxes at 15kg each.
- Return every fraction in reading order. Multiple fractions can belong to one lot.
- Blank numerator means boxes:null. Do not guess it; the app will allocate the remainder only if there is exactly one blank-numerator group.
- If more than one fraction has a blank numerator, leave all such counts null and flag the row for manual review.
- Lot mark HCR-55/50 means original_mark "HCR-55/50", lot_identity "HCR-55", actual declared_boxes 50. The final slash suffix here is the actual box count, not a weight fraction.
- Prefer a clearly written separate Boxes column over a suffix if they conflict; explain the conflict in notes and uncertain_fields.
- If mark is HCR-55 with no suffix and no clearer Boxes column, 55 may be the count.
- Rates are per kg and must come from the Rate column, not weight columns.
- Use null for unreadable numeric values; do not invent.
"""
    last = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            return json.loads(resp.text)
        except Exception as e:
            last = e
            msg = str(e).lower()
            if attempt == 2 or not any(x in msg for x in ["503","429","unavailable","high demand","overloaded","resource_exhausted"]):
                raise
            time.sleep(2 ** (attempt + 1))
    raise last

def resolve(rows, declared):
    items = []
    for row in rows:
        kg = dec(row.get("Kg per box"))
        boxes = dec(row.get("Boxes"))
        if kg is None or kg <= 0: continue
        boxes = int(boxes) if boxes is not None and boxes >= 0 else None
        items.append({"Boxes": boxes, "Kg per box": kg})
    blanks = [i for i, x in enumerate(items) if x["Boxes"] is None]
    explicit = sum(x["Boxes"] for x in items if x["Boxes"] is not None)
    warnings = []
    if len(blanks) == 1 and declared > 0:
        remaining = declared - explicit
        if remaining >= 0:
            items[blanks[0]]["Boxes"] = remaining
            warnings.append(f"Assigned remaining {remaining} boxes to the single blank-numerator group.")
        else:
            warnings.append(f"Explicit counts ({explicit}) exceed declared boxes ({declared}).")
    elif len(blanks) > 1:
        warnings.append("Multiple blank numerators: enter box counts manually; remainder allocation would be ambiguous.")
    elif len(blanks) == 1:
        warnings.append("Actual box count is unknown, so the blank numerator cannot be resolved.")
    elif declared > 0 and explicit != declared:
        warnings.append(f"Fractions total {explicit} boxes, but actual box count is {declared}.")
    return items, warnings

if upload:
    st.image(upload, caption="Uploaded image", use_container_width=True)
    if key and st.button("Read all rows with AI", type="primary"):
        with st.spinner("Reading rows and weight fractions…"):
            try:
                st.session_state["regdata"] = read_image(upload.getvalue(), upload.type or "image/jpeg", key)
            except Exception as e:
                st.error(f"Could not read image: {e}")
                st.caption("For 503/429 errors, wait and retry. A straight-on, well-lit image improves extraction.")
    elif not key:
        st.info("Add the API key in Streamlit Secrets first.")

if "regdata" in st.session_state:
    data = st.session_state["regdata"]
    st.subheader("1. Review extracted details")
    st.text_input("Date", value=str(data.get("date") or ""), key="review_date")
    st.text_input("Customer / party", value=str(data.get("customer") or ""), key="review_customer")
    lots = data.get("lots") or []
    if not lots: st.warning("No lot rows detected. Try a sharper photo with the full page visible.")
    results = []
    for i, lot in enumerate(lots):
        st.markdown(f"### Row {i+1}: {lot.get('original_mark') or 'Unmarked lot'}")
        c1, c2 = st.columns([2,1])
        with c1:
            mark = st.text_input("Original lot mark", value=str(lot.get("original_mark") or lot.get("lot_mark") or ""), key=f"mark{i}")
            identity = st.text_input("Lot identity", value=str(lot.get("lot_identity") or lot.get("original_mark") or ""), key=f"id{i}")
        raw_boxes = lot.get("declared_boxes")
        try: default_boxes = max(0, int(raw_boxes)) if raw_boxes is not None else 0
        except Exception: default_boxes = 0
        with c2:
            declared = st.number_input("Actual boxes", min_value=0, step=1, value=default_boxes, key=f"declared{i}", help="For HCR-55/50, enter 50.")
        try: rate_default = float(dec(lot.get("rate_per_kg"), Decimal(0)) or 0)
        except Exception: rate_default = 0.0
        rate = st.number_input("Rate per kg (₹)", min_value=0.0, step=1.0, value=rate_default, key=f"rate{i}")
        entries = lot.get("weight_entries") or []
        initial = [{"Boxes": int(e["boxes"]) if e.get("boxes") is not None else None,
                    "Kg per box": float(e["kg_per_box"]) if e.get("kg_per_box") is not None else None} for e in entries]
        if not initial: initial = [{"Boxes": None, "Kg per box": None}]
        edited = st.data_editor(
            pd.DataFrame(initial, columns=["Boxes","Kg per box"]), num_rows="dynamic",
            use_container_width=True, hide_index=True, key=f"fractions{i}",
            column_config={
                "Boxes": st.column_config.NumberColumn("Boxes (blank = remaining)", min_value=0, step=1),
                "Kg per box": st.column_config.NumberColumn("Kg per box", min_value=0.0, step=0.1, format="%.3f")
            }
        )
        items, warnings = resolve(edited.to_dict(orient="records"), int(declared))
        box_total = sum(x["Boxes"] for x in items if x["Boxes"] is not None)
        unresolved = any(x["Boxes"] is None for x in items)
        weight = sum((Decimal(x["Boxes"]) * x["Kg per box"] for x in items if x["Boxes"] is not None), Decimal(0))
        if declared and box_total != int(declared) and not any("exceed" in w or "Fractions total" in w for w in warnings):
            warnings.append(f"Resolved groups total {box_total} boxes; actual count is {int(declared)}.")
        for w in warnings: st.warning(w)
        if lot.get("notes"): st.caption("AI note: " + str(lot["notes"]))
        amount = weight * Decimal(str(rate)) if not unresolved and rate > 0 else None
        a,b,c = st.columns(3)
        a.metric("Boxes in groups", str(box_total))
        b.metric("Total weight", f"{weight:,.3f} kg")
        c.metric("Lot amount", f"₹{amount:,.2f}" if amount is not None else "Review rate/count")
        results.append({
            "Row": i+1, "Original lot mark": mark, "Lot identity": identity,
            "Actual boxes": int(declared), "Boxes in groups": box_total,
            "Total weight (kg)": float(weight), "Rate (₹/kg)": float(rate),
            "Amount (₹)": float(amount) if amount is not None and not unresolved else None,
            "Needs review": bool(warnings or unresolved or amount is None)
        })
    if results:
        st.subheader("2. Register summary")
        result_df = pd.DataFrame(results)
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        total_weight = sum((dec(x, Decimal(0)) or Decimal(0) for x in result_df["Total weight (kg)"]), Decimal(0))
        amounts = [dec(x) for x in result_df["Amount (₹)"] if dec(x) is not None]
        grand_total = sum(amounts, Decimal(0))
        a,b,c = st.columns(3)
        a.metric("Combined weight", f"{total_weight:,.3f} kg")
        b.metric("Calculated amount", f"₹{grand_total:,.2f}")
        c.metric("Rows needing review", str(int(result_df["Needs review"].sum())))
        st.warning("Verify all rows marked for review before using the total for payment or accounting.")
        st.download_button("Download summary as CSV", result_df.to_csv(index=False).encode("utf-8-sig"),
                           "raisin_register_calculation.csv", "text/csv")
    if data.get("uncertain_fields"):
        st.subheader("AI uncertainties")
        for item in data["uncertain_fields"]: st.write("- " + str(item))
    if st.button("Clear this register"):
        st.session_state.pop("regdata", None)
        st.rerun()

st.caption("Always verify handwritten lot marks, fractions, box counts, and rates. AI extraction can make mistakes.")
