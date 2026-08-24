import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_ok():
    client = Client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}
