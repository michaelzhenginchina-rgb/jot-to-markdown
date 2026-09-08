# Jot

Highlight something while you're reading → save it, with a note, to a plain
Markdown file on your own disk. One file per article.

No account, no cloud, no database. A ~200-line Python server that only listens
on `127.0.0.1`, plus a small Chrome extension (or a bookmarklet, if you'd
rather not install anything).

Requires macOS and Python 3.9+. Everything the core needs is in the standard
library.

## Install

```bash
git clone https://github.com/michaelzhenginchina-rgb/jot-to-markdown.git
cd jot-to-markdown
./install.sh
```

`install.sh` registers the server as a login agent
(`~/Library/LaunchAgents/com.jot.server.plist`) so it's always running, and
generates a local token into `extension/config.js`.

**Run `./install.sh` before loading the extension.** `config.js` is generated,
not committed — the extension won't load without it.

Then load the extension once: **chrome://extensions** → turn on **Developer
mode** (top right) → **Load unpacked** → pick the `extension/` folder.

> Chrome remembers an unpacked extension by its *path*. If you later move or
> rename this folder, Chrome silently drops the extension and you'll need to
> Load unpacked again. Put it somewhere you won't reorganise.

By default notes land in `~/highlights`. To put them somewhere else — an
Obsidian vault, say:

```bash
JOT_STORE=~/Documents/vault/highlights ./install.sh
```

Set `JOT_PORT` the same way if 7777 is taken. Both are remembered, so a bare
`./install.sh` later won't move your notes back.

## Use

Select text, then right-click:

- **Save highlight to Jot** — saves immediately, no dialog. A toast confirms it.
- **Save to Jot with a note…** — opens a panel for a note and tags. `⌘↵` saves, `esc` closes.

`⌘⇧S` opens the note panel without touching the mouse. Right-clicking with
nothing selected offers **Jot a thought about this page** — a note with no
highlight saves fine.

The extension reads the selection from the frame you right-clicked in, so it
works on sites that render the article inside an iframe.

<details>
<summary>Bookmarklet alternative (no extension)</summary>

`install.sh` also writes `install.html`; open it and drag the **Jot** button to
your bookmarks bar. Same panel, but no right-click menu, and it can't see
selections inside iframes.
</details>

## What lands on disk

`~/highlights/2026-08-30-on-strategic-depth.md`

```markdown
---
title: "On Strategic Depth"
url: https://example.com/strategy
site: example.com
author: Someone
saved: 2026-08-30
---

# On Strategic Depth

[example.com](https://example.com/strategy)

---

> Now, you may not be on an actual battlefield, but you are always on a
> metaphorical one. A battlefield where you are both the protagonist and antagonist.

**Note:** don't fully get protagonist/antagonist here

#strategy #vocab

<sub>2026-08-30 11:43</sub>
```

Every later highlight from the same article appends to the same file. Articles
are matched by URL, so two different pieces that happen to share a title get
separate files (`…-on-strategic-depth-2.md`).

The folder is just Markdown — point Obsidian at it, `grep` it, or open it in
anything.

## Files

| | |
|---|---|
| `server.py` | The store. Stdlib only. `GET /ping`, `POST /save`. |
| `extension/background.js` | Context menus, shortcut, talks to the server. |
| `extension/panel.js` | The note panel, injected on demand. |
| `bookmarklet.js` | Bookmarklet version of the panel. |
| `build.py` | Bakes port + token into `extension/config.js` and `install.html`. |
| `install.sh` | LaunchAgent + build. |

After editing the extension, run `python3 build.py` if the token changed, then
hit reload on the extension card in `chrome://extensions`.

## Optional extras

None of these are needed for highlighting; they're small scripts built on top
of the same Markdown folder. Skip them and nothing breaks.

| | |
|---|---|
| `enrich.py` | Looks up a definition for highlights tagged `生词` ("new word") and writes it back into the note. Needs an API key — see below. |
| `pronounce.py` | Renders the word with the macOS `say` voice to an `.m4a` and embeds it, so Obsidian shows a play button. |
| `vocab_book.py` | Gathers every `生词` highlight into one review sheet. Regenerable; never the source of truth. |
| `books_import.py` | Pulls Apple Books highlights into the same folder, in the same format. Re-runs only import what's new. |
| `notes_import.py` | Imports Apple Notes as Markdown, extracting inline images instead of leaving base64 blobs. |

The vocabulary lookups are the one part that talks to the network. Give it a
key with `./set-key.sh` (it reads without echoing and writes to
`<store>/.jot-api-key`, mode 600), or set `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` in the environment. Without a key, the lookups sit out and
everything else works.

## Notes

- **Token.** `<store>/.jot-token` is a shared secret generated at install and
  baked into the extension. Without it the server refuses to write, so a random
  site you visit can't quietly append to your notes.
- **Safari.** Safari blocks `https://` pages from talking to `http://localhost`.
  Chrome, Edge, Brave, Arc and Firefox all allow it. In Safari the bookmarklet
  falls back to copying the formatted Markdown to your clipboard instead — it
  tells you when it does.
- **Logs.** `<store>/.jot.log`.
- **Nothing leaves your machine** except the optional vocabulary lookups.

```bash
launchctl bootout gui/$UID/com.jot.server   # uninstall (then delete the plist)
```

## License

MIT — see [LICENSE](LICENSE).
