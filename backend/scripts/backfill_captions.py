"""Backfill diary-style captions for any itinerary_item with caption=null."""
import json
import os

import google.generativeai as genai
from dotenv import load_dotenv
from sqlmodel import Session, create_engine, text

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

db_url = os.environ["SUPABASE_DB_URL"]
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(db_url)

with Session(engine) as s:
    rows = s.execute(
        text("select id, title, description from itinerary_item where caption is null")
    ).fetchall()
    print(f"{len(rows)} items need captions")
    if not rows:
        raise SystemExit

    payload = [{"id": r.id, "title": r.title, "description": r.description or ""} for r in rows]
    prompt = (
        "For each activity below, write a diary-style caption that would appear over "
        "the photos in a recap video. Rules:\n"
        "- 10-15 words, ONE sentence\n"
        "- first-person plural ('we'/'us'), past tense\n"
        "- conversational, warm — like a personal travel note\n"
        "- mention specifics from the description (places, food, names)\n"
        "- no exclamation marks\n\n"
        'Return strict JSON: {"captions": [{"id": "...", "caption": "..."}, ...]}\n\n'
        f"Activities:\n{json.dumps(payload, indent=2)}"
    )
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.7, "response_mime_type": "application/json"},
    )
    data = json.loads(resp.text)
    by_id = {x["id"]: x["caption"] for x in data.get("captions", [])}
    updated = 0
    for r in rows:
        cap = by_id.get(r.id)
        if cap:
            s.execute(
                text("update itinerary_item set caption = :c where id = :i"),
                {"c": cap, "i": r.id},
            )
            print(f"  {r.title[:30]:<30} -> {cap}")
            updated += 1
    s.commit()
    print(f"\nbackfilled {updated} captions")
