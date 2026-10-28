from django.urls import path

from . import views_public as v

app_name = 'certs'

urlpatterns = [
    path('', v.home, name='home'),
    path('v/<str:number>/', v.verify, name='verify'),
    path('d/<uuid:token>/', v.download, name='download'),
]
