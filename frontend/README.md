# Model Deployer console

React + TypeScript single-page app for the Model Deployer platform. It talks to
the Django API under `/api` and is built with Vite, Tailwind CSS 4, and Zustand.

## Pages

| Route | Page | Purpose |
|---|---|---|
| `/` | `Explore` | Public model explorer |
| `/login`, `/register` | `Auth` | Sign in / create an account |
| `/dashboard/*` | `Dashboard` | Uploads, deployments, deploy logs, API keys, inference testing |
| `/docs` | `Docs` | In-app API reference |
| `/:namespace` | `UserProfile` | A user's public models |
| `/:namespace/:model_name` | `ModelRepo` | Single model page with README and inference form |

`/docs` must stay registered above `/:namespace` in `src/App.tsx`, otherwise it
is matched as a profile lookup for a user named "docs".

## Development

The API is expected on `http://127.0.0.1:8000`; Vite proxies `/api` there
(`vite.config.ts`), so no environment variables are required.

```sh
npm install
npm run dev        # http://localhost:5173
```

Other scripts:

```sh
npm run build      # type-check (tsc -b) and build to dist/
npm run preview    # serve the production build locally
npm run lint       # oxlint
```

## How requests are made

`src/api.ts` wraps `fetch` and prefixes every path with `/api`. It attaches the
JWT from `localStorage` as `Authorization: Bearer <token>` and redirects to
`/login` on `401`. Auth state and the current user live in `src/store.ts`.

## Container image

`Dockerfile.frontend` builds the app with Node and serves `dist/` from nginx.
`nginx.conf` falls back to `index.html` for client-side routes and reverse
proxies `/api/` to the `api` service, so the console and API share an origin in
the Compose stack.
