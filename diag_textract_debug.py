# -*- coding: utf-8 -*-
"""
Deep-debug Textract parser:
- Uploads a realistic receipt PNG to S3
- Calls analyze_expense and dumps ALL raw fields
- Traces every step of _parse_response and _parse_amount
- Identifies which field types are being missed
"""
import sys, io, os, re, boto3
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

s3 = boto3.client('s3', **creds)
tx = boto3.client('textract', **creds)

# ── Build a realistic receipt PNG ──────────────────────────────────────────
from PIL import Image, ImageDraw, ImageFont

img  = Image.new('RGB', (500, 400), color=(255, 255, 255))
draw = ImageDraw.Draw(img)
lines = [
    ("TESCO IRELAND",          20, True ),
    ("123 O'Connell Street",   20, False),
    ("Dublin, D01 T6K2",       20, False),
    ("",                       10, False),
    ("Milk 2L            1.89",20, False),
    ("Bread              2.50",20, False),
    ("Coffee             4.99",20, False),
    ("",                       10, False),
    ("Subtotal           9.38",20, False),
    ("VAT (13.5%)        1.27",20, False),
    ("TOTAL             10.65",20, True ),
    ("",                       10, False),
    ("Date: 17/04/2026",       20, False),
]
y = 20
for (text, gap, bold) in lines:
    if text:
        draw.text((30, y), text, fill=(0, 0, 0))
    y += gap + (14 if text else 0)

buf = io.BytesIO()
img.save(buf, format='PNG')
img_bytes = buf.getvalue()
IMG_KEY   = "diagnostics/debug_receipt.png"

print("=" * 60)
print("TEXTRACT DEEP DEBUG")
print("=" * 60)

# Upload
s3.put_object(Bucket=BUCKET, Key=IMG_KEY, Body=img_bytes, ContentType='image/png')
print(f"[S3] Uploaded -> s3://{BUCKET}/{IMG_KEY}\n")

# Call Textract
resp = tx.analyze_expense(Document={'S3Object': {'Bucket': BUCKET, 'Name': IMG_KEY}})

# ── Dump ALL raw SummaryFields ─────────────────────────────────────────────
print("=" * 60)
print("RAW TEXTRACT SummaryFields")
print("=" * 60)
all_field_types = set()
for doc_i, doc in enumerate(resp.get('ExpenseDocuments', [])):
    print(f"\n[Document {doc_i}]")
    for field in doc.get('SummaryFields', []):
        ftype  = field.get('Type', {}).get('Text', '')
        fvalue = field.get('ValueDetection', {}).get('Text', '')
        fconf  = field.get('Type', {}).get('Confidence', 0)
        vconf  = field.get('ValueDetection', {}).get('Confidence', 0)
        all_field_types.add(ftype)
        print(f"  Type={ftype:<30}  Value={fvalue:<20}  TypeConf={fconf:.0f}%  ValConf={vconf:.0f}%")

print(f"\nAll field types found: {sorted(all_field_types)}")

# ── Trace _parse_response ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("PARSE TRACE (_parse_response logic)")
print("=" * 60)

MAPPED_TYPES = {'VENDOR_NAME', 'NAME', 'TOTAL', 'TAX', 'INVOICE_RECEIPT_DATE'}
MISSED_TYPES = all_field_types - MAPPED_TYPES

result = {'merchant_name': '', 'total_amount': None, 'tax_amount': None, 'transaction_date': ''}

for doc in resp.get('ExpenseDocuments', []):
    for field in doc.get('SummaryFields', []):
        ftype  = field.get('Type', {}).get('Text', '')
        fvalue = field.get('ValueDetection', {}).get('Text', '')

        def parse_amount(value):
            try:
                cleaned = re.sub(r'[^\d.]', '', value.replace(',', ''))
                return float(cleaned) if cleaned else None
            except Exception:
                return None

        if ftype in ('VENDOR_NAME', 'NAME'):
            result['merchant_name'] = fvalue
            print(f"  [MAPPED ] {ftype} -> merchant_name = '{fvalue}'")
        elif ftype == 'TOTAL':
            parsed = parse_amount(fvalue)
            result['total_amount'] = parsed
            print(f"  [MAPPED ] {ftype} -> total_amount = {parsed}  (raw='{fvalue}')")
        elif ftype == 'TAX':
            parsed = parse_amount(fvalue)
            result['tax_amount'] = parsed
            print(f"  [MAPPED ] {ftype} -> tax_amount = {parsed}  (raw='{fvalue}')")
        elif ftype == 'INVOICE_RECEIPT_DATE':
            result['transaction_date'] = fvalue
            print(f"  [MAPPED ] {ftype} -> transaction_date = '{fvalue}'")
        else:
            print(f"  [SKIPPED] {ftype} = '{fvalue}'")

print(f"\nFinal parsed result: {result}")

# ── Highlight missed amounts ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("MISSED AMOUNT FIELDS (could contain the total)")
print("=" * 60)
amount_like = {'SUBTOTAL', 'AMOUNT_DUE', 'AMOUNT_PAID', 'GRAND_TOTAL',
               'DUE_DATE', 'OTHER', 'PRICE', 'UNIT_PRICE'}
for ftype in sorted(MISSED_TYPES):
    if any(k in ftype for k in ['TOTAL', 'AMOUNT', 'PRICE', 'DUE', 'PAID', 'SUBTOTAL']):
        print(f"  !! Missed potential amount field: {ftype}")

# ── _parse_amount edge cases ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("_parse_amount EDGE-CASE TESTS")
print("=" * 60)
test_values = [
    "10.65", "$10.65", "EUR 10.65", "10,65", "EUR10.65",
    "1,234.56", "$1,234.56", "10.65 EUR", "", "N/A", "TOTAL",
    "10.6.5",   # multiple dots — this causes float() to throw
]
for v in test_values:
    try:
        cleaned = re.sub(r'[^\d.]', '', v.replace(',', ''))
        result_v = float(cleaned) if cleaned else None
    except Exception as ex:
        result_v = f"EXCEPTION: {ex}"
    print(f"  parse_amount({v!r:20}) -> cleaned={cleaned!r:15} -> {result_v}")

# Cleanup
s3.delete_object(Bucket=BUCKET, Key=IMG_KEY)
print(f"\n[S3] Cleaned up s3://{BUCKET}/{IMG_KEY}")
print("\nDone.")
