from django.urls import path

from exchange import views

urlpatterns = [
    path("", views.picker, name="picker"),
    path("chat/<str:persona_id>/", views.chat, name="chat"),
    path("about/", views.about, name="about"),
    path("demo/", views.demo, name="demo"),
    path("docs/", views.docs, name="docs"),
    path("api/chat", views.api_chat, name="api_chat"),
    path("api/presign", views.api_presign, name="api_presign"),
    path("api/report", views.api_report, name="api_report"),
    path("api/points", views.api_points, name="api_points"),
    path("healthz", views.healthz, name="healthz"),
]
