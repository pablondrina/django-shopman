from django.urls import include, path

urlpatterns = [
    path("api/", include("shopman.orderman.api.urls")),
]
