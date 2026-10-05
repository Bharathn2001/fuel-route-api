from django.contrib import admin
from django.urls import path

from routing.views import route_api


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/route/", route_api, name="route-api"),
]