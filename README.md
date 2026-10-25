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

The app uses the official Connecticut sales dataset `5mzw-sjtu` and parcel/CAMA dataset `rny9-6ak2`. Live records and the source audit are cached for one hour so ordinary filter and question interactions do not re-download the full datasets. It labels data vintages, displays source URLs and record IDs, and directly verifies five displayed sales when the live sources are reachable. If the public API is unavailable, it loads `data/sample_new_haven_comps.json`: 40 real public-source records (10 per supported property type) captured on 2026-10-25. The UI labels this as a small, historical offline sample, not a complete or current dataset, and skips the live audit. No sample sale records are synthetic.

The AI feature answers supported factual questions from Python-computed analyses of the currently matching records; it does not invent prices or make buy/sell recommendations. The single PydanticAI agent uses only a read-only `public_records` tool that returns the selected Python evidence; it has no arbitrary web or database access. Unsupported questions and common instruction-override attempts are blocked before the model call. Public-record comparisons are context, not an appraisal.

AI use is bounded to five attempts per Streamlit browser session. Each agent run allows at most two model requests, one tool call, 4,000 input tokens, and 500 output tokens. Attempts are counted before the network request, including failed calls. The session counter is not an account-wide billing cap: a user can start another session, so a production deployment would still need provider-side spending controls and user-level rate limiting.

`PORTKEY_API_KEY` is loaded from `.env` in this folder or its parent. Never commit `.env`; it is ignored. Without a key, filtering, Python calculations, map, table, CSV export, and the offline sample remain usable; the agent reports that it is unavailable. The agent uses `gpt-6-luna` through Portkey. Token usage and cost use the course rates: input $0.10, cached input $0.01, cache-write $0.125, output $0.50 per 1M tokens. If unavailable, the UI says so.
