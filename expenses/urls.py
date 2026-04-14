from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login'), name='home'), 
    path('signup/',                                 views.signup_view,         name='signup'),
    path('login/',                                  views.login_view,          name='login'),
    path('logout/',                                 views.logout_view,         name='logout'),
    path('dashboard/',                              views.dashboard_view,      name='dashboard'),
    path('groups/',                                 views.group_list_view,     name='groups'),
    path('groups/create/',                          views.group_create_view,   name='group_create'),
    path('groups/<int:pk>/',                        views.group_detail_view,   name='group-detail'),
    path('groups/<int:pk>/delete/',                 views.group_delete_view,   name='group_delete'),
    path('groups/<int:pk>/add-member/',             views.add_member_view,     name='add_member'),
    path('groups/<int:pk>/remove/<int:user_id>/',   views.remove_member_view,  name='remove_member'),
    path('groups/<int:group_pk>/upload/',           views.receipt_upload_view, name='receipt_upload'),
    path('groups/<int:pk>/manual-split/',           views.manual_split_view,   name='manual_split'),
    path('groups/<int:pk>/settle-up/',              views.settle_up_view,      name='settle_up'),
    path('receipts/<int:pk>/',                      views.receipt_detail_view, name='receipt-detail'),
    path('receipts/<int:pk>/delete/',               views.receipt_delete_view, name='receipt_delete'),
    path('splits/<int:split_id>/toggle/',           views.mark_paid_view,      name='mark_paid'),
]