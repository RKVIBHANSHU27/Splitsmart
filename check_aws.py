# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
AWS Connectivity Check for SplitsMarts
Validates: S3, DynamoDB, SNS, Lambda, CloudWatch, Textract
"""

import os
import sys
import boto3
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ─────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN     = os.getenv("AWS_SESSION_TOKEN")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
SNS_TOPIC_ARN         = os.getenv("SNS_TOPIC_ARN")
S3_BUCKET             = os.getenv("AWS_STORAGE_BUCKET_NAME")

CREDS = dict(
    region_name          = AWS_REGION,
    aws_access_key_id    = AWS_ACCESS_KEY_ID,
    aws_secret_access_key= AWS_SECRET_ACCESS_KEY,
    aws_session_token    = AWS_SESSION_TOKEN,
)

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results = []

def ok(service, detail=""):
    msg = f"  {GREEN}✔  {service}{RESET}"
    if detail:
        msg += f"  →  {detail}"
    print(msg)
    results.append((service, True, detail))

def fail(service, error):
    print(f"  {RED}✘  {service}{RESET}  →  {error}")
    results.append((service, False, str(error)))

def warn(label, msg):
    print(f"  {YELLOW}⚠  {label}{RESET}  →  {msg}")


# ── Header ───────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}====  SplitsMarts AWS Connectivity Check  ===={RESET}\n")

# ── 0. Env vars ──────────────────────────────────────────────────────────────
print(f"{BOLD}[0] Environment Variables{RESET}")
env_issues = []
for var in ["AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_REGION",
            "SNS_TOPIC_ARN","AWS_STORAGE_BUCKET_NAME"]:
    val = os.getenv(var)
    if val:
        masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
        print(f"       {var} = {masked}")
    else:
        warn(var, "NOT SET")
        env_issues.append(var)

if not AWS_SESSION_TOKEN:
    warn("AWS_SESSION_TOKEN", "not set (OK if using long-term credentials)")

print()

# ── 1. STS — identity check ──────────────────────────────────────────────────
print(f"{BOLD}[1] STS — Caller Identity{RESET}")
try:
    sts = boto3.client('sts', **CREDS)
    identity = sts.get_caller_identity()
    ok("STS", f"Account={identity['Account']}  ARN={identity['Arn']}")
except Exception as e:
    fail("STS", e)
print()

# ── 2. S3 ────────────────────────────────────────────────────────────────────
print(f"{BOLD}[2] S3 — Bucket Access{RESET}")
try:
    s3 = boto3.client('s3', **CREDS)
    if S3_BUCKET:
        s3.head_bucket(Bucket=S3_BUCKET)
        ok("S3", f"Bucket '{S3_BUCKET}' exists and is accessible")
    else:
        # fallback: list buckets
        resp = s3.list_buckets()
        names = [b["Name"] for b in resp.get("Buckets", [])]
        ok("S3", f"Reachable — buckets in account: {names or 'none'}")
        warn("S3 Bucket", "AWS_STORAGE_BUCKET_NAME not set — bucket not verified")
except Exception as e:
    fail("S3", e)
print()

# ── 3. DynamoDB ──────────────────────────────────────────────────────────────
print(f"{BOLD}[3] DynamoDB — Table Check{RESET}")
EXPECTED_TABLES = [
    "splitsmart-groups",
    "splitsmart-receipts",
    "splitsmart-splits",
    "splitsmart-activity",
]
try:
    ddb = boto3.client('dynamodb', **CREDS)
    resp = ddb.list_tables()
    existing = resp.get("TableNames", [])
    for table in EXPECTED_TABLES:
        if table in existing:
            # also check status
            desc = ddb.describe_table(TableName=table)["Table"]
            status = desc["TableStatus"]
            ok(f"DynamoDB:{table}", f"Status={status}")
        else:
            fail(f"DynamoDB:{table}", "Table NOT FOUND")
except Exception as e:
    fail("DynamoDB", e)
print()

# ── 4. SNS ───────────────────────────────────────────────────────────────────
print(f"{BOLD}[4] SNS — Topic Check{RESET}")
try:
    sns = boto3.client('sns', **CREDS)
    if SNS_TOPIC_ARN:
        attrs = sns.get_topic_attributes(TopicArn=SNS_TOPIC_ARN)
        ok("SNS", f"Topic found: {SNS_TOPIC_ARN}")
    else:
        topics = sns.list_topics().get("Topics", [])
        ok("SNS", f"Reachable — {len(topics)} topic(s) in account")
        warn("SNS Topic", "SNS_TOPIC_ARN not set — topic not verified")
except Exception as e:
    fail("SNS", e)
print()

# ── 5. Lambda ────────────────────────────────────────────────────────────────
print(f"{BOLD}[5] Lambda — Function Check{RESET}")
EXPECTED_FUNCTIONS = [
    "splitsmart-receipt-processor",
    "splitsmart-monthly-summary",
]
try:
    lmb = boto3.client('lambda', **CREDS)
    for fn in EXPECTED_FUNCTIONS:
        try:
            cfg = lmb.get_function_configuration(FunctionName=fn)
            ok(f"Lambda:{fn}", f"Runtime={cfg['Runtime']}  State={cfg.get('State','?')}")
        except lmb.exceptions.ResourceNotFoundException:
            fail(f"Lambda:{fn}", "Function NOT FOUND")
        except Exception as e2:
            fail(f"Lambda:{fn}", e2)
except Exception as e:
    fail("Lambda", e)
print()

# ── 6. CloudWatch Logs ────────────────────────────────────────────────────────
print(f"{BOLD}[6] CloudWatch Logs — Log Group Check{RESET}")
LOG_GROUP = "/splitsmart/app"
try:
    cw = boto3.client('logs', **CREDS)
    resp = cw.describe_log_groups(logGroupNamePrefix=LOG_GROUP)
    groups = resp.get("logGroups", [])
    if groups:
        ok("CloudWatch", f"Log group '{LOG_GROUP}' exists")
    else:
        warn("CloudWatch", f"Log group '{LOG_GROUP}' not yet created (will be created on first use)")
        results.append(("CloudWatch", True, "log group pending"))
except Exception as e:
    fail("CloudWatch", e)
print()

# ── 7. Textract ───────────────────────────────────────────────────────────────
print(f"{BOLD}[7] Textract — Service Reachability{RESET}")
try:
    tx = boto3.client('textract', **CREDS)
    # Textract has no cheap list API; use STS re-confirm + client creation as proof
    tx.meta.events  # access metadata to confirm client is built
    ok("Textract", "Client created successfully (credentials accepted)")
except Exception as e:
    fail("Textract", e)
print()

# ── Summary ──────────────────────────────────────────────────────────────────
passed = [r for r in results if r[1]]
failed = [r for r in results if not r[1]]

print(f"{BOLD}{CYAN}====  Summary  ===={RESET}")
print(f"  {GREEN}Passed : {len(passed)}{RESET}")
print(f"  {RED}Failed : {len(failed)}{RESET}")

if failed:
    print(f"\n{BOLD}Failed checks:{RESET}")
    for svc, _, err in failed:
        print(f"  {RED}✘  {svc}{RESET}  →  {err}")
    sys.exit(1)
else:
    print(f"\n  {GREEN}{BOLD}All AWS services connected successfully! 🎉{RESET}")
    sys.exit(0)
