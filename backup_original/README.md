# CRE Cash-Flow Stress Tester

Runnable Streamlit MVP for an investment analyst. The application uses clearly labeled synthetic inputs and a deterministic Python calculator for annual rental income, NOI, interest expense, and cash flow after interest. Principal payments and taxes are explicitly excluded.

## Fresh-clone run (under 10 minutes)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional; put PORTKEY_API_KEY=... in it
pytest -q
streamlit run app.py
```

`PORTKEY_API_KEY` is loaded from `.env` in this folder or its parent. Never commit `.env`; it is ignored. Without a key, the calculator remains usable and the agent reports that it is unavailable. The agent is configured for `gpt-6-luna` through Portkey and has only the calculator tool. It may explain returned values but is instructed and programmatically guarded against inventing figures. Token usage and cost use the course rates: input $0.10, cached input $0.01, cache-write $0.125, output $0.50 per 1M tokens. If unavailable, the UI says so.
