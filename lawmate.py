import os
os.environ["STREAMLIT_SERVER_ENABLE_FILE_WATCHER"] = "false"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import streamlit as st
st.set_page_config(
    page_title="LawMate",
    layout="centered",
    initial_sidebar_state="expanded"
)

import PyPDF2
from transformers import pipeline
import spacy
import re
import hashlib
from datetime import datetime
import sqlite3
import json

# --- Database Setup with Clauses Storage ---
def init_db():
    conn = sqlite3.connect('lawmate.db')
    c = conn.cursor()
    
    # Check if table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analyses'")
    table_exists = c.fetchone()
    
    if table_exists:
        # Check if clauses_json column exists
        c.execute("PRAGMA table_info(analyses)")
        columns = [col[1] for col in c.fetchall()]
        if 'clauses_json' not in columns:
            c.execute("ALTER TABLE analyses ADD COLUMN clauses_json TEXT")
        if 'pattern_version' not in columns:
            c.execute("ALTER TABLE analyses ADD COLUMN pattern_version TEXT DEFAULT '1.0'")
    else:
        c.execute('''CREATE TABLE analyses
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      content_hash TEXT UNIQUE,
                      is_legal INTEGER,
                      confidence REAL,
                      summary TEXT,
                      num_clauses INTEGER,
                      clauses_json TEXT,
                      pattern_version TEXT DEFAULT '1.0',
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def save_analysis(content_hash, is_legal, confidence, summary, clauses):
    conn = sqlite3.connect('lawmate.db')
    c = conn.cursor()
    try:
        clauses_json = json.dumps(clauses)
        c.execute('''INSERT OR REPLACE INTO analyses 
                    (content_hash, is_legal, confidence, summary, num_clauses, clauses_json, pattern_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (content_hash, int(is_legal), confidence, summary, len(clauses), clauses_json, '2.0'))
        conn.commit()
    except sqlite3.Error as e:
        st.warning(f"Database warning: {str(e)}")
    finally:
        conn.close()

def get_recent_analyses(limit=5):
    conn = sqlite3.connect('lawmate.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,))
    results = c.fetchall()
    conn.close()
    
    analyses = []
    for row in results:
        analysis = dict(row)
        analysis['clauses'] = json.loads(analysis['clauses_json']) if analysis['clauses_json'] else []
        analyses.append(analysis)
    return analyses

init_db()

# --- Legal Patterns ---
LEGAL_PATTERNS = {
    # Obligations and Requirements
    "OBLIGATION": r"(shall\s.*?|must\s.*?|required to\s.*?|obligated to\s.*?)(?=[.;])",
    "CONDITION": r"(if\s.*?then.*?|in the event\s.*?)(?=[.;])",
    
    # Rights and Permissions
    "RIGHT": r"(entitled to\s.*?|may\s.*?|right to\s.*?|permission to\s.*?)(?=[.;])",
    "DISCRETION": r"(at the sole discretion of\s.*?)(?=[.;])",
    
    # Definitions
    "DEFINITION": r"\"(.*?)\"\s+(?:means|shall mean)\s+(.*?)(?=[.;])",
    "INTERPRETATION": r"(for the purposes? of this\s.*?)(?=[.;])",
    
    # Liabilities and Indemnities
    "LIABILITY": r"(liability\s.*?|responsible for\s.*?)(?=[.;])",
    "INDEMNITY": r"(indemnify\s.*?|hold harmless\s.*?)(?=[.;])",
    "LIMITATION": r"(not liable for\s.*?|exclusion of liability\s.*?)(?=[.;])",
    
    # Term and Termination
    "TERM": r"(term\s.*?of this agreement.*?)(?=[.;])",
    "TERMINATION": r"(terminat(?:ion|e)\s.*?(?:upon|with|after).*?)(?=[.;])",
    "RENEWAL": r"(renew\s.*?automatically.*?)(?=[.;])",
    
    # Confidentiality
    "CONFIDENTIALITY": r"(confidential\s.*?|non-disclosure\s.*?)(?=[.;])",
    "NON-CIRCUMVENTION": r"(not circumvent\s.*?)(?=[.;])",
    
    # Representations and Warranties
    "REPRESENTATION": r"(represent(?:s|ations?)\s.*?(?:that|as).*?)(?=[.;])",
    "WARRANTY": r"(warrant(?:y|ies)\s.*?)(?=[.;])",
    
    # Governing Law and Disputes
    "GOVERNING_LAW": r"(govern(?:ed|ing)\s.*?law.*?)(?=[.;])",
    "JURISDICTION": r"(jurisdiction\s.*?courts? of.*?)(?=[.;])",
    "ARBITRATION": r"(arbitration\s.*?under.*?)(?=[.;])",
    
    # Payment Terms
    "PAYMENT": r"(pay(?:ment|able)\s.*?\$?\d+.*?)(?=[.;])",
    "INTEREST": r"(interest\s.*?\d+%.*?)(?=[.;])",
    "TAX": r"(tax\s.*?responsib.*?)(?=[.;])",
    
    # Dates and Effective Periods
    "EFFECTIVE_DATE": r"(effective\s.*?date.*?)(?=[.;])",
    "NOTICE_PERIOD": r"(notice\s.*?\d+\sdays.*?)(?=[.;])",
    
    # Intellectual Property
    "IP_OWNERSHIP": r"(ownership of\s.*?intellectual property.*?)(?=[.;])",
    "LICENSE": r"(license\s.*?grant.*?)(?=[.;])",
    
    # Miscellaneous
    "FORCE_MAJEURE": r"(force\s.*?majeure.*?)(?=[.;])",
    "AMENDMENT": r"(amend(?:ment|ed)\s.*?writing.*?)(?=[.;])",
    "ENTIRE_AGREEMENT": r"(entire agreement\s.*?)(?=[.;])"
}

@st.cache_resource
def load_models():
    try:
        nlp = spacy.load("en_core_web_sm")
        
        legal_verifier = pipeline(
            "text-classification",
            model="nlpaueb/legal-bert-base-uncased",
            device=-1,
            top_k=None
        )
        
        summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=-1
        )
        
        return nlp, legal_verifier, summarizer
    except Exception as e:
        st.error(f"Model loading failed: {str(e)}")
        st.stop()

nlp, legal_verifier, summarizer = load_models()

def has_legal_structure(text):
    """Rule-based checks for legal document characteristics"""

    section_headers = [
        r"\b(article|section|clause)\s+\d+",
        r"\b(terms and conditions|governing law|jurisdiction|confidentiality)\b",
        r"\b(now therefore|in consideration of|hereinafter)\b"
    ]
    
    # Count matches of legal patterns and headers
    pattern_matches = sum(
        1 for pattern in LEGAL_PATTERNS.values()
        if re.search(pattern, text, re.IGNORECASE)
    )
    
    header_matches = sum(
        1 for pattern in section_headers
        if re.search(pattern, text, re.IGNORECASE)
    )
    
    # Document contains at least 3 legal patterns/headers
    return (pattern_matches + header_matches) >= 3

def contains_legal_keywords(text):
    """Check for presence of characteristic legal terms"""
    legal_keywords = [
        'party', 'agreement', 'shall', 'warrant', 'indemn', 
        'liability', 'govern', 'jurisdiction', 'effective date',
        'term', 'terminat', 'obligat', 'right', 'represent',
        'notwithstand', 'hereby', 'whereas', 'force majeure'
    ]
    return sum(
        1 for keyword in legal_keywords
        if re.search(rf'\b{keyword}', text, re.IGNORECASE)
    )

def preprocess_legal_text(text):
    """Clean text for better model analysis"""
    # Remove common non-legal elements
    text = re.sub(r'(?i)(page \d+|confidential|draft|©|copyright|\b\w{1,3}\d+\w{1,3}\b)', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text[:3000]  # Focus on first 3000 chars (where key clauses usually appear)

def has_legal_structure(text):
    """Rule-based checks for legal document characteristics"""
    # Check for legal section headers
    section_headers = [
        r"\b(article|section|clause)\s+\d+",
        r"\b(terms and conditions|governing law|jurisdiction|confidentiality)\b",
        r"\b(now therefore|in consideration of|hereinafter)\b"
    ]
    
    # Count matches of legal patterns and headers
    pattern_matches = sum(
        1 for pattern in LEGAL_PATTERNS.values()
        if re.search(pattern, text, re.IGNORECASE)
    )
    
    header_matches = sum(
        1 for pattern in section_headers
        if re.search(pattern, text, re.IGNORECASE)
    )
    
    # Document contains at least 3 legal patterns/headers
    return (pattern_matches + header_matches) >= 3

def contains_legal_keywords(text):
    """Check for presence of characteristic legal terms"""
    legal_keywords = [
        'party', 'agreement', 'shall', 'warrant', 'indemn', 
        'liability', 'govern', 'jurisdiction', 'effective date',
        'term', 'terminat', 'obligat', 'right', 'represent',
        'notwithstand', 'hereby', 'whereas', 'force majeure'
    ]
    return sum(
        1 for keyword in legal_keywords
        if re.search(rf'\b{keyword}', text, re.IGNORECASE)
    )

def preprocess_legal_text(text):
    """Clean text for better model analysis"""
    # Remove common non-legal elements
    text = re.sub(r'(?i)(page \d+|confidential|draft|©|copyright|\b\w{1,3}\d+\w{1,3}\b)', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text[:3000]  # Focus on first 3000 chars (where key clauses usually appear)

def hybrid_verify(text):
    """
    Enhanced verification combining:
    1. Rule-based checks (fast)
    2. Legal-BERT model (accurate)
    3. Fallback heuristics
    """
    try:
        # Preprocess text
        clean_text = preprocess_legal_text(text)
        
        # --- Phase 1: Rule-Based Verification ---
        if has_legal_structure(clean_text):
            keyword_score = min(1.0, 0.6 + (0.05 * contains_legal_keywords(clean_text)))
            return True, keyword_score
        
        # --- Phase 2: Model Verification ---
        model_result = legal_verifier(clean_text[:2000])[0][0]
        model_legal = model_result['label'] == 'LABEL_1'
        model_confidence = model_result['score']
        
        # --- Phase 3: Hybrid Decision ---
        # If model is unsure (0.3 < confidence < 0.7), use rules to break ties
        if 0.3 < model_confidence < 0.7:
            if contains_legal_keywords(clean_text) >= 5:
                return True, min(1.0, model_confidence + 0.2)
        
        # Final decision with adjusted confidence
        final_confidence = model_confidence
        if len(text) > 1500:  # Longer docs get confidence boost
            final_confidence = min(1.0, model_confidence + 0.1)
            
        return model_legal, final_confidence
        
    except Exception as e:
        st.warning(f"Verification warning: {str(e)}")
        # Default to legal with medium confidence if errors occur
        return True, 0.5

def show_verification_details(text, is_legal, confidence):
    """Display detailed verification report"""
    with st.expander("Verification Analysis Details"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Final Decision", "LEGAL" if is_legal else "NON-LEGAL")
            st.metric("Confidence", f"{confidence:.0%}")
            
        with col2:
            clean_text = preprocess_legal_text(text)
            st.metric("Legal Keywords Found", contains_legal_keywords(clean_text))
            st.metric("Legal Patterns Found", sum(
                1 for p in LEGAL_PATTERNS.values() 
                if re.search(p, clean_text, re.IGNORECASE)
            ))
        
        # Decision factors
        st.subheader("Key Decision Factors")
        if is_legal:
            if confidence > 0.7:
                st.success("Strong legal structure detected")
            else:
                st.warning("Marginal legal content - review recommended")
        else:
            st.error("Lacks strong legal indicators")
        
        # Sample detected clauses
        sample_clauses = []
        for pattern_name, pattern in list(LEGAL_PATTERNS.items())[:5]:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                sample_clauses.append(f"{pattern_name}: {match.group()[:100]}...")
        
        if sample_clauses:
            st.write("Sample detected clauses:")
            for clause in sample_clauses[:3]:
                st.code(clause, language='text')

# --- Text Extraction ---
def extract_content(file):
    try:
        if file.name.endswith('.pdf'):
            reader = PyPDF2.PdfReader(file)
            text = " ".join([
                page.extract_text() or "" 
                for page in reader.pages
                if page.extract_text()
            ])
            return text if len(text.strip()) > 50 else ""
        return file.read().decode("utf-8", errors="replace").strip()
    except Exception as e:
        st.error(f"Extraction error: {str(e)}")
        return ""

# --- Enhanced Analysis Function ---
def analyze_text(text):
    try:
        if len(text) < 100:
            return "Document too short for analysis", []
        
        summary = summarizer(
            text[:3000] if len(text) > 3000 else text,
            max_length=200,  
            min_length=50,   
            do_sample=False
        )[0]['summary_text']
        
        clauses = []
        for label, pattern in LEGAL_PATTERNS.items():
            try:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                clauses.extend((m.group().strip(), label) for m in matches)
            except Exception as e:
                st.warning(f"Pattern '{label}' failed: {str(e)}")
                continue
        
        return summary, clauses[:30]  # Increased limit
    except Exception as e:
        return f"Analysis completed with limitations: {str(e)}", []

# --- Main App ---
st.title("LawMate")

input_method = st.radio(
    "Input Method:",
    ["Upload Document", "Paste Text"],
    horizontal=True
)

text = ""
content_hash = ""
if input_method == "Upload Document":
    uploaded_file = st.file_uploader(
        "Upload legal document (PDF/TXT)", 
        type=["pdf", "txt"],
        help="Files up to 10MB supported"
    )
    if uploaded_file:
        with st.spinner("Extracting content..."):
            text = extract_content(uploaded_file)
            if text:
                content_hash = hashlib.sha256(text.encode()).hexdigest()
else:
    text_input = st.text_area(
        "Paste legal text here:",
        height=200,
        placeholder="Enter contract text or legal document content..."
    )
    if st.button("Analyze Text"):
        if text_input.strip():
            text = text_input
            content_hash = hashlib.sha256(text.encode()).hexdigest()
        else:
            st.warning("Please enter text to analyze")

if text:
    # Verification Stage - REPLACE THIS SECTION
    with st.spinner("Verifying document..."):
        legal, confidence = hybrid_verify(text)
        show_verification_details(text, legal, confidence)
        
        if not legal:
            st.error(f"Document not classified as legal (Confidence: {confidence:.0%})")
            if confidence > 0.3:
                st.info("This might be a legal document with unusual formatting. Consider:")
                st.markdown("- Removing headers/footers\n- Checking for OCR errors\n- Including more contractual language")
            st.stop()
        
        st.success(f"Verified as legal document (Confidence: {confidence:.0%})")

    # Legal analysis
    with st.spinner("Performing legal analysis..."):
        summary, clauses = analyze_text(text)
        save_analysis(content_hash, legal, confidence, summary, clauses)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Document Summary")
            st.markdown(f"""<div style="
                background:#000;
                padding:15px;
                border-radius:8px;
                border:4px solid #fff;
                margin-bottom:20px
            ">{summary}</div>""", unsafe_allow_html=True)
            
            with st.expander("Document Details"):
                st.metric("Text Length", f"{len(text):,} characters")
                st.code(f"Content Hash: {content_hash[:16]}...")

        with col2:
            st.subheader("Detected Clauses")
            if clauses:
                for clause, label in clauses:
                    st.markdown(f"""
                    <div style="
                        margin-bottom:10px;
                        padding:10px;
                        background:#000;
                        border-radius:5px;
                        border:3px solid #fff;
                        word-break: break-word
                    ">
                        <strong>{label.replace('_', ' ').title()}:</strong>
                        <div style="color:#2c3e50"><code>{clause}</code></div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("""
                No standard clauses detected. Possible reasons:
                - Document uses non-standard phrasing
                - Contains mostly non-contractual text
                - Uses uncommon clause structures
                """)

    st.subheader("Analysis History")
    recent_analyses = get_recent_analyses()
    if recent_analyses:
        for analysis in recent_analyses:
            with st.expander(f"Analysis {analysis['id']} - {analysis['created_at']}"):
                cols = st.columns(3)
                cols[0].metric("Confidence", f"{analysis['confidence']:.0%}")
                cols[1].metric("Clauses Found", analysis['num_clauses'])
                cols[2].metric("Legal", "Yes" if analysis['is_legal'] else "No")
                
                st.write(f"**Summary:** {analysis['summary']}")
                
                if analysis['clauses']:
                    st.write("**Detected Clauses:**")
                    for clause, label in analysis['clauses']:
                        st.markdown(f"""
                        <div style="
                            margin-bottom:8px;
                            padding:8px;
                            background:#f0f2f6;
                            border-radius:5px;
                            border-left:3px solid #4e79a7;
                            word-break: break-word;
                            color:red
                        ">
                            <strong>{label.replace('_', ' ').title()}:</strong>
                            <div style="color:red"><code>{clause}</code></div>
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("No previous analyses found")

