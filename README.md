# 🧾 Receipt Auditor

A vision LLM reads receipt photos into clean, validated data. The extractor is **measured against human-labelled answers**, and simple checks then flag receipts that look wrong, duplicated or unusual.

## Live demo
[Open the app](https://receipt-auditor-zpdg2exmzom6prgik79jcs.streamlit.app/): upload a receipt photo (or pick a sample) and the result appears. A few reads work with the shared demo key; for more, paste your own free [Groq API key](https://console.groq.com/keys) in the sidebar.

## 📸 Screenshot
![Receipt_Auditor App](screenshot.png)

## Result

On **50 randomly chosen receipts** from the CORD dataset (validation and test parts, receipts with a usable correct total), the extractor returned the **exact total on 50 of 50**.

| | |
|---|---|
| Receipts tested | 50 |
| Total exactly correct | 50 (100%) |
| Failed or invalid calls | 0 |

Read this honestly: 50 receipts is a small sample, so the true rate is probably somewhere above 93%, not necessarily 100%. Only the **total** was measured (not items, subtotal, store name or date), and CORD is made of fairly clean Indonesian receipts. See *Limitations*.

## How it works

```
receipt photo
  → turned into base64 text (the API only accepts text)
  → vision model (Qwen on Groq) replies in JSON
  → Pydantic checks every field and type; an invalid reply is retried (up to 3 times)
  → tables: one row per receipt, one row per item
  → checks: items add up? duplicate bill? unusual spike? monthly summary
```

## Evaluation method

1. CORD stores the correct answer for each receipt as JSON text. I read it into a table and cleaned the price text into whole numbers (`1,591,600`, `48.000`, `70000.00`, `Rp 116000` all appear).
2. The extractor runs on 50 random receipts (`random.seed(42)`, so it is repeatable).
3. The AI's total is compared with the correct total. A failed call or a missing total counts as **wrong**.
4. Results are saved after every receipt, so a run stopped by the free-tier limit continues where it stopped.

### A bug I found in my own answer key

The first run scored 90%. The one "wrong" receipt was the AI answering 70,000 where my key said 7,000,000. The raw answer was `70000.00`, with two decimal zeros. My first cleaning rule kept every digit, so cents became extra digits. The AI was right and the key was wrong. Fixing the rule corrected 50 totals in the key, and the score was re-computed against the corrected key. Lesson: when a model "fails", check the grader too.

## Checks on the extracted data (20 receipts)

| Check | What it does | Result |
|---|---|---|
| Items add up | Item prices should sum to the subtotal | 19 of 20 consistent. The one flag was an item discount the schema has no field for (the AI read it correctly) |
| Duplicate bills | Same store, date, total and item count | Found the deliberately added copy, no false alarms among the real receipts |
| Spikes | Totals above Q3 + 1.5 × IQR | Flagged 4 bigger bills (normal for this mixed sample) |
| Monthly summary | Totals grouped by month | Works, but only 1 of 20 receipts had a printed date, so it is shown on a small made-up demo table as well |

These checks **flag receipts for a human to look at**. They do not decide anything.

## Limitations

- **Only totals are measured.** Item names, quantities, store names and dates were not scored against ground truth (CORD has no store or date labels).
- **Clean, scanned, Indonesian receipts.** Crumpled phone photos, handwriting or other languages and currencies may do worse. The prompt includes rupiah number rules learned from this dataset.
- **Discounts.** The schema has no discount field, so a receipt with an item discount is falsely flagged by the items-add-up check (seen once in the sample). A `discount` field would fix it.
- **Spike rule compares all receipts in one pool.** A small bakery bill and a large restaurant bill are judged together. Real use would compare within a store or category, or over time.
- **Monthly summary needs dates**, and most receipts do not print one.
- **Small sample** (50 receipts, one run).
- **Privacy:** receipt photos are sent to Groq's API. Do not use receipts you are not comfortable sharing with an API provider.
- **Shared demo key.** The live app can use a shared key for a few reads per visitor session. It shares one daily Groq allowance, so it may be used up, and the app then asks for your own key.
- **Groq free tier** has per-minute and daily token limits. Photos are token-heavy, so a full run can hit the daily limit. The notebook records failures and can resume.
- **Model name:** the vision model on Groq may change. `MODEL` is set in one place, in `receipt_extractor.py`.

## Run it

```bash
git clone https://github.com/Shaheen3107/Receipt-Auditor.git
cd Receipt-Auditor

python -m venv venv
venv\Scripts\activate          # Windows
```

**The app:**
```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

**The notebook (answer key, accuracy, checks):**
```bash
pip install -r requirements-notebook.txt
jupyter notebook Receipt_Auditor.ipynb
```

Get a free key at [console.groq.com/keys](https://console.groq.com/keys). The notebook asks for it in a hidden prompt, so it is never saved in the file. Never put a key in code or commit it to GitHub.

Run the cells from top to bottom. `receipt_extractor.py` must sit next to the notebook.

## Files

```
├── app.py                    # the Streamlit app
├── Receipt_Auditor.ipynb     # the whole pipeline: answer key, accuracy, checks
├── receipt_extractor.py      # the form (Pydantic), the prompt, ask_receipt, to_number
├── samples/                  # a few CORD receipt photos for the app's sample menu
├── requirements.txt          # for the app
├── requirements-notebook.txt # for the notebook (adds datasets, jupyter)
├── stage3_results.csv        # the 50-receipt results (optional)
└── README.md
```

## Data

[CORD-v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) by NAVER CLOVA, 1,000 receipt images with annotations, licensed CC-BY-4.0. The dataset is downloaded when the notebook runs. The few sample photos in `samples/` come from it (CC-BY-4.0, attribution to NAVER CLOVA).

## Author

**Shaheen Akram** · [GitHub @Shaheen3107](https://github.com/Shaheen3107)
