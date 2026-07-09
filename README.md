# GaariGuru: Pakistani Used Car Finder

This is the main monorepo containing the decoupled frontend and backend for the GaariGuru application.

For detailed specification of the project requirements, architecture, and roadmap, please see the documents in the workspace root:
- [ReadMe.md](../ReadMe.md) - Project overview and design contract
- [Requirements.md](../Requirements.md) - Environment and setup checklist
- [RoadMap.md](../RoadMap.md) - Folder architecture and developmental phases

## Project Architecture
- `/gaariguru-backend` - FastAPI server with scrapers, SQLModel database, and AI Orchestration (Mistral, Gemini, Llama).
- `/gaariguru-frontend` - React single-page application powered by Vite, Tailwind CSS, and Three.js.
