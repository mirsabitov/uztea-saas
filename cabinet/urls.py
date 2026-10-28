from django.urls import path

from . import views

app_name = 'cabinet'

urlpatterns = [
    path('', views.home, name='home'),
    path('profile/', views.profile, name='profile'),
    path('subscription/', views.subscription, name='subscription'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('access/', views.request_link, name='request_link'),
    path('set-password/<uidb64>/<token>/', views.set_password, name='set_password'),
]
