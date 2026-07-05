"""
URL configuration for config project.

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
from django.conf import settings
from django.urls import path, include

urlpatterns = [
    path('', include('web.urls')),
]

# 관리자 앱이 설치된 로컬에서만 /admin/ 라우트를 노출한다.
# (배포본은 settings_prod에서 admin 앱을 제외하므로 이 블록을 건너뛴다)
if 'django.contrib.admin' in settings.INSTALLED_APPS:
    from django.contrib import admin
    urlpatterns.insert(0, path('admin/', admin.site.urls))
