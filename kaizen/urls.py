"""kaizen/urls.py — root URL conf"""
from django.urls import path, include

urlpatterns = [
    path("", include("analyser.urls")),
]
