from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Group, Receipt


class SignUpForm(UserCreationForm):
    email      = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=50)
    last_name  = forms.CharField(max_length=50)

    class Meta:
        model  = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2')


class LoginForm(AuthenticationForm):
    pass


class GroupForm(forms.ModelForm):
    class Meta:
        model   = Group
        fields  = ('name', 'description')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class AddMemberForm(forms.Form):
    username = forms.CharField(max_length=150)

    def clean_username(self):
        username = self.cleaned_data['username']
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError(f'User "{username}" not found.')


class ReceiptForm(forms.ModelForm):
    class Meta:
        model   = Receipt
        fields  = ('merchant_name', 'transaction_date', 'total_amount', 'tax_amount', 'notes')
        widgets = {
            'transaction_date': forms.DateInput(attrs={'type': 'date'}),
            'notes':            forms.Textarea(attrs={'rows': 2}),
        }