# -*- coding: utf-8 -*-
"""
Test Textract with a real PNG receipt created via Pillow,
then fall back to a plain-text document test if Pillow unavailable.
"""
import sys, io, os, boto3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()

creds = dict(
    region_name           = os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id     = os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token     = os.getenv('AWS_SESSION_TOKEN'),
)
BUCKET = os.getenv('AWS_STORAGE_BUCKET_NAME', 'splitsmart-receipt')

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN  = "\033[96m"; RESET = "\033[0m"; BOLD = "\033[1m"

def ok(l, m=""): print(f"  {GREEN}OK   {l}{RESET}  {m}")
def fail(l, m):  print(f"  {RED}FAIL {l}{RESET}  -> {m}")
def info(l, m):  print(f"  {YELLOW}INFO {l}{RESET}  -> {m}")

s3 = boto3.client('s3', **creds)
tx = boto3.client('textract', **creds)

print(f"\n{BOLD}{CYAN}==== Textract Real-Image Test ===={RESET}\n")

# ── Build a proper receipt image using Pillow ────────────────────────────────
img_bytes = None
IMG_KEY   = "diagnostics/real_receipt.png"

print(f"{BOLD}[1] Generate receipt image with Pillow{RESET}")
try:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    lines = [
        "SPLITSMART CAFE",
        "123 Main Street, Dublin",
        "------------------------------",
        "Coffee           EUR 3.50",
        "Sandwich         EUR 6.00",
        "------------------------------",
        "TOTAL            EUR 9.50",
        "TAX              EUR 0.85",
        "DATE: 2026-04-17",
    ]
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=(0, 0, 0))
        y += 28
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()
    ok("pillow_image", f"Generated {len(img_bytes)} bytes PNG receipt")
except ImportError:
    info("pillow", "Not installed — using pre-built PDF bytes instead")
except Exception as e:
    fail("pillow_image", e)

# ── Fallback: use a minimal valid PDF with text ──────────────────────────────
if img_bytes is None:
    print(f"\n{BOLD}[1b] Fallback — minimal PDF with text{RESET}")
    PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 300 144]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 100>>
stream
BT /F1 12 Tf 10 120 Td (SPLITSMART CAFE) Tj 0 -20 Td (TOTAL EUR 9.50) Tj 0 -20 Td (DATE 2026-04-17) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000274 00000 n 
0000000426 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
509
%%EOF"""
    img_bytes = PDF
    IMG_KEY   = "diagnostics/real_receipt.pdf"
    ok("pdf_fallback", f"Built {len(img_bytes)}-byte PDF")

# ── Upload to S3 ─────────────────────────────────────────────────────────────
print(f"\n{BOLD}[2] Upload to S3{RESET}")
ctype = 'image/png' if IMG_KEY.endswith('.png') else 'application/pdf'
try:
    s3.put_object(Bucket=BUCKET, Key=IMG_KEY, Body=img_bytes, ContentType=ctype)
    ok("s3_upload", f"s3://{BUCKET}/{IMG_KEY}")
    uploaded = True
except Exception as e:
    fail("s3_upload", e)
    uploaded = False

# ── Textract DetectDocumentText (inline) ─────────────────────────────────────
print(f"\n{BOLD}[3] Textract DetectDocumentText (inline bytes){RESET}")
try:
    resp   = tx.detect_document_text(Document={'Bytes': img_bytes})
    blocks = resp.get('Blocks', [])
    words  = [b['Text'] for b in blocks if b['BlockType'] == 'WORD']
    ok("detect_document_text", f"{len(blocks)} blocks, words detected: {words[:10]}")
except Exception as e:
    fail("detect_document_text", e)

# ── Textract AnalyzeExpense (S3) ──────────────────────────────────────────────
print(f"\n{BOLD}[4] Textract AnalyzeExpense (S3 object){RESET}")
if uploaded:
    try:
        resp = tx.analyze_expense(
            Document={'S3Object': {'Bucket': BUCKET, 'Name': IMG_KEY}}
        )
        docs   = resp.get('ExpenseDocuments', [])
        fields = []
        for doc in docs:
            for f in doc.get('SummaryFields', []):
                t = f.get('Type', {}).get('Text', '')
                v = f.get('ValueDetection', {}).get('Text', '')
                fields.append(f"{t}={v}")
        ok("analyze_expense", f"{len(docs)} doc(s), fields: {fields}")
    except Exception as e:
        fail("analyze_expense", e)

    # cleanup
    try:
        s3.delete_object(Bucket=BUCKET, Key=IMG_KEY)
        info("cleanup", f"Removed s3://{BUCKET}/{IMG_KEY}")
    except:
        pass
else:
    info("analyze_expense", "Skipped (S3 upload failed)")

print(f"\n{BOLD}{CYAN}==== Done ===={RESET}\n")
