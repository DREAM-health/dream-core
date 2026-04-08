"""dream_core URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
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
from django.urls import path, include
from dream_core.health_check.views import health_check_view

api_v1_patterns = [
    path('auth/',       include('dream_core.accounts.urls.auth')),
    path('accounts/',   include('dream_core.accounts.urls.accounts')),
    path('audit/',      include('dream_core.audit.urls')),
    path('catalog/',    include('dream_core.catalog.urls')),
    path('facilities/', include('dream_core.facilities.urls')),
    path('patients/',   include('dream_core.patients.urls')),
]

urlpatterns = [
    path('health-check/', health_check_view),
    path('api/core/v1/', include(api_v1_patterns)),
]