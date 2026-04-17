# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os, json, boto3
from dotenv import load_dotenv

load_dotenv()

creds = dict(
    region_name           = os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id     = os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token     = os.getenv('AWS_SESSION_TOKEN'),
)
BUCKET = os.getenv('AWS_STORAGE_BUCKET_NAME', 'splitsmart-receipt')

GREEN  = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; RESET = "\033[0m"; BOLD = "\033[1m"

def ok(label, msg=""): print(f"  {GREEN}OK   {label}{RESET}  {msg}")
def fail(label, msg): print(f"  {RED}FAIL {label}{RESET}  -> {msg}")
def info(label, msg): print(f"  {YELLOW}INFO {label}{RESET}  -> {msg}")

# ── S3 DIAGNOSTICS ──────────────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}==== S3 Diagnostics ===={RESET}\n")

s3 = boto3.client('s3', **creds)

# 1. Bucket exists?
print(f"{BOLD}[1] Bucket existence{RESET}")
try:
    s3.head_bucket(Bucket=BUCKET)
    ok("head_bucket", f"'{BUCKET}' found")
except Exception as e:
    fail("head_bucket", e)

# 2. Bucket location
print(f"\n{BOLD}[2] Bucket region{RESET}")
try:
    loc = s3.get_bucket_location(Bucket=BUCKET)
    region = loc['LocationConstraint'] or 'us-east-1'
    if region != creds['region_name']:
        info("region mismatch", f"Bucket is in '{region}' but AWS_REGION='{creds['region_name']}'")
    else:
        ok("region", f"Bucket region matches: {region}")
except Exception as e:
    fail("get_bucket_location", e)

# 3. Bucket ACL / public access
print(f"\n{BOLD}[3] Public access block{RESET}")
try:
    pab = s3.get_public_access_block(Bucket=BUCKET)
    cfg = pab['PublicAccessBlockConfiguration']
    for k, v in cfg.items():
        status = f"{RED}BLOCKED{RESET}" if v else f"{GREEN}ALLOWED{RESET}"
        print(f"     {k}: {status}")
except Exception as e:
    info("public_access_block", f"Could not read ({e})")

# 4. Upload a tiny test object
print(f"\n{BOLD}[4] Upload test (PutObject){RESET}")
TEST_KEY = "diagnostics/test_upload.txt"
try:
    s3.put_object(Bucket=BUCKET, Key=TEST_KEY, Body=b"splitsmart-test", ContentType="text/plain")
    ok("put_object", f"Uploaded -> s3://{BUCKET}/{TEST_KEY}")
    upload_ok = True
except Exception as e:
    fail("put_object", e)
    upload_ok = False

# 5. Download / GetObject
print(f"\n{BOLD}[5] Download test (GetObject){RESET}")
if upload_ok:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=TEST_KEY)
        body = obj['Body'].read()
        ok("get_object", f"Read back {len(body)} bytes")
    except Exception as e:
        fail("get_object", e)
else:
    info("get_object", "Skipped (upload failed)")

# 6. Presigned URL
print(f"\n{BOLD}[6] Presigned URL generation{RESET}")
if upload_ok:
    try:
        url = s3.generate_presigned_url('get_object',
            Params={'Bucket': BUCKET, 'Key': TEST_KEY}, ExpiresIn=300)
        ok("presigned_url", f"{url[:80]}...")
    except Exception as e:
        fail("presigned_url", e)

# 7. Upload a minimal valid JPEG (1x1 pixel) for Textract test
print(f"\n{BOLD}[7] Upload sample image for Textract{RESET}")
# Minimal 1x1 JPEG bytes
JPEG_1x1 = bytes([
    0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,
    0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,
    0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,0x07,0x07,0x07,0x09,
    0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
    0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,
    0x24,0x2E,0x27,0x20,0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,
    0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,0x39,0x3D,0x38,0x32,
    0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
    0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,
    0x01,0x05,0x01,0x01,0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
    0x09,0x0A,0x0B,0xFF,0xC4,0x00,0xB5,0x10,0x00,0x02,0x01,0x03,
    0x03,0x02,0x04,0x03,0x05,0x05,0x04,0x04,0x00,0x00,0x01,0x7D,
    0x01,0x02,0x03,0x00,0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,
    0x13,0x51,0x61,0x07,0x22,0x71,0x14,0x32,0x81,0x91,0xA1,0x08,
    0x23,0x42,0xB1,0xC1,0x15,0x52,0xD1,0xF0,0x24,0x33,0x62,0x72,
    0x82,0x09,0x0A,0x16,0x17,0x18,0x19,0x1A,0x25,0x26,0x27,0x28,
    0x29,0x2A,0x34,0x35,0x36,0x37,0x38,0x39,0x3A,0x43,0x44,0x45,
    0x46,0x47,0x48,0x49,0x4A,0x53,0x54,0x55,0x56,0x57,0x58,0x59,
    0x5A,0x63,0x64,0x65,0x66,0x67,0x68,0x69,0x6A,0x73,0x74,0x75,
    0x76,0x77,0x78,0x79,0x7A,0x83,0x84,0x85,0x86,0x87,0x88,0x89,
    0x8A,0x93,0x94,0x95,0x96,0x97,0x98,0x99,0x9A,0xA2,0xA3,0xA4,
    0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xB2,0xB3,0xB4,0xB5,0xB6,0xB7,
    0xB8,0xB9,0xBA,0xC2,0xC3,0xC4,0xC5,0xC6,0xC7,0xC8,0xC9,0xCA,
    0xD2,0xD3,0xD4,0xD5,0xD6,0xD7,0xD8,0xD9,0xDA,0xE1,0xE2,0xE3,
    0xE4,0xE5,0xE6,0xE7,0xE8,0xE9,0xEA,0xF1,0xF2,0xF3,0xF4,0xF5,
    0xF6,0xF7,0xF8,0xF9,0xFA,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,
    0x00,0x3F,0x00,0xFB,0xD2,0x8A,0x28,0x03,0xFF,0xD9
])
IMG_KEY = "diagnostics/test_receipt.jpg"
img_upload_ok = False
try:
    s3.put_object(Bucket=BUCKET, Key=IMG_KEY, Body=JPEG_1x1, ContentType='image/jpeg')
    ok("image_upload", f"Uploaded -> s3://{BUCKET}/{IMG_KEY}")
    img_upload_ok = True
except Exception as e:
    fail("image_upload", e)

# Cleanup test.txt
if upload_ok:
    try:
        s3.delete_object(Bucket=BUCKET, Key=TEST_KEY)
    except:
        pass

# ── TEXTRACT DIAGNOSTICS ────────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}==== Textract Diagnostics ===={RESET}\n")

tx = boto3.client('textract', **creds)

# 1. detect_document_text on inline bytes (no S3 needed)
print(f"{BOLD}[1] DetectDocumentText (inline bytes){RESET}")
try:
    resp = tx.detect_document_text(Document={'Bytes': JPEG_1x1})
    blocks = resp.get('Blocks', [])
    ok("detect_document_text", f"Returned {len(blocks)} block(s)")
except Exception as e:
    fail("detect_document_text", e)

# 2. analyze_expense on S3 image
print(f"\n{BOLD}[2] AnalyzeExpense (S3 object){RESET}")
if img_upload_ok:
    try:
        resp = tx.analyze_expense(
            Document={'S3Object': {'Bucket': BUCKET, 'Name': IMG_KEY}}
        )
        docs = resp.get('ExpenseDocuments', [])
        ok("analyze_expense", f"Returned {len(docs)} expense document(s)")
    except Exception as e:
        fail("analyze_expense", e)
        print(f"\n  {YELLOW}Full error detail:{RESET}")
        print(f"  {e}")
else:
    info("analyze_expense", "Skipped (image upload to S3 failed)")

# 3. Check IAM permissions summary
print(f"\n{BOLD}[3] IAM role / permissions note{RESET}")
sts = boto3.client('sts', **creds)
try:
    identity = sts.get_caller_identity()
    info("caller", f"ARN = {identity['Arn']}")
    if 'voclabs' in identity['Arn']:
        info("role", "AWS Academy voclabs role detected — Textract may be restricted in Academy labs")
except Exception as e:
    fail("sts", e)

# Cleanup image
if img_upload_ok:
    try:
        s3.delete_object(Bucket=BUCKET, Key=IMG_KEY)
        info("cleanup", f"Removed s3://{BUCKET}/{IMG_KEY}")
    except:
        pass

print(f"\n{BOLD}{CYAN}==== Done ===={RESET}\n")
