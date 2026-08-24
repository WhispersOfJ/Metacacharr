import pytest
from django.test import Client


@pytest.mark.django_db
def test_post_with_mismatched_host_header_is_rejected(settings):
    settings.ALLOWED_HOSTS = ["*"]
    client = Client()
    response = client.post("/admin/login/", HTTP_HOST="evil.example.com")
    assert response.status_code == 403


@pytest.mark.django_db
def test_get_with_mismatched_host_header_is_allowed(settings):
    client = Client()
    response = client.get("/admin/login/", HTTP_HOST="evil.example.com")
    assert response.status_code != 403
