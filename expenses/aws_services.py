import boto3
import uuid
import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class S3Service:
    """OOP library for AWS S3 receipt image storage."""

    def __init__(self):
        self.client = boto3.client(
            's3',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,
        )
        self.bucket = settings.AWS_STORAGE_BUCKET_NAME

    def upload_receipt(self, file_obj, user_id, group_id):
        try:
            ext = os.path.splitext(file_obj.name)[1].lower()
            key = f"receipts/user_{user_id}/group_{group_id}/{uuid.uuid4()}{ext}"
            self.client.upload_fileobj(
                file_obj, self.bucket, key,
                ExtraArgs={
                    'ContentType': self._get_content_type(ext),
                 }
             )
            url = f"https://{self.bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
            return {'success': True, 'url': url, 'key': key}
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return {'success': False, 'error': str(e)}

    def delete_receipt(self, key):
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return {'success': True}
        except Exception as e:
            logger.error(f"S3 delete failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_public_url(self, key):
        return f"https://{self.bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"

    def _get_content_type(self, ext):
        types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png',  '.pdf':  'application/pdf',
        }
        return types.get(ext, 'application/octet-stream')
    
    def generate_presigned_url(self, key, expiry=3600):
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': key},
                ExpiresIn=expiry  # 1 hour
            )
            return url
        except Exception as e:
            logger.error(f"Presigned URL failed: {e}")
            return None


class TextractService:
    """OOP library for AWS Textract OCR on receipts."""

    def __init__(self):
        self.client = boto3.client(
            'textract',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN, 
        )
        self.bucket = settings.AWS_STORAGE_BUCKET_NAME

    def extract_receipt(self, s3_key):
        try:
            response = self.client.analyze_expense(
                Document={'S3Object': {'Bucket': self.bucket, 'Name': s3_key}}
            )
            return {'success': True, 'data': self._parse_response(response)}
        except Exception as e:
            logger.error(f"Textract failed: {e}")
            return {'success': False, 'error': str(e)}

    def _parse_response(self, response):
        result = {
            'merchant_name':    '',
            'total_amount':     None,
            'tax_amount':       None,
            'transaction_date': '',
        }
        for doc in response.get('ExpenseDocuments', []):
            for field in doc.get('SummaryFields', []):
                self._map_field(
                    result,
                    field.get('Type', {}).get('Text', ''),
                    field.get('ValueDetection', {}).get('Text', '')
                )
        return result

    def _map_field(self, result, field_type, field_value):
        if field_type == 'NAME':
            result['merchant_name'] = field_value
        elif field_type == 'TOTAL':
            result['total_amount'] = self._parse_amount(field_value)
        elif field_type == 'TAX':
            result['tax_amount'] = self._parse_amount(field_value)
        elif field_type == 'INVOICE_RECEIPT_DATE':
            result['transaction_date'] = field_value

    def _parse_amount(self, value):
        try:
            return float(value.replace('€','').replace('$','').replace(',','').strip())
        except:
            return None


class SNSService:
    """OOP library for AWS SNS email notifications."""

    def __init__(self):
        self.client    = boto3.client(
            'sns',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN, 
        )
        self.topic_arn = settings.SNS_TOPIC_ARN

    def notify(self, subject, message):
        try:
            self.client.publish(
                TopicArn=self.topic_arn,
                Subject=subject,
                Message=message,
            )
            return {'success': True}
        except Exception as e:
            logger.error(f"SNS failed: {e}")
            return {'success': False, 'error': str(e)}

    def notify_new_expense(self, group_name, username, amount, currency):
        return self.notify(
            subject=f'New expense in {group_name}',
            message=f'{username} added {currency} {amount} in "{group_name}".\n\nLog in to SplitSmart to view details.'
        )

    def notify_settlement(self, group_name, payer, payee, amount, currency):
        return self.notify(
            subject=f'Payment recorded in {group_name}',
            message=f'{payer} paid {payee} {currency} {amount} in "{group_name}".'
        )

    def notify_member_added(self, group_name, new_member, added_by):
        return self.notify(
            subject=f'You were added to {group_name} on SplitSmart',
            message=f'Hi {new_member},\n\n{added_by} added you to "{group_name}" on SplitSmart.\n\nLog in to view your expenses.'
        )

class LambdaService:
    """OOP library for AWS Lambda function invocation."""

    def __init__(self):
        self.client = boto3.client(
            'lambda',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,
        )

    def invoke_receipt_processor(self, bucket, key):
        """Manually invoke the receipt processor Lambda."""
        try:
            payload = {
                'Records': [{
                    's3': {
                        'bucket': {'name': bucket},
                        'object': {'key': key}
                    }
                }]
            }
            response = self.client.invoke(
                FunctionName='splitsmart-receipt-processor',
                InvocationType='Event',  # async
                Payload=json.dumps(payload)
            )
            logger.info(f"Lambda invoked: {response['StatusCode']}")
            return {'success': True, 'status': response['StatusCode']}
        except Exception as e:
            logger.error(f"Lambda invoke failed: {e}")
            return {'success': False, 'error': str(e)}

    def invoke_monthly_summary(self):
        """Manually trigger the monthly summary Lambda."""
        try:
            response = self.client.invoke(
                FunctionName='splitsmart-monthly-summary',
                InvocationType='Event',  # async
            )
            return {'success': True, 'status': response['StatusCode']}
        except Exception as e:
            logger.error(f"Lambda monthly invoke failed: {e}")
            return {'success': False, 'error': str(e)}

# Singletons
s3       = S3Service()
textract = TextractService()
sns      = SNSService()
lambda_service = LambdaService()