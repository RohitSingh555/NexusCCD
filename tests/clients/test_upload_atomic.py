import io
import os
import csv
import pytest
import django
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

# Ensure Django is configured when running under plain pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ccd.settings")
django.setup()

from core.models import Client


@pytest.mark.django_db(transaction=True)
def test_upload_rolls_back_on_bulk_create_failure(client, monkeypatch):
    # Build a minimal valid CSV that results in a new client creation
    csv_io = io.StringIO()
    writer = csv.writer(csv_io)
    writer.writerow(["client_id", "first_name", "last_name", "phone"])  # required columns
    writer.writerow(["1001", "Alex", "Morgan", "5551112222"])  # valid row
    csv_io.seek(0)

    # Wrap the CSV content into a Django UploadedFile
    uploaded = SimpleUploadedFile(
        "clients.csv",
        csv_io.getvalue().encode("utf-8"),
        content_type="text/csv",
    )

    # Force an error during bulk_create to ensure the outer transaction rolls back
    import clients.views as views
    original_bulk_create = views.Client.objects.bulk_create

    def raise_on_bulk_create(objs, batch_size=None):
        raise IntegrityError("Forced failure for atomicity test")

    monkeypatch.setattr(views.Client.objects, "bulk_create", raise_on_bulk_create)

    # Hit the upload endpoint
    url = reverse("clients:upload_process")
    response = client.post(url, {"file": uploaded, "source": "SMIS"})

    # The view catches at the outermost except and returns 500 on failure
    assert response.status_code == 500

    # Verify nothing was persisted due to @transaction.atomic rollback
    assert Client.objects.filter(client_id="1001").count() == 0


