from __future__ import annotations

import unittest

from aipack.security import redact_content, scan_for_secrets


class SecurityTests(unittest.TestCase):
    def test_redacts_group_values_without_hiding_assignment(self) -> None:
        key = "a" * 24
        password = "very-secret-password"
        content = f'API_KEY = "{key}"\npassword = "{password}"\n'

        redacted, count = redact_content(content)

        self.assertEqual(count, 2)
        self.assertIn('API_KEY = "[REDACTED]"', redacted)
        self.assertIn('password = "[REDACTED]"', redacted)
        self.assertNotIn(key, redacted)
        self.assertNotIn(password, redacted)

    def test_scans_multiple_secrets_on_one_line(self) -> None:
        first = "a" * 24
        second = "b" * 24
        content = f"api_key={first}; secret_key={second}\n"

        warnings = scan_for_secrets(content, "config.py")

        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(warning.line_number == 1 for warning in warnings))

    def test_private_key_redaction_covers_key_body(self) -> None:
        content = "\n".join(
            [
                "before = True",
                "-----BEGIN PRIVATE KEY-----",
                "very-private-key-body",
                "-----END PRIVATE KEY-----",
                "after = True",
            ]
        )

        warnings = scan_for_secrets(content, "key.txt")
        redacted, count = redact_content(content)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].line_number, 2)
        self.assertEqual(count, 1)
        self.assertIn("-----BEGIN PRIVATE KEY-----\n[REDACTED]\n-----END PRIVATE KEY-----", redacted)
        self.assertNotIn("very-private-key-body", redacted)

    def test_bearer_redaction_keeps_header(self) -> None:
        token = "x" * 24
        content = f"Authorization: Bearer {token}\n"

        redacted, count = redact_content(content)

        self.assertEqual(count, 1)
        self.assertEqual(redacted, "Authorization: Bearer [REDACTED]\n")

    def test_whole_match_token_redaction_hides_token_prefix(self) -> None:
        token = "sk-" + ("x" * 48)

        redacted, count = redact_content(f'token = "{token}"\n')

        self.assertEqual(count, 1)
        self.assertEqual(redacted, 'token = "[REDACTED]"\n')


if __name__ == "__main__":
    unittest.main()
