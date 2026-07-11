# Security Boundary

## Credentials And Origin

- Read only `SKILL_GITLAB_BASE_URL` and `SKILL_GITLAB_PAT` as required credentials.
- Reject URL userinfo, query, fragment, traversal, and non-loopback HTTP unless explicitly enabled.
- Preserve self-managed GitLab path prefixes when constructing `/api/v4`.
- Validate every absolute pagination link and redirect against scheme, host, effective port, and API root before attaching the PAT.
- Use the configured CA bundle with normal TLS verification; there is no insecure TLS switch.

## Bounded Transport

- Limit each response even when `Content-Length` is absent or false; bound aggregate pagination by pages, items, bytes, visited URLs, retry delay, and timeout.
- Reject oversized JSON request bodies before opening a connection.
- Retry only GET/HEAD for selected transient responses and connection failures.
- Never retry POST/PUT automatically. A lost response yields `outcome=unknown` and explicit read-before-replay guidance.
- Close success and HTTP-error responses and keep PATs, response secrets, unsafe URLs, and tracebacks out of public errors.

## Guarded Writes

The fingerprint binds normalized origin, operation, method, path/query, canonical body, target identity, and selected preflight state. Description, note, and discussion bodies are represented by length/hash in previews; discussion preflight also hashes existing note bodies.

Apply requires the complete fingerprint, rereads preflight, rejects drift, and sends one POST/PUT. This reduces agent drift but is not server-side compare-and-swap; the post-write reread remains required.

Explicit clear/unassign flags prevent an omitted argument, shell quoting error, or empty file from silently removing metadata.

## Files And Output

Raw repository bytes are never decoded with replacement. Base64 is the default envelope representation. `--text` requires valid UTF-8. `--output` writes through a same-directory temporary file and refuses to replace an existing target unless `--overwrite` is explicit.

## Prohibited Boundary

Project deletion, branch/repository mutation, merge, approval, credential or permission management, CI mutation, and bulk writes have no executor. Exact capability lookup reports them as unsupported. Live production projects are never validation targets.
