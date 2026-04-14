from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class Group(models.Model):
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    members     = models.ManyToManyField(User, related_name='expense_groups', blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def total_expenses(self):
        return sum(r.total_amount or 0 for r in self.receipts.all())

    def member_count(self):
        return self.members.count()


class Receipt(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('processed', 'Processed'),
        ('error',     'Error'),
    ]
    group            = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='receipts')
    uploaded_by      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_receipts')
    paid_by          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_receipts')
    image_s3_url     = models.URLField(max_length=1000, blank=True)
    image_s3_key     = models.CharField(max_length=500, blank=True)
    merchant_name    = models.CharField(max_length=200, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    total_amount     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tax_amount       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency         = models.CharField(max_length=10, default='EUR')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.merchant_name or 'Receipt'} - {self.group.name}"

    def split_amount(self):
        members = self.group.members.count()
        if members and self.total_amount:
            return round(self.total_amount / members, 2)
        return Decimal('0.00')


class ExpenseSplit(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='splits')
    user    = models.ForeignKey(User, on_delete=models.CASCADE)
    amount  = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)


class Settlement(models.Model):
    group      = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='settlements')
    paid_by    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='settlements_paid')
    paid_to    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='settlements_received')
    amount     = models.DecimalField(max_digits=10, decimal_places=2)
    currency   = models.CharField(max_length=10, default='EUR')
    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ActivityLog(models.Model):
    group      = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='activities')
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    action     = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']