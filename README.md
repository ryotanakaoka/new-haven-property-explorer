# New Haven Public Property Sales Explorer

Runnable Streamlit app using Connecticut public sales and parcel/CAMA data. The explorer supports property-type, date, and sale-price filters, a median sale price, CSV export, and a map using only official source coordinates. Records without reliable coordinates are excluded from the map and are not guessed. Assessments are displayed separately from sale prices.

## Fresh-clone run (under 10 minutes)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional; put PORTKEY_API_KEY=... in it
pytest -q
streamlit run app.py
```

## Render deployment

Create a Render Web Service using:

- Build Command: `pip install -r requirements.txt`
- Start Command: `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT`
- Required environment variable: `PORTKEY_API_KEY` (set it in Render’s environment settings only if the AI feature is needed)

Render provides `PORT` automatically; the Start Command binds Streamlit to `0.0.0.0` and uses that assigned port. Do not add `.env` or API-key values to the repository. `.env` is ignored by Git.

The app uses the official Connecticut sales dataset `5mzw-sjtu` and parcel/CAMA dataset `rny9-6ak2`. It labels data vintages, displays source URLs and record IDs, and directly verifies five displayed sales. The AI feature answers factual questions from Python-computed analyses of the currently matching records; it does not invent prices or make buy/sell recommendations. Public-record comparisons are context, not an appraisal.

`PORTKEY_API_KEY` is loaded from `.env` in this folder or its parent. Never commit `.env`; it is ignored. Without a key, the calculator remains usable and the agent reports that it is unavailable. The agent is configured for `gpt-6-luna` through Portkey and has only the calculator tool. It may explain returned values but is instructed and programmatically guarded against inventing figures. Token usage and cost use the course rates: input $0.10, cached input $0.01, cache-write $0.125, output $0.50 per 1M tokens. If unavailable, the UI says so.
