# LawMate ⚖️📄

LawMate is an AI-powered legal document analyzer that verifies, summarizes, and extracts key clauses from contracts or agreements. It uses a hybrid approach of rule-based pattern matching and transformer-based NLP models to classify legal documents and identify critical legal content. The system is built with Streamlit and maintains a searchable history of all analyses using a local SQLite database.

---

## Table of Contents
- [Setup Instructions](#setup-instructions)
- [System Architecture](#system-architecture)
- [Hybrid Legal Document Verification](#hybrid-legal-document-verification)
- [Clause Extraction Methodology](#clause-extraction-methodology)
- [Summary Generation](#summary-generation)
- [Analysis History & Database](#analysis-history--database)
- [Limitations and Future Improvements](#limitations-and-future-improvements)
- [License](#license)

---

## 📸 Preview

🔍 Clause Detection  
<p align="center"><img src="Shot1.png" width="700" alt="Detected Clauses Preview"/></p>

📄 Summary Output  
<p align="center"><img src="Shot2.png" width="700" alt="Document Summary Preview"/></p>

📚 History View  
<p align="center"><img src="Shot3.png" width="700" alt="Analysis History UI"/></p>

---

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Git
- pip

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/lawmate.git
   cd lawmate
```
# Setup Instructions

## Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

## Install the required packages:

```bash
pip install -r requirements.txt
```

## Download SpaCy language model:

```bash
python -m spacy download en_core_web_sm
```

## Run the application:

```bash
streamlit run main.py
```

# System Architecture

```plaintext
         ┌────────────────────┐
         │  User Uploads PDF │
         └────────┬───────────┘
                  │
                  ▼
         ┌────────────────────┐
         │  Streamlit Frontend│
         └────────┬───────────┘
                  │
                  ▼
      ┌────────────────────────────┐
      │  Document Preprocessing    │
      └────────┬───────────────────┘
               │
               ▼
 ┌────────────────────────────┐
 │ Hybrid Verification Engine │  ← Uses Legal-BERT + rules
 └────────┬───────────────────┘
          │
          ▼
 ┌────────────────────────────┐
 │ Clause Extraction Module   │  ← Regex-based pattern matcher
 └────────┬───────────────────┘
          │
          ▼
 ┌────────────────────────────┐
 │  Summary Generator         │  ← BART summarizer
 └────────┬───────────────────┘
          │
          ▼
 ┌────────────────────────────┐
 │ SQLite Analysis DB         │ ← Stores hash, summary, clauses
 └────────┬───────────────────┘
          │
          ▼
 ┌────────────────────────────┐
 │ Streamlit Output UI        │ ← Renders full results
 └────────────────────────────┘
```
# Document Verification

```markdown
# Hybrid Legal Document Verification

LawMate uses a three-stage verification process:

## 1. Rule-Based Structure Detection
- Scans for headers like *Section 1*, *Terms and Conditions*, etc.
- Checks for key legal keywords (e.g., "agreement", "party", "indemnify")

## 2. Legal-BERT Classification
- **Model:** nlpaueb/legal-bert-base-uncased
- Classifies whether a document is legal with a confidence score

## 3. Hybrid Confidence Boosting
- Applies fallback rules if model confidence is between 30–70%
- Long documents get a slight confidence boost
```
---

# Clause Extraction Methodology

LawMate detects over 30 clause types using robust regex patterns, grouped into:
```markdown

| Category             | Examples                                   |
|----------------------|--------------------------------------------|
| Obligations        | shall, must, required to                  |
| Rights & Permissions | entitled to, may, discretion             |
| Termination        | terminate, notice period, renew           |
| Liabilities        | indemnify, liability, hold harmless       |
| Confidentiality    | non-disclosure, confidential              |
| Legal Framework    | jurisdiction, governing law, arbitration  |

Each clause is extracted with its label and displayed in a structured block.
```
---

# Summary Generation

- **Model:** facebook/bart-large-cnn (via HuggingFace Transformers)
- **Input:** First 3000 characters of text (for relevance)
- **Output:** Approximately 200-word summary highlighting the document’s core intent

Displayed with stylized formatting in the UI.

---

# Analysis History & Database

All verified documents are hashed and saved in an SQLite database with:

- Document hash
- Legal status and confidence
- Clause types and count
- Summary and timestamp

### Schema

```sql
CREATE TABLE analyses (
  id INTEGER PRIMARY KEY,
  content_hash TEXT UNIQUE,
  is_legal INTEGER,
  confidence REAL,
  summary TEXT,
  num_clauses INTEGER,
  clauses_json TEXT,
  pattern_version TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

A sidebar lets users view and inspect recent document analyses.

---

# Limitations and Future Improvements

## Current Limitations
- Not OCR-enabled — scanned documents won't work
- Regex-based clause extraction may miss uncommon wording
- Summary generation may occasionally omit context
- Model decisions are not legally binding (AI assistance only)

## Planned Improvements
- 🧾 OCR Integration (Tesseract) for scanned PDFs
- 🧠 Clause Similarity Matching to detect paraphrased terms
- 🌐 Multilingual Support for global contract analysis
- 🎙️ TTS Integration to convert summaries to audio
- 🖼️ Improved UI with search, filter, and download options
- ☁️ Deploy to Streamlit Cloud or AWS

---

# License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---
