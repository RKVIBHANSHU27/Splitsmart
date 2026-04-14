from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from decimal import Decimal
from .models import Group, Receipt, ExpenseSplit, Settlement, ActivityLog
from .forms import SignUpForm, LoginForm, GroupForm, AddMemberForm, ReceiptForm
from .aws_services import s3, textract, sns, lambda_service
from .cloudwatch import cw
from .dynamodb import db

CURRENCIES = ['EUR', 'USD', 'GBP', 'INR', 'AUD', 'CAD']


# AUTH----------------------------------- 
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            cw.info('user_signup', user=user.username, details={'email': user.email})
            messages.success(request, f'Welcome {user.first_name}!')
            return redirect('dashboard')
        else:
            cw.warning('signup_failed', details={'errors': str(form.errors)})
    else:
        form = SignUpForm()
    return render(request, 'expenses/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            cw.info('user_login', user=user.username)
            return redirect('dashboard')
        else:
            cw.warning('login_failed', details={'username': request.POST.get('username')})
    else:
        form = LoginForm()
    return render(request, 'expenses/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


#  HELPERS ----------------------------------------------------
def get_balances(group):
    balances = {m.pk: Decimal('0.00') for m in group.members.all()}
    for receipt in group.receipts.all():
        if not receipt.total_amount:
            continue
        payer = receipt.paid_by or receipt.uploaded_by
        for split in receipt.splits.all():
            if split.user == payer or split.is_paid:
                continue
            balances[payer.pk]      = balances.get(payer.pk, Decimal('0')) + split.amount
            balances[split.user.pk] = balances.get(split.user.pk, Decimal('0')) - split.amount
    for s in group.settlements.all():
        balances[s.paid_by.pk] = balances.get(s.paid_by.pk, Decimal('0')) + s.amount
        balances[s.paid_to.pk] = balances.get(s.paid_to.pk, Decimal('0')) - s.amount
    return balances


def get_debts(group):
    balances = get_balances(group)
    members  = {m.pk: m for m in group.members.all()}
    debts    = []
    pos = sorted([(pk, amt) for pk, amt in balances.items() if amt > 0 and pk in members], key=lambda x: -x[1])
    neg = sorted([(pk, amt) for pk, amt in balances.items() if amt < 0 and pk in members], key=lambda x: -x[1])
    neg = [(pk, -amt) for pk, amt in neg]
    i = j = 0
    while i < len(pos) and j < len(neg):
        creditor_pk, credit = pos[i]
        debtor_pk,   debt   = neg[j]
        amount = min(credit, debt)
        debts.append((members[debtor_pk], members[creditor_pk], round(amount, 2)))
        pos[i] = (creditor_pk, credit - amount)
        neg[j] = (debtor_pk,   debt - amount)
        if pos[i][1] == 0: i += 1
        if neg[j][1] == 0: j += 1
    return debts


#  DASHBOARD ---------------------------------------------------------
@login_required
def dashboard_view(request):
    groups       = request.user.expense_groups.all()
    all_receipts = Receipt.objects.filter(group__members=request.user)
    total_owed   = Decimal('0.00')
    total_owe    = Decimal('0.00')
    for group in groups:
        for debtor, creditor, amount in get_debts(group):
            if creditor == request.user: total_owed += amount
            if debtor   == request.user: total_owe  += amount
    return render(request, 'expenses/dashboard.html', {
        'groups':          groups,
        'recent_receipts': Receipt.objects.filter(group__members=request.user).order_by('-created_at')[:5],
        'total_spent':     sum(r.total_amount or 0 for r in all_receipts),
        'total_groups':    groups.count(),
        'total_receipts':  all_receipts.count(),
        'pending':         all_receipts.filter(status='pending').count(),
        'total_owed':      total_owed,
        'total_owe':       total_owe,
    })


# GROUPS --------------------------------------------
@login_required
def group_list_view(request):
    return render(request, 'expenses/groups.html', {
        'groups': request.user.expense_groups.all()
    })


@login_required
def group_create_view(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()
            group.members.add(request.user)
            db.save_group(group)
            activity = ActivityLog.objects.create(
                group=group, user=request.user,
                action=f'created group "{group.name}"'
            )
            db.save_activity(activity)
            cw.info('group_created', user=request.user.username, details={'group': group.name})
            messages.success(request, f'Group "{group.name}" created!')
            return redirect('group-detail', pk=group.pk)
    else:
        form = GroupForm()
    return render(request, 'expenses/group-form.html', {'form': form, 'action': 'Create'})


@login_required
def group_detail_view(request, pk):
    group           = get_object_or_404(Group, pk=pk, members=request.user)
    balances        = get_balances(group)
    member_balances = [
        {'user': m, 'balance': balances.get(m.pk, Decimal('0.00'))}
        for m in group.members.all()
    ]
    return render(request, 'expenses/group-detail.html', {
        'group':           group,
        'receipts':        group.receipts.all().order_by('-created_at'),
        'add_member_form': AddMemberForm(),
        'debts':           get_debts(group),
        'member_balances': member_balances,
        'activities':      group.activities.all()[:10],
        'currencies':      CURRENCIES,
    })


@login_required
def group_delete_view(request, pk):
    group = get_object_or_404(Group, pk=pk, created_by=request.user)
    if request.method == 'POST':
        name = group.name
        db.delete_group(group.pk)
        group.delete()
        cw.info('group_deleted', user=request.user.username, details={'group': name})
        messages.success(request, f'Group "{name}" deleted.')
        return redirect('groups')
    return render(request, 'expenses/confirm-delete.html', {'object': group, 'type': 'Group'})


@login_required
def add_member_view(request, pk):
    group = get_object_or_404(Group, pk=pk, created_by=request.user)
    if request.method == 'POST':
        form = AddMemberForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['username']
            group.members.add(user)
            db.save_group(group)
            activity = ActivityLog.objects.create(
                group=group, user=request.user,
                action=f'added {user.username} to the group'
            )
            db.save_activity(activity)
            sns.notify_member_added(group.name, user.username, request.user.username)
            cw.info('member_added', user=request.user.username, details={'added': user.username})
            messages.success(request, f'{user.username} added.')
    return redirect('group-detail', pk=pk)


@login_required
def remove_member_view(request, pk, user_id):
    group = get_object_or_404(Group, pk=pk, created_by=request.user)
    user  = get_object_or_404(User, pk=user_id)
    if user != request.user:
        group.members.remove(user)
        remaining_members = group.members.all()
        for receipt in group.receipts.all():
            if not receipt.total_amount:
                continue
            receipt.splits.filter(user=user).delete()
            receipt.splits.all().delete()
            if remaining_members.count() > 0:
                split_amount = receipt.total_amount / remaining_members.count()
                for member in remaining_members:
                    ExpenseSplit.objects.create(
                        receipt=receipt,
                        user=member,
                        amount=round(split_amount, 2)
                    )
        db.save_group(group)
        activity = ActivityLog.objects.create(
            group=group, user=request.user,
            action=f'removed {user.username}'
        )
        db.save_activity(activity)
        cw.info('member_removed', user=request.user.username, details={'removed': user.username})
        messages.success(request, f'{user.username} removed.')
    return redirect('group-detail', pk=pk)


# RECEIPTS-------------------------------------------------------------
@login_required
def receipt_upload_view(request, group_pk):
    group = get_object_or_404(Group, pk=group_pk, members=request.user)
    if request.method == 'POST':
        form = ReceiptForm(request.POST, request.FILES)
        if form.is_valid():
            receipt             = form.save(commit=False)
            receipt.group       = group
            receipt.uploaded_by = request.user
            receipt.paid_by     = request.user
            receipt.status      = 'processed'
            receipt.currency    = request.POST.get('currency', 'EUR')

            paid_by_id = request.POST.get('paid_by')
            if paid_by_id:
                try:
                    receipt.paid_by = User.objects.get(pk=paid_by_id)
                except User.DoesNotExist:
                    pass

            # S3 Upload
            image_file = request.FILES.get('image')
            if image_file:
                s3_result = s3.upload_receipt(image_file, request.user.pk, group.pk)
                if s3_result['success']:
                    receipt.image_s3_url = s3_result['url']
                    receipt.image_s3_key = s3_result['key']
                    receipt.status       = 'pending'
                    # Invoke Lambda automatically
                    lambda_service.invoke_receipt_processor(
                        settings.AWS_STORAGE_BUCKET_NAME,
                        s3_result['key']
                    )
                    cw.info('s3_upload', user=request.user.username, details={'key': s3_result['key']})
                else:
                    cw.error('s3_failed', user=request.user.username, details={'error': s3_result['error']})

            receipt.save()

            # Textract OCR
            if receipt.image_s3_key:
                ocr = textract.extract_receipt(receipt.image_s3_key)
                if ocr['success']:
                    data = ocr['data']
                    if data['merchant_name'] and not receipt.merchant_name:
                        receipt.merchant_name = data['merchant_name']
                    if data['total_amount'] and not receipt.total_amount:
                        receipt.total_amount = data['total_amount']
                    if data['tax_amount'] and not receipt.tax_amount:
                        receipt.tax_amount = data['tax_amount']
                    receipt.status = 'processed'
                    receipt.save()
                    cw.info('textract_success', user=request.user.username, details=data)
                    messages.info(request, f'Extracted: {data["merchant_name"]} — {data["total_amount"]}')
                else:
                    cw.error('textract_failed', user=request.user.username, details={'error': ocr['error']})
                    receipt.status = 'processed'
                    receipt.save()

            # DynamoDB
            db.save_receipt(receipt)

            # Split
            selected      = request.POST.getlist('members')
            split_members = User.objects.filter(pk__in=selected) if selected else group.members.all()
            if receipt.total_amount and split_members.count():
                split_amount = receipt.total_amount / split_members.count()
                for member in split_members:
                    split = ExpenseSplit.objects.create(
                        receipt=receipt, user=member, amount=round(split_amount, 2)
                    )
                    db.save_split(split)

            activity = ActivityLog.objects.create(
                group=group, user=request.user,
                action=f'added "{receipt.merchant_name or "receipt"}" for {receipt.currency} {receipt.total_amount}'
            )
            db.save_activity(activity)
            sns.notify_new_expense(group.name, request.user.username, receipt.total_amount, receipt.currency)
            cw.info('receipt_uploaded', user=request.user.username, details={'amount': str(receipt.total_amount)})
            messages.success(request, 'Receipt uploaded!')
            return redirect('receipt-detail', pk=receipt.pk)
    else:
        form = ReceiptForm()
    return render(request, 'expenses/receipt-upload.html', {
        'form':       form,
        'group':      group,
        'members':    group.members.all(),
        'currencies': CURRENCIES,
    })


@login_required
def receipt_detail_view(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    splits  = receipt.splits.all()
    non_payer_splits = splits.exclude(user=receipt.paid_by)
    count = non_payer_splits.count()
    per_person = round(receipt.total_amount / count, 2) if receipt.total_amount and count > 0 else 0
    image_url = None
    if receipt.image_s3_key:
        image_url = s3.generate_presigned_url(receipt.image_s3_key)
    return render(request, 'expenses/receipt-detail.html', {
        'receipt': receipt,
        'splits':  splits,
        'non_payer_splits_count': count,
        'per_person_amount': per_person,
        'image_url': image_url,
    })


@login_required
def receipt_delete_view(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk, uploaded_by=request.user)
    if request.method == 'POST':
        group_pk = receipt.group.pk
        if receipt.image_s3_key:
            s3.delete_receipt(receipt.image_s3_key)
        db.delete_receipt(receipt.pk, receipt.group.pk)
        activity = ActivityLog.objects.create(
            group=receipt.group, user=request.user,
            action=f'deleted "{receipt.merchant_name}"'
        )
        db.save_activity(activity)
        cw.info('receipt_deleted', user=request.user.username)
        receipt.delete()
        messages.success(request, 'Receipt deleted.')
        return redirect('group-detail', pk=group_pk)
    return render(request, 'expenses/confirm-delete.html', {'object': receipt, 'type': 'Receipt'})


@login_required
def mark_paid_view(request, split_id):
    split         = get_object_or_404(ExpenseSplit, pk=split_id, user=request.user)
    split.is_paid = not split.is_paid
    split.save()
    db.save_split(split)
    cw.info('split_toggled', user=request.user.username, details={'is_paid': split.is_paid})
    return redirect('receipt-detail', pk=split.receipt.pk)  


@login_required
def manual_split_view(request, pk):
    group = get_object_or_404(Group, pk=pk, members=request.user)
    if request.method == 'POST':
        total            = request.POST.get('total_amount')
        selected_members = request.POST.getlist('members')
        description      = request.POST.get('description', 'Manual Split')
        paid_by_id       = request.POST.get('paid_by')
        currency         = request.POST.get('currency', 'EUR')
        if total and selected_members:
            total_decimal = Decimal(total)
            paid_by       = request.user
            if paid_by_id:
                try:
                    paid_by = User.objects.get(pk=paid_by_id)
                except User.DoesNotExist:
                    pass
            receipt = Receipt.objects.create(
                group=group, uploaded_by=request.user, paid_by=paid_by,
                merchant_name=description, total_amount=total_decimal,
                currency=currency, status='processed',
            )
            split_amount = total_decimal / len(selected_members)
            for user_id in selected_members:
                split = ExpenseSplit.objects.create(
                    receipt=receipt,
                    user=User.objects.get(pk=user_id),
                    amount=round(split_amount, 2)
                )
                db.save_split(split)
            db.save_receipt(receipt)
            activity = ActivityLog.objects.create(
                group=group, user=request.user,
                action=f'added "{description}" for {currency} {total}'
            )
            db.save_activity(activity)
            sns.notify_new_expense(group.name, request.user.username, total, currency)
            cw.info('manual_split', user=request.user.username, details={'amount': total})
            messages.success(request, 'Split saved!')
        else:
            messages.error(request, 'Enter amount and select at least one member.')
    return redirect('group-detail', pk=pk)  


@login_required
def settle_up_view(request, pk):
    group = get_object_or_404(Group, pk=pk, members=request.user)
    if request.method == 'POST':
        paid_to_id = request.POST.get('paid_to')
        amount     = request.POST.get('amount')
        note       = request.POST.get('note', '')
        currency   = request.POST.get('currency', 'EUR')
        if paid_to_id and amount:
            paid_to = get_object_or_404(User, pk=paid_to_id)
            Settlement.objects.create(
                group=group, paid_by=request.user, paid_to=paid_to,
                amount=Decimal(amount), currency=currency, note=note
            )
            activity = ActivityLog.objects.create(
                group=group, user=request.user,
                action=f'settled {currency} {amount} with {paid_to.username}'
            )
            db.save_activity(activity)
            sns.notify_settlement(group.name, request.user.username, paid_to.username, amount, currency)
            cw.info('settle_up', user=request.user.username, details={'amount': amount})
            messages.success(request, 'Settlement recorded!')
    return redirect('group-detail', pk=pk)  