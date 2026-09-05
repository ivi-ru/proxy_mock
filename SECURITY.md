# Security policy

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting on this repository
("Security" → "Report a vulnerability"), or email <aryabokon@ivi.ru>.

Reports are reviewed weekly. If a report is accepted, the fix ships in the next release and the
CHANGELOG says what was fixed.

## Supported versions

Fixes are released for the latest published version of the current major line. Older versions
are not patched — upgrade instead.

## The security model

proxy-mock is a testing tool. An instance is meant to run in a test environment, on a network
you control, and not on the public internet. The properties below are by design, documented in
the README, and are not vulnerabilities:

- **No authentication.** Anyone who can reach the port can configure mocks, read captured
  traffic and clear the storage.
- **Proxying to arbitrary hosts.** A mock can proxy to any URL, which makes an exposed instance
  a request-forwarding tool (SSRF). `PROXY_MOCK_ALLOWED_PROXY_HOSTS` restricts the targets;
  by default any host is allowed.
- **Traffic capture.** Request bodies and headers, including any credentials the service under
  test sends, are kept in memory and returned by `GET /traffic`.

What *is* worth reporting: anything that lets a request escape those documented boundaries — for
example remote code execution through a configuration payload, a path that reads or writes files
outside the process, or a way to make the service run code from a proxied response.
