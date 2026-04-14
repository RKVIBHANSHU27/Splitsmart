import boto3
import uuid
from datetime import datetime
from django.conf import settings


class DynamoDB:
    """OOP library for AWS DynamoDB — stores all app data."""

    def __init__(self):
        self.resource       = boto3.resource(
            'dynamodb',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN, 
        )
        self.groups_table   = self.resource.Table('splitsmart-groups')
        self.receipts_table = self.resource.Table('splitsmart-receipts')
        self.splits_table   = self.resource.Table('splitsmart-splits')
        self.activity_table = self.resource.Table('splitsmart-activity')

    def save_group(self, group):
        try:
            self.groups_table.put_item(Item={
                'group_id':    str(group.pk),
                'name':        group.name,
                'description': group.description,
                'created_by':  group.created_by.username,
                'members':     [m.username for m in group.members.all()],
                'created_at':  str(group.created_at),
            })
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_group(self, group_id):
        try:
            self.groups_table.delete_item(Key={'group_id': str(group_id)})
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def save_receipt(self, receipt):
        try:
            self.receipts_table.put_item(Item={
                'receipt_id':       str(receipt.pk),
                'group_id':         str(receipt.group.pk),
                'group_name':       receipt.group.name,
                'uploaded_by':      receipt.uploaded_by.username,
                'paid_by':          receipt.paid_by.username if receipt.paid_by else '',
                'merchant_name':    receipt.merchant_name or '',
                'total_amount':     str(receipt.total_amount or 0),
                'tax_amount':       str(receipt.tax_amount or 0),
                'currency':         receipt.currency or 'EUR',
                'status':           receipt.status,
                'image_s3_url':     receipt.image_s3_url or '',
                'image_s3_key':     receipt.image_s3_key or '',
                'notes':            receipt.notes or '',
                'transaction_date': str(receipt.transaction_date or ''),
                'created_at':       str(receipt.created_at),
            })
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_receipt(self, receipt_id, group_id):
        try:
            self.receipts_table.delete_item(
                Key={'receipt_id': str(receipt_id), 'group_id': str(group_id)}
            )
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def save_split(self, split):
        try:
            self.splits_table.put_item(Item={
                'split_id':   str(split.pk),
                'receipt_id': str(split.receipt.pk),
                'username':   split.user.username,
                'amount':     str(split.amount),
                'is_paid':    split.is_paid,
                'created_at': str(datetime.now()),
            })
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def save_activity(self, activity):
        try:
            self.activity_table.put_item(Item={
                'activity_id': str(uuid.uuid4()),
                'group_id':    str(activity.group.pk),
                'username':    activity.user.username,
                'action':      activity.action,
                'created_at':  str(activity.created_at),
            })
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Singleton
db = DynamoDB()