---
name: mcp-headless-oauth
description: Use when MCP OAuth authentication runs on a remote or headless machine (SSH box, no browser) - the localhost callback redirect fails, the auth link can't open a local browser, or the user is port-forwarding (ssh -L) an OAuth callback port. Also when `claude mcp login` auth on a remote needs help, or an SDK/`claude -p` run needs a server that requires sign-in.
---

# MCP Headless OAuth

MCP OAuth redirects the user's browser to `http://localhost:PORT/callback`, but the listener binds the remote machine's localhost. Browser is on the laptop. Fix: paste the redirect back to the remote, or tunnel the port.

Escape hatch: if paste-back fails (provider rejects it, harness has no paste prompt), the `ssh -L` tunnel always works - the browser's localhost redirect is forwarded verbatim to the remote listener, so the flow completes exactly as on a local machine.

Three paths, in preference order:

## 1. Paste-back (Claude Code built-in - no tunnel)

```bash
ssh -t coreweave              # -t: paste prompt needs an interactive terminal
claude mcp login <server>     # auto-detects no browser; add --no-browser to force
```

Open the printed URL in the laptop browser and sign in. The final redirect to `localhost:PORT/callback` fails in the browser - expected. Copy the FULL URL from the address bar (contains `code=` and `state=`), paste it at the remote prompt. Token exchange happens on the remote; redirect_uri still matches, so the provider accepts it.

Same paste-prompt flow appears if the browser redirect fails during in-session `/mcp` auth.

## 2. Pinned-port tunnel (repeatable, best for other harnesses)

Pin the callback port so the tunnel is deterministic across retries:

```bash
claude mcp add --transport http --callback-port 8080 my-server https://mcp.example.com/mcp
# or in add-json: {"type":"http","url":"...","oauth":{"callbackPort":8080}}
```

Then, from the laptop (separate terminal):

```bash
ssh -N -L 8080:127.0.0.1:8080 coreweave
```

Trigger auth, open the URL in the laptop browser - the localhost redirect now tunnels to the remote listener and completes normally. Kill the tunnel after.

## 3. Ephemeral port (no pin configured)

Read the port from the printed callback/redirect URL (e.g. `53058`), then from the laptop:

```bash
ssh -N -L 53058:127.0.0.1:53058 coreweave
```

To add the forward without reconnecting an existing SSH session: Enter, then `~C`, then `-L 53058:127.0.0.1:53058`.

## Gotchas

| Trap | Fix |
|---|---|
| Port is random per attempt by default | Path 3 needs a new forward per retry - or pin it (Path 2) |
| `-L` vs `-R` confusion | `-L` = laptop listens, forwards to the remote's localhost. That's the direction needed here |
| Auth code is single-use and expires fast | Forward/copy promptly after sign-in |
| `claude -p` / Agent SDK can't run OAuth | Run `claude mcp login` or in-session `/mcp` from an interactive session first; stored tokens are reused |
| No `claude mcp auth` command | It's `claude mcp login <name>` / `claude mcp logout <name>` |
| Anthropic-hosted connectors (Microsoft 365, Gmail, Google Calendar) | No local OAuth at all - authorize via claude.ai/customize/connectors |
| Non-OAuth auth (Kerberos, short-lived tokens, internal SSO) | Use `headersHelper`, not OAuth |

Copying credential files between machines is not viable: macOS stores tokens in the system keychain, and no documented credentials-file path exists elsewhere.

For harnesses other than Claude Code without a paste-back prompt, Path 2/3 is the generic answer.
