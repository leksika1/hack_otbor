# Frontend

React + Vite dashboard for the session analyzer. It uploads a `.jsonl` log,
then renders the summary, the deterministic findings, the LLM explanations and
the generated `AGENTS.md`.

```bash
npm install
npm run dev        # http://localhost:5173, /api is proxied to localhost:8000
npm run build      # production bundle in dist/
npm run lint
```

`VITE_API_URL` (see `.env.example`) selects the API base path; it defaults to
`/api`, which the dev server and the nginx image both proxy to the backend, so
no host name is compiled into the bundle.

```
src/
├── api/client.js                 the only place that calls the backend
├── utils/format.js               formatting and colour mapping
├── features/analysis/            upload screen, dashboard and its panels
├── App.jsx                       upload -> report state machine
└── main.jsx
```
