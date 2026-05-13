[<-- Back to Main Index](../../README.md)
# Frontend Overview: What Exists Today and How It Works

## 1. What this frontend is

This frontend is the web control panel for the synthetic data pipeline.

In practical terms, it gives users a guided workflow to:
1. Start from data ingestion,
2. inspect datasets and detected schema,
3. move toward profiling, configuration, training, generation, and audit.

```
[ Browser ]  <-- HTTP/JSON -->  [ FastAPI backend ]  <-- Python -->  [ Your pipeline ]
     ^
     |
This folder (frontend) builds what the browser shows.
```

The **frontend** is just a program that runs in the user's browser. It draws
buttons, forms, tables — and when the user clicks something, it calls the
backend API over HTTP (the same protocol as any website). The backend doesn't
know or care what the frontend looks like; it just answers requests.

This separation is why you could later replace the frontend entirely (with a
mobile app, a CLI, another web UI) without touching Python code.


## 2. Technologies

This table is intentionally specific to this repository, not generic labels.

| Technology | Role in this project | Why this is the right fit here |
|---|---|---|
| Next.js 16 (App Router) | Provides the full web app structure: routing by folder, layouts, build pipeline, dev server, and production runtime | Lets the team ship a multi-page product shell quickly without hand-rolling routing/build conventions |
| React 19 | Component model for building reusable UI blocks | Makes wizard pages, layout pieces, and data views composable and maintainable |
| TypeScript | Enforces typed contracts in UI and API models | Reduces runtime mistakes when integrating with backend responses |
| Tailwind CSS v4 | Styling system used across the app | Fast iteration with consistent visual language and low CSS maintenance overhead |
| shadcn + Base UI stack | Source-owned UI primitives and components (cards, tables, forms, badges, etc.) | Team can customize deeply without being locked into a black-box component library |
| TanStack React Query | Data fetching, caching, loading/error states, and polling | Perfect for inspection jobs that transition from in progress to completed and need reactive UI updates |
| Axios | HTTP client wrapper for backend communication | Centralizes base URL and request behavior in one place, making API wiring predictable |
| Sonner | Toast feedback system | Gives immediate UX feedback for success and error events during async operations |
| openapi-typescript (installed) | Planned type generation from backend OpenAPI schema | Prevents frontend/backend drift once generation step is wired in fully |

CORS (see backend/src/api/main.py line 37): allow the Next.js dev server (and optional extra origins via env var) to call the API from the browser. Without this, browsers block cross-origin requests between http://localhost:3000 and http://localhost:8000. 

## 3. Frontend code files structure

### App shell and routing
- src/app/layout.tsx: global layout wrapper (sidebar, header, content area, providers).
- src/app/page.tsx: landing page.
- src/app/pipeline/.../page.tsx: each wizard step route.

### Pipeline navigation model
- src/lib/pipeline-steps.ts: single source of truth for step order, labels, and implementation flags.

### Data and API integration
- src/lib/api.ts: axios client and typed API models currently used by frontend.
- src/lib/query-provider.tsx: React Query provider and caching defaults.

### Reusable UI
- src/components/layout/: sidebar, header, wizard shell, coming-soon wrapper.
- src/components/ui/: shared primitives and components.


## 4. How to run locally

```bash
make setup
````

```bash
make frontend
```

The frontend itself cannot do much without the backend as well, for that run

```bash
make api
```

in a different terminal and open the UI:
- http://localhost:3000

For more execution details check out [Use the CLI](../setup/use_cli.md).

For the frontend to know where the backend is, we need to have a .env.local file with:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

This is automatically done by the _backend.src.sessions.configs bootstrap_ script executed at the end of make setup, you can change the path here if the backend url changes.

[<-- Back to Main Index](../../README.md)