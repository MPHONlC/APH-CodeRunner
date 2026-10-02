# Security Policy

## Supported versions

Only the latest release of APH-CodeRunner gets security fixes: the newest Version on ESOUI and GitHub Releases (a date-based number such as `2026.09.29.21.48`). Older builds are not patched; update instead.

## Reporting a vulnerability

Please report privately. Open this repository's Security tab and choose "Report a vulnerability". Don't post it as a public issue, an ESOUI comment or a Discord message until a fixed version is out. If you can't use GitHub, contact @APHONlC on ESOUI and don't put the details in a public post.

A useful report has the version you were running, your platform (PC, Xbox or PlayStation), the steps to reproduce it and what an attacker could do with it.

## What counts

Anything in this add-on's code or its GitHub workflows that could harm a player or the repository: unsafe handling of data in SavedVariables, dynamic code execution from untrusted data, leaking the repository's secrets, or pushing code nobody reviewed. Ordinary bugs, crashes and feature ideas go through Issues, not this channel.

Out of scope: bugs in the game client, and third-party libraries (LibAddonMenu-2.0, LibHarvensAddonSettings, LibDebugLogger and the like). Report those to their own authors.

## What to expect

I maintain this alone, so replies take as long as they take. I'll confirm the report, fix it in a new release, and credit you in the changelog if you want that.

## License

All rights reserved; see LICENSE.md. Testing this add-on on your own installation to find problems is fine. Copying, redistributing or selling it is not, and the license's opt-out for AI agents and bots applies to security research as well.
