# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev          # Start dev server at localhost:3000
npm run build        # Build to dist/
npm run preview      # Serve the production build locally
npm run lint         # TypeScript type-check (tsc --noEmit)
npm run og:generate  # Regenerate public/og-image.png (Playwright + sharp)
```

`npm run lint` is type-checking only. ESLint (`eslint.config.mjs`) is configured solely for the Firebase security rules plugin, not for the app source.

There are no automated tests. Firestore security rules have a test file (`firestore.rules.test.ts`) but no test runner is wired up in `package.json`.

**Build/serving note:** `vite.config.ts` sets `base: '/neighbourhoods/'`, so the app is served from that subpath (production: `carte.utoronto.ca/neighbourhoods/`), not the domain root. The `@` import alias resolves to the project root.

## Architecture

This is a single-page React + Vite + Tailwind CSS app. All state lives in `App.tsx` and is passed down to two sibling components:

- **`src/components/Sidebar.tsx`** — the left panel with the 3-step wizard UI (name → draw → submit), form submission to Firestore, share/copy logic, and two portalled modals (welcome, data info). It reads/writes `localStorage` to persist submission state across page loads.
- **`src/components/MapEditor.tsx`** — the MapLibre GL map (right/top panel). Handles click-to-place polygon points, ghost line preview on mousemove, polygon closing, and renders all GeoJSON sources/layers on the map. The map is initialized once in a `useEffect` on mount; subsequent effects sync React state → MapLibre sources via `setData()`.

**Step flow:** Step 1 (name input) → Step 2 (draw polygon on map) → Step 3 (optional text fields + submit). Closing the polygon in `MapEditor` automatically advances to step 3. `App.tsx` controls the step state and passes setters to both components.

**Firebase:** `src/firebase.ts` exports `db` (Firestore), `auth`, and `handleFirestoreError`. The Firestore database ID is non-default (passed explicitly to `getFirestore`). In `import.meta.env.DEV` mode, `handleSubmit` skips the Firestore write and only logs the payload to console.

**Map data files** (under `src/assets/toronto-data/`): GeoJSON files for transit lines, transit stations, and park points are loaded as static JSON imports and added as MapLibre sources on map load.

**Coordinate convention:** The app uses `LatLngTuple = [lat, lng]` (Leaflet convention) throughout React state, but MapLibre and GeoJSON expect `[lng, lat]`. Conversion happens inside the `createLineFeature`, `createPolygonFeature`, and `createPointFeature` helpers in `MapEditor.tsx`.

## Design system

Tailwind v4. Custom UofT brand colors are defined as CSS variables (e.g. `uoft-blue`, `uoft-teal`, `uoft-border`) and used throughout. No `tailwind.config.js` — configuration is done via CSS.

## Environment

Copy `.env.example` to `.env.local`. The only variable is `APP_URL`. Firebase config is loaded from `firebase-applet-config.json` (not from env vars).

## Firestore security rules

Rules are in `firestore.rules`. Only the `neighborhoods` collection is writable. `create` requires the full `isValidNeighborhood` shape; `update` additionally checks that `createdAt` is unchanged. `list` and `delete` are always denied.

## Deployment

`.github/workflows/deploy.yml` runs on push to `main`. It builds the multi-stage `Dockerfile` (Node build → `dist/` served by a Caddy static-file server, see `Caddyfile.internal`), pushes the image to `ghcr.io/uoft-carte/toronto-neighbourhoods`, then SSHes into the production VM to `docker compose pull/up` the `neighbourhoods` service and runs a health check against the live URL. Deploy secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`) are required repo secrets.
