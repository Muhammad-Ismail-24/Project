# Drive Fetch: Pakistani Used Car Finder

This is the main monorepo containing the decoupled frontend and backend for the Drive Fetch application.

For detailed specification of the project requirements, architecture, and roadmap, please see the documents in the workspace root:
- [ReadMe.md](../ReadMe.md) - Project overview and design contract
- [Requirements.md](../Requirements.md) - Environment and setup checklist
- [RoadMap.md](../RoadMap.md) - Folder architecture and developmental phases

## 📂 Project Structure

- `/drivefetch-backend` - FastAPI server with scrapers, SQLModel database, and AI Orchestration (Mistral, Gemini, Llama).
- `/drivefetch-frontend` - React single-page application powered by Vite, Tailwind CSS, and Three.js.

## Environment Variables

Make sure to configure the following environment variables in your deployment environments (e.g. Vercel for frontend, Render for backend):

- `FRONTEND_URL`: The full URL of the deployed frontend, e.g. `https://drivefetch.vercel.app`