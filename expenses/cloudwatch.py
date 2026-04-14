import boto3
import time
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class CloudWatchLogger:
    """OOP library for AWS CloudWatch application logging."""

    def __init__(self):
        self.client     = boto3.client(
            'logs',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN, 
        )
        self.log_group  = '/splitsmart/app'
        self.log_stream = 'django-app'
        self._setup()

    def _setup(self):
        try:
            self.client.create_log_group(logGroupName=self.log_group)
        except:
            pass
        try:
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except:
            pass

    def log(self, level, action, user=None, details=None):
        try:
            self.client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
                logEvents=[{
                    'timestamp': int(time.time() * 1000),
                    'message':   json.dumps({
                        'level':   level,
                        'action':  action,
                        'user':    str(user) if user else 'anonymous',
                        'details': details or {},
                    }),
                }]
            )
        except Exception as e:
            logger.error(f"CloudWatch log failed: {e}")

    def info(self, action, user=None, details=None):
        self.log('INFO', action, user, details)

    def error(self, action, user=None, details=None):
        self.log('ERROR', action, user, details)

    def warning(self, action, user=None, details=None):
        self.log('WARNING', action, user, details)


# Singleton
cw = CloudWatchLogger()