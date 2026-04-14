from django.contrib import admin
from .models import Group, Receipt, ExpenseSplit, Settlement, ActivityLog

admin.site.register(Group)
admin.site.register(Receipt)
admin.site.register(ExpenseSplit)
admin.site.register(Settlement)
admin.site.register(ActivityLog)