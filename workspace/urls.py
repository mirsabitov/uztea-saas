from django.urls import path

from . import views, views_messages

app_name = 'workspace'

urlpatterns = [
    path('', views.home, name='home'),
    path('people/', views.people_members, name='people'),
    path('people/teachers-bank/', views.people_teachers_bank, name='teachers_bank'),
    path('people/contacts/', views.people_contacts, name='contacts'),
    path('people/<int:pk>/', views.member_profile, name='member_profile'),
    path('people/<int:pk>/preview/', views.member_preview, name='member_preview'),
    path('messages/', views_messages.history, name='messages'),
    path('messages/compose/', views_messages.compose, name='message_compose'),
    path('website/', views.website, name='website'),
    path('forms/', views.forms_list, name='forms'),
    path('forms/studio/', views.form_studio, name='form_studio'),
    path('payments/', views.payments, name='payments'),
    path('partners/', views.partners, name='partners'),
    path('settings/', views.settings_view, name='settings'),
    path('tools/', views.tools, name='tools'),
]
