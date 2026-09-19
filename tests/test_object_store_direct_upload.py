from __future__ import annotations

from types import SimpleNamespace

from app.saas.storage import COSObjectStore, OSSObjectStore, S3ObjectStore


def test_s3_signed_put_and_object_size_use_expected_client_calls() -> None:
    calls: list[tuple] = []

    class Client:
        def generate_presigned_url(self, operation, *, Params, ExpiresIn):
            calls.append(("sign", operation, Params, ExpiresIn))
            return "https://s3.example.test/signed-put"

        def head_object(self, *, Bucket, Key):
            calls.append(("head", Bucket, Key))
            return {"ContentLength": 123}

    store = object.__new__(S3ObjectStore)
    store.bucket = "bucket"
    store.client = Client()

    assert store.signed_put_url("tenant/page.mp4") == "https://s3.example.test/signed-put"
    assert store.object_size("tenant/page.mp4") == 123
    assert calls[0][0:2] == ("sign", "put_object")
    assert calls[0][2] == {"Bucket": "bucket", "Key": "tenant/page.mp4"}
    assert calls[1] == ("head", "bucket", "tenant/page.mp4")


def test_oss_signed_put_and_object_size_use_expected_bucket_calls() -> None:
    calls: list[tuple] = []

    class Bucket:
        def sign_url(self, method, key, expires):
            calls.append(("sign", method, key, expires))
            return "https://oss.example.test/signed-put"

        def head_object(self, key):
            calls.append(("head", key))
            return SimpleNamespace(content_length=456)

    store = object.__new__(OSSObjectStore)
    store.bucket = Bucket()

    assert store.signed_put_url("tenant/page.wav") == "https://oss.example.test/signed-put"
    assert store.object_size("tenant/page.wav") == 456
    assert calls[0][0:3] == ("sign", "PUT", "tenant/page.wav")
    assert calls[1] == ("head", "tenant/page.wav")


def test_cos_signed_put_and_object_size_use_expected_client_calls() -> None:
    calls: list[tuple] = []

    class Client:
        def get_presigned_url(self, *, Method, Bucket, Key, Expired):
            calls.append(("sign", Method, Bucket, Key, Expired))
            return "https://cos.example.test/signed-put"

        def head_object(self, *, Bucket, Key):
            calls.append(("head", Bucket, Key))
            return {"Content-Length": "789"}

    store = object.__new__(COSObjectStore)
    store.bucket = "bucket-appid"
    store.client = Client()

    assert store.signed_put_url("tenant/page.mp4") == "https://cos.example.test/signed-put"
    assert store.object_size("tenant/page.mp4") == 789
    assert calls[0][0:4] == ("sign", "PUT", "bucket-appid", "tenant/page.mp4")
    assert calls[1] == ("head", "bucket-appid", "tenant/page.mp4")
