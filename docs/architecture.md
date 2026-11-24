# Architecture

Sysmon App separates metric collection from presentation.

## Overview

```text
Linux system
    |
    v
Python daemon
    |
    +---- collectors
    |
    +---- latest snapshot
    |
    +---- HTTP API
    |       |
    |       +---- GET /stats
    |       |
    |       +---- GET /events (SSE)
    |
    v
React dashboard
    |
    +---- Browser
    |
    +---- Tauri desktop window
```

## Daemon

The daemon runs the system collectors in a single collection cycle. It stores the latest snapshot and makes that snapshot available to all clients.

This avoids running a separate collector for each browser or desktop client.

The daemon serves the built frontend and exposes the metrics API.

## Frontend

The frontend uses React, TypeScript, and Vite.

On startup, it loads the current snapshot from `GET /stats`. It then subscribes to `GET /events` for live updates.

When the SSE connection becomes inactive, the frontend falls back to periodic requests to `/stats`. It returns to SSE when events are received again.

The frontend displays metrics. It does not send system actions.

## Desktop application

The desktop application uses Tauri 2.

It opens the same dashboard served by the daemon. When no daemon is listening on the configured port, the desktop application starts its bundled daemon and manages its lifecycle.

Closing the window hides the application in the system tray when a tray watcher is available.

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Dashboard |
| `GET /stats` | Latest JSON snapshot |
| `GET /events` | Server-Sent Events stream |
| `GET /static/*` | Frontend assets |

Both `/stats` and `/events` expose the same snapshot data.

## Network and privacy

The default host is `0.0.0.0` to support access from other devices on the local network.

The API has no authentication. Use `127.0.0.1` when network access is not required.
