from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_CONFIG = (
    REPO_ROOT / "scripts" / "ops" / "nginx" / "ego.example.invalid.bootstrap.conf"
)
HTTPS_CONFIG = REPO_ROOT / "scripts" / "ops" / "nginx" / "ego.example.invalid.conf"
RENEWAL_HOOK = (
    REPO_ROOT / "scripts" / "ops" / "certbot" / "10-egolink-nginx-reload.sh"
)
AMAP_COORDINATE_PATH = "/_AMapService/v3/assistant/coordinate/convert"


def _location_bodies(config: str, selector: str) -> list[str]:
    marker = f"location {selector} {{"
    bodies: list[str] = []
    cursor = 0
    while True:
        start = config.find(marker, cursor)
        if start < 0:
            return bodies
        body_start = start + len(marker)
        depth = 1
        position = body_start
        while position < len(config) and depth:
            if config[position] == "{":
                depth += 1
            elif config[position] == "}":
                depth -= 1
            position += 1
        if depth:
            raise AssertionError(f"unterminated location block: {selector}")
        bodies.append(config[body_start : position - 1].strip())
        cursor = position


def _directives(body: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in body.splitlines() if line.strip())


class VpsHttpsConfigTests(unittest.TestCase):
    def test_bootstrap_limits_http_to_acme_for_expected_host(self) -> None:
        config = BOOTSTRAP_CONFIG.read_text(encoding="utf-8")

        self.assertIn("server_name ego.example.invalid;", config)
        self.assertIn("/.well-known/acme-challenge/", config)
        self.assertIn("root /var/www/letsencrypt;", config)
        self.assertIn("location / {\n        return 503;\n    }", config)
        self.assertNotIn("proxy_pass", config)
        self.assertNotIn("listen 443", config)

    def test_https_host_redirects_and_uses_exact_certificate(self) -> None:
        config = HTTPS_CONFIG.read_text(encoding="utf-8")

        self.assertIn("return 301 https://ego.example.invalid$request_uri;", config)
        self.assertIn("listen 443 ssl http2;", config)
        self.assertIn(
            "ssl_certificate /etc/letsencrypt/live/ego.example.invalid/fullchain.pem;",
            config,
        )
        self.assertIn(
            "ssl_certificate_key /etc/letsencrypt/live/ego.example.invalid/privkey.pem;",
            config,
        )
        self.assertIn("include /etc/letsencrypt/options-ssl-nginx.conf;", config)
        self.assertIn("ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;", config)
        self.assertNotIn("ssl_protocols", config)
        self.assertIn("add_header X-Frame-Options SAMEORIGIN always;", config)
        self.assertIn(
            'add_header Strict-Transport-Security "max-age=31536000" always;',
            config,
        )
        self.assertNotIn("includeSubDomains", config)
        self.assertNotIn("ssl_protocols TLSv1 ", config)

    def test_https_proxy_is_loopback_and_preserves_origin_metadata(self) -> None:
        config = HTTPS_CONFIG.read_text(encoding="utf-8")

        self.assertIn("proxy_pass http://127.0.0.1:8790;", config)
        self.assertNotIn("proxy_pass http://0.0.0.0:8790", config)
        for header in (
            "proxy_set_header Host $host;",
            "proxy_set_header X-Real-IP $remote_addr;",
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "proxy_set_header X-Forwarded-Proto $scheme;",
            "proxy_set_header X-Forwarded-Host $host;",
            "proxy_set_header Upgrade $http_upgrade;",
        ):
            self.assertIn(header, config)

    def test_coordinate_convert_access_log_is_disabled_only_for_exact_path(
        self,
    ) -> None:
        config = HTTPS_CONFIG.read_text(encoding="utf-8")
        exact_bodies = _location_bodies(config, f"= {AMAP_COORDINATE_PATH}")
        catch_all_bodies = _location_bodies(config, "/")

        self.assertEqual(len(exact_bodies), 2)
        self.assertEqual(config.count("access_log off;"), 2)
        self.assertTrue(all("access_log off;" in body for body in exact_bodies))
        self.assertEqual(len(catch_all_bodies), 2)
        self.assertTrue(
            all("access_log off;" not in body for body in catch_all_bodies)
        )
        self.assertNotIn(f"location ^~ {AMAP_COORDINATE_PATH}", config)
        self.assertNotIn(f"location ~ {AMAP_COORDINATE_PATH}", config)

    def test_coordinate_locations_preserve_redirect_and_proxy_behavior(
        self,
    ) -> None:
        config = HTTPS_CONFIG.read_text(encoding="utf-8")
        exact_bodies = _location_bodies(config, f"= {AMAP_COORDINATE_PATH}")
        catch_all_bodies = _location_bodies(config, "/")

        exact_redirect = next(body for body in exact_bodies if "return 301" in body)
        normal_redirect = next(
            body for body in catch_all_bodies if "return 301" in body
        )
        exact_proxy = next(body for body in exact_bodies if "proxy_pass" in body)
        normal_proxy = next(body for body in catch_all_bodies if "proxy_pass" in body)

        self.assertEqual(
            tuple(
                directive
                for directive in _directives(exact_redirect)
                if directive != "access_log off;"
            ),
            _directives(normal_redirect),
        )
        self.assertEqual(
            tuple(
                directive
                for directive in _directives(exact_proxy)
                if directive != "access_log off;"
            ),
            _directives(normal_proxy),
        )
        self.assertIn("https://ego.example.invalid$request_uri", exact_redirect)
        self.assertIn("proxy_pass http://127.0.0.1:8790;", exact_proxy)

    def test_configs_contain_no_runtime_credentials(self) -> None:
        combined = BOOTSTRAP_CONFIG.read_text(encoding="utf-8") + HTTPS_CONFIG.read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "EGOLINK_MESSAGE_HUB_TOKEN=",
            "EGOLINK_AMAP_JS_API_KEY=",
            "EGOLINK_AMAP_SECURITY_JS_CODE=",
            "Authorization: Bearer",
        ):
            self.assertNotIn(forbidden, combined)

    def test_renewal_hook_validates_before_reload(self) -> None:
        hook = RENEWAL_HOOK.read_text(encoding="utf-8")
        runbook = (REPO_ROOT / "docs" / "operations" / "VPS_RUNBOOK.md").read_text(
            encoding="utf-8"
        )

        self.assertTrue(hook.startswith("#!/usr/bin/env bash\nset -eu\n"))
        self.assertIn("/usr/sbin/nginx -t", hook)
        self.assertIn("/usr/bin/systemctl reload nginx", hook)
        self.assertLess(
            hook.index("/usr/sbin/nginx -t"),
            hook.index("/usr/bin/systemctl reload nginx"),
        )
        self.assertIn("install -o root -g root -m 755", runbook)
        self.assertIn(
            "/etc/letsencrypt/renewal-hooks/deploy/10-egolink-nginx-reload.sh",
            runbook,
        )


if __name__ == "__main__":
    unittest.main()
