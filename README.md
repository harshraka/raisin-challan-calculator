# Raisin Challan Calculator (free starter)

A mobile-friendly Streamlit app that reads a challan photo with Gemini and calculates:
- each weight entry as boxes × kg per box
- total weight per lot
- amount = total weight × rate per kg
- box-count mismatch warnings
- CSV export

## Important
AI handwriting recognition can make mistakes. Review and correct every extracted value before using the total for payment or accounting. The app does not submit or save records to a cloud database.

## Run locally
1. Install Python 3.10+.
2. In this folder run: `pip install -r requirements.txt`
3. Get a Gemini API key from Google AI Studio: https://aistudio.google.com/apikey
4. Set the environment variable:
   - macOS/Linux: `export GEMINI_API_KEY="your-key"`
   - Windows PowerShell: `$env:GEMINI_API_KEY="your-key"`
5. Run: `streamlit run app.py`

## Deploy free on Streamlit Community Cloud
1. Create a GitHub account and a new private or public repository.
2. Upload `app.py` and `requirements.txt`.
3. Deploy the repository on Streamlit Community Cloud: https://share.streamlit.io/
4. In the app's Settings / Secrets, add:
   `GEMINI_API_KEY = "your-key"`
5. Restart/redeploy the app.

Free-tier availability, quotas, and provider terms can change. Keep your API key private and do not commit it to GitHub.

## How fractions work
`63/15` = 63 boxes × 15 kg each.
`1/13.3` = 1 box × 13.3 kg.
Total weight = sum of (boxes × kg per box).
Amount = total weight × rate per kg.

## First test case
ALC-64, entries 63 × 15 kg and 1 × 13.3 kg, rate ₹250/kg:
Total weight = 958.3 kg; amount = ₹239,575.
