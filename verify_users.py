import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'splitsmart.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.auth import authenticate

print("=== Users in DB ===")
for u in User.objects.all():
    print(f"  id={u.id}  username={u.username}  email={u.email}  superuser={u.is_superuser}  active={u.is_active}")

print()
u1 = authenticate(username='admin', password='Admin@1234')
print(f"admin login     : {'PASS' if u1 else 'FAIL'}")
u2 = authenticate(username='testuser', password='Test@1234')
print(f"testuser login  : {'PASS' if u2 else 'FAIL'}")
