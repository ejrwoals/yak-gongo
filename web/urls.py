from django.urls import path

from . import views

app_name = 'web'

urlpatterns = [
    path('', views.home, name='home'),
    path('compare/', views.compare, name='compare'),
    path('compare/result/', views.compare_result, name='compare_result'),
    path('fulltime/', views.fulltime, name='fulltime'),
    path('weekend/', views.weekend, name='weekend'),
    path('etc/', views.etc, name='etc'),
    path('onetime/', views.onetime, name='onetime'),
]
