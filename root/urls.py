"""
URL configuration for root project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from workspace import views_public as workspace_public

urlpatterns = [
    path('admin/', admin.site.urls),
    path('workspace/', include('workspace.urls')),
    path('set-language/', workspace_public.change_language, name='set_language'),
    path('certificates/', include('certificates.urls_public')),
    path('account/', include('cabinet.urls')),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('', include('app.urls')),
    path('payments/click/', include('click.urls')),
    path('payments/atmos/', include('atmos.urls')),
    path('payments/payme/', include('payme.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
