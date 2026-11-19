# LoopWheeGo

> **Read-only mirror.** This repository is synced automatically from LoopWheeGo's private
> source repositories (one for the backend, one for the frontend) on every push to their
> main branch. Development, issues and deployments happen there, so pull requests opened
> here will not be merged. The full commit history of both is preserved below.

LoopWheeGo is a walking and cycling route planner for Singapore. You give it a start point and a
distance, and it generates closed-loop routes that end where they start, or A-to-B routes, on a
self-hosted OSRM routing engine. Fitness mode searches for loops close to your target distance
and effort; Explorer mode favours routes that pass interesting places.

- **Live app:** [loopwheego.app](https://www.loopwheego.app)
- **How it works:** [Loops that end where they start](https://amishtp.tech/blog/loopwheego), the write-up on the loop generator, Fitness mode and Explorer mode

## Layout

| Folder | What it is | Stack |
|---|---|---|
| [`backend/`](backend/) | Route generation API: anchor points, OSRM round trips, scoring, places | Python, FastAPI, OSRM, OpenStreetMap |
| [`frontend/`](frontend/) | Web app: map, route controls, Fitness and Explorer modes, GPX export | Next.js, TypeScript, MapLibre |

Each folder has its own README with setup instructions.

## How the mirror works

Each private repository runs a GitHub Actions workflow on push. It scans the repository for
secrets with gitleaks, and only if that passes, it merges the new commits into its folder here
with `git subtree`, so every original commit is kept. Nothing is published if the scan fails.
