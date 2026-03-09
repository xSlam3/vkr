from botocore.exceptions import EndpointConnectionError

from scripts import setup_local_s3


class FakeSetupClient:
    def __init__(self, existing_buckets=None, fail_attempts=0):
        self.existing_buckets = existing_buckets or []
        self.fail_attempts = fail_attempts
        self.calls = 0
        self.created_bucket = None
        self.cors_bucket = None
        self.cors_config = None
        self.policy_bucket = None
        self.policy_document = None

    def list_buckets(self):
        self.calls += 1
        if self.calls <= self.fail_attempts:
            raise EndpointConnectionError(endpoint_url="http://127.0.0.1:9000")
        return {"Buckets": [{"Name": name} for name in self.existing_buckets]}

    def create_bucket(self, Bucket):
        self.created_bucket = Bucket
        self.existing_buckets.append(Bucket)

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.cors_bucket = Bucket
        self.cors_config = CORSConfiguration

    def put_bucket_policy(self, Bucket, Policy):
        self.policy_bucket = Bucket
        self.policy_document = Policy


def test_ensure_bucket_creates_when_missing():
    client = FakeSetupClient(existing_buckets=["other-bucket"])
    setup_local_s3.ensure_bucket(client, "jewelry-media")
    assert client.created_bucket == "jewelry-media"


def test_ensure_bucket_skips_when_exists():
    client = FakeSetupClient(existing_buckets=["jewelry-media"])
    setup_local_s3.ensure_bucket(client, "jewelry-media")
    assert client.created_bucket is None


def test_configure_cors_sets_expected_rules():
    client = FakeSetupClient()
    setup_local_s3.configure_cors(client, "jewelry-media")

    assert client.cors_bucket == "jewelry-media"
    rules = client.cors_config["CORSRules"][0]
    assert "GET" in rules["AllowedMethods"]
    assert "POST" in rules["AllowedMethods"]
    assert "http://localhost:5173" in rules["AllowedOrigins"]
    assert "http://localhost:3000" in rules["AllowedOrigins"]


def test_configure_public_read_sets_policy():
    client = FakeSetupClient()
    setup_local_s3.configure_public_read(client, "jewelry-media")

    assert client.policy_bucket == "jewelry-media"
    assert "s3:GetObject" in client.policy_document
    assert "arn:aws:s3:::jewelry-media/*" in client.policy_document


def test_wait_for_s3_retries_then_succeeds(monkeypatch):
    client = FakeSetupClient(fail_attempts=2)
    monkeypatch.setattr(setup_local_s3.time, "sleep", lambda _: None)
    setup_local_s3.wait_for_s3(client, timeout_seconds=5)
    assert client.calls >= 3


def test_main_orchestrates_setup(monkeypatch):
    events = []

    class StubClient:
        pass

    def fake_build():
        events.append("build")
        return StubClient()

    def fake_wait(client):
        assert isinstance(client, StubClient)
        events.append("wait")

    def fake_ensure(client, bucket):
        assert isinstance(client, StubClient)
        assert bucket == "demo-bucket"
        events.append("ensure")

    def fake_cors(client, bucket):
        assert isinstance(client, StubClient)
        assert bucket == "demo-bucket"
        events.append("cors")

    def fake_policy(client, bucket):
        assert isinstance(client, StubClient)
        assert bucket == "demo-bucket"
        events.append("policy")

    monkeypatch.setattr(setup_local_s3, "build_s3_client", fake_build)
    monkeypatch.setattr(setup_local_s3, "wait_for_s3", fake_wait)
    monkeypatch.setattr(setup_local_s3, "ensure_bucket", fake_ensure)
    monkeypatch.setattr(setup_local_s3, "configure_cors", fake_cors)
    monkeypatch.setattr(setup_local_s3, "configure_public_read", fake_policy)
    monkeypatch.setattr(setup_local_s3, "env", lambda name, default: "demo-bucket")

    setup_local_s3.main()

    assert events == ["build", "wait", "ensure", "cors", "policy"]
