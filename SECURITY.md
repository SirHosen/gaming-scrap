# Security & Responsible Use

## Reporting a vulnerability

If you discover a security issue (e.g. a way NESTfetch could be abused to attack
a host, a dependency vulnerability, or unsafe handling of credentials in
`settings.py` / `.env`), please report it privately:

- Email: **hoseaoktarivanes@gmail.com** with the subject `NESTfetch security`.
- Do **not** open a public issue for undisclosed vulnerabilities.
- Include reproduction steps and the affected version (`nestfetch.__version__`).

You can expect an acknowledgement within a reasonable time frame. Fixes are
released as a patch version and noted in `CHANGELOG.md`.

## Supported versions

Only the latest minor release line receives security fixes. Please upgrade
before reporting issues against older versions.

## Responsible-use policy

NESTfetch is a **metadata scraper** for publicly listed download pages. It is
intended for indexing, availability/link-health checking, and personal
cataloguing. To keep usage ethical and low-impact:

- **robots.txt is respected by default** (`RESPECT_ROBOTS_TXT = True`). Do not
  disable it to crawl areas a site has disallowed.
- **Rate-limit and cache.** Use `--rate-limit` / `PER_HOST_RATE_LIMIT` and the
  on-disk cache to minimise load on target sites.
- **Identify honestly.** Keep a truthful `User-Agent`; do not impersonate.
- **Respect the law and site terms.** You are responsible for ensuring your use
  complies with local law, copyright, and each site's terms of service.
- NESTfetch does **not** download or host copyrighted content — it only records
  publicly visible links and metadata.

Secrets (tokens, webhook URLs, SMTP passwords) belong in environment variables
or a git-ignored `.env` file — never commit them. See `.env.example`.
