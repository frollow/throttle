from django.http import HttpResponse
from django.urls import path


def _dummy_view(request):
    return HttpResponse("ok")


urlpatterns = [path("__dummy__/", _dummy_view, name="dummy")]
