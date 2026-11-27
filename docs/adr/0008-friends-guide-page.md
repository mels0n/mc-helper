# 0008. A friends guide page, behind the login, with a print view

- Status: accepted
- Date: 2026-11-27

## Context
Getting a friend onto the server is the hardest part of running it. Consoles cannot type in a server address, so they join through the Friends tab. Phones, tablets and computers add the server by address. Parents also have to open settings on the child's Microsoft and Nintendo accounts. The person running the server is a child and needs something to hand to friends and their parents.

## Decision
- The app has a guide page at `/friends-guide`, linked from the home page, and a printer-friendly view at `/friends-guide/print` for printing or taking a screenshot. Both sit behind the same login as the rest of the app.
- The server address, broadcast gamertag and display name come from the boot-validated settings (`SERVER_ADDRESS`, `BROADCAST_GAMERTAG`, `SERVER_DISPLAY_NAME`) and are required: nothing about a particular server is built into the code or the public repository. The port defaults to the Bedrock standard, 19132 (`SERVER_PORT`). Page titles and the top bar use the display name too, and `HELPER_NAME` (default "a grown-up") names who to ask when something is out of the child's hands.
- The two views share one content template. The print view is always light, drops the app navigation and every action form, and prints as a single clean column.
- The guide is plain server-rendered HTML. The only script is the existing small file: it adds copy and print buttons that stay hidden unless the browser supports them.
- The home page shows an "Add yourself first" step while the friends list is empty and the server is answering.

## Alternatives rejected
- **A public page.** The guide shows the server address and the broadcast gamertag. Anyone who found the page could find a server that is meant for approved friends only, and could send friend requests to the broadcast account. Sharing is done by printing or a screenshot instead.
- **A static document outside the app.** It would hold a copy of the address and gamertag that drifts from the real settings.
- **A PDF.** It needs a generator and goes stale the moment a value changes.

## Consequences
The guide's text describes how third-party consoles and parental controls work today, and those menus change. Check the steps when a platform changes its menus.
