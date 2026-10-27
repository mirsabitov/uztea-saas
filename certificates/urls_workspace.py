"""Included under /workspace/certificates/ inside the "workspace" namespace."""
from django.urls import path

from . import views_workspace as v

urlpatterns = [
    path('', v.templates_list, name='certificates'),
    path('templates/', v.templates_list, name='cert_templates'),
    path('templates/new/', v.template_new, name='cert_template_new'),
    path('templates/<int:pk>/', v.designer, name='cert_designer'),
    path('templates/<int:pk>/preview.pdf', v.template_preview, name='cert_template_preview'),
    path('issue/', v.issue, name='cert_issue'),
    path('issued/', v.issued, name='cert_issued'),
    path('issued/zip/', v.download_batch, name='cert_batch_zip'),
    path('<int:pk>/pdf/', v.download, name='cert_download'),
    path('<int:pk>/action/', v.certificate_action, name='cert_action'),
]
