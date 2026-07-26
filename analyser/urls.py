"""analyser/urls.py"""
from django.urls import path
from . import views

app_name = "analyser"

urlpatterns = [
    # UI
    path("",                          views.index,          name="index"),

    # SSE analysis streams
    path("analyse/content/",          views.analyse_content, name="analyse_content"),
    path("analyse/visual/",           views.analyse_visual,  name="analyse_visual"),

    # URL download via yt-dlp
    path("fetch-url/",                views.fetch_url,       name="fetch_url"),

    # Export endpoints
    path("download/json/<uuid:job_id>/", views.download_json, name="download_json"),
    path("download/pdf/<uuid:job_id>/",  views.download_pdf,  name="download_pdf"),

    # Job history API
    path("api/jobs/",                 views.job_list,        name="job_list"),
    path("api/jobs/<uuid:job_id>/",   views.job_detail,      name="job_detail"),
    path("api/jobs/<uuid:job_id>/delete/", views.job_delete,  name="job_delete"),
]
