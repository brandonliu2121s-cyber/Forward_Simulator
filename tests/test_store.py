"""Run the Node tests for dashboard/store.js (Supabase saved runs) against an in-memory fake of auth + PostgREST."""
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, os.path.join(ROOT, "dev"))
import build_dashboard  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StoreSuite(unittest.TestCase):
    def test_store_suite(self):
        res = subprocess.run(["node", os.path.join(ROOT, "tests", "test_store.js")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class BuildConfig(unittest.TestCase):
    ENV = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY")

    def setUp(self):
        self.old = {k: os.environ.pop(k, None) for k in self.ENV}

    def tearDown(self):
        for k in self.ENV:
            os.environ.pop(k, None)
        for k, v in self.old.items():
            if v is not None:
                os.environ[k] = v

    def test_static_by_default(self):
        if not os.path.exists(os.path.join(ROOT, "dashboard", "config.json")):
            self.assertEqual(build_dashboard.cloud_config_json(), "null")

    def test_env_config_is_embedded(self):
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"] = "https://abcdefghij.supabase.co", "sb_publishable_x"
        self.assertEqual(build_dashboard.cloud_config_json(), '{"url":"https://abcdefghij.supabase.co","key":"sb_publishable_x"}')
        self.assertIn('"key":"sb_publishable_x"', build_dashboard.fragment())

    def test_secret_keys_are_never_embedded(self):
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"] = "https://abcdefghij.supabase.co", "sb_secret_abc"
        with self.assertRaises(SystemExit):
            build_dashboard.cloud_config_json()

    def test_legacy_service_role_jwt_is_refused_but_anon_is_fine(self):
        import base64
        import json

        def jwt(role):
            b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")  # noqa: E731
            return f"{b({'alg': 'HS256'})}.{b({'role': role})}.sig"
        os.environ["SUPABASE_URL"] = "https://abcdefghij.supabase.co"
        os.environ["SUPABASE_PUBLISHABLE_KEY"] = jwt("service_role")
        with self.assertRaises(SystemExit):
            build_dashboard.cloud_config_json()
        os.environ["SUPABASE_PUBLISHABLE_KEY"] = jwt("anon")
        self.assertIn('"url"', build_dashboard.cloud_config_json())


if __name__ == "__main__":
    unittest.main()
