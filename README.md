<!-- @format -->

# Predictive Healthcare Triage & Readmission Risk Visualizer

A Vue 3 dashboard for exploring synthetic 30-day hospital readmission risk. The frontend uses D3 and communicates with a FastAPI service that trains a scikit-learn model at startup.

> This project uses synthetic data for demonstration only. It is not a clinical tool and must not be used for medical decisions.

## Features

- Cohort risk visualization with low, moderate, and high risk tiers
- Risk prediction for an individual patient profile
- Per-factor risk contribution explanations
- Synthetic model metrics and cohort metadata
- FastAPI Swagger documentation
- Single Docker image that serves the API and built Vue application

## Project Structure

```text
Health-check/
├── backend/
│   ├── main.py                 # FastAPI application and model logic
│   ├── requirements.txt        # Runtime Python dependencies
│   ├── requirements-dev.txt    # Runtime dependencies plus test tools
│   └── tests/test_api.py       # API tests
├── frontend/
│   ├── src/                    # Vue components and dashboard
│   ├── package.json
│   └── vite.config.js          # Development API proxy
├── Dockerfile                  # Multi-stage frontend and backend image
├── docker-compose.yml
├── render.yaml                 # Render deployment configuration
└── .github/workflows/ci.yml    # Backend, frontend, and Docker checks
```

## Requirements

For local development, install:

- Python 3.12 or newer
- Node.js 20 or newer and npm
- Docker Desktop, if using Docker

## Run Locally on Windows

Open Command Prompt or PowerShell in the repository root:

```bat
cd /d E:\company\hackathon\Health-check\backend
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --port 8000
```

Leave the backend terminal running. In a second terminal, start the Vue development server:

```bat
cd /d E:\company\hackathon\Health-check\frontend
npm install
npm run dev
```

Open the dashboard at <http://localhost:5173>. Vite proxies `/api` requests to the backend at port 8000.

To run the backend tests:

```bat
cd /d E:\company\hackathon\Health-check\backend
.venv\Scripts\activate
pytest -q
```

The backend API and interactive Swagger docs are available at:

- <http://localhost:8000/api/health>
- <http://localhost:8000/docs>

### macOS and Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Run with Docker

From the repository root:

```bash
docker compose up --build
```

Open <http://localhost:8000>. The container builds the Vue application, installs the Python runtime dependencies, serves the compiled frontend, and exposes the API from the same origin.

Stop the container with:

```bash
docker compose down
```

## API

| Method | Endpoint       | Description                                                  |
| ------ | -------------- | ------------------------------------------------------------ |
| `GET`  | `/api/health`  | Returns service and model readiness                          |
| `GET`  | `/api/meta`    | Returns feature definitions, thresholds, AUC, and prevalence |
| `GET`  | `/api/cohort`  | Returns the synthetic cohort sorted by risk                  |
| `POST` | `/api/predict` | Predicts risk for the supplied patient features              |

Example prediction request:

```json
{
  "features": {
    "age": 65,
    "prior_admissions": 1,
    "ed_visits": 1,
    "length_of_stay": 5,
    "charlson": 2,
    "medications": 8,
    "hemoglobin": 12.5
  }
}
```

The seven required feature keys are `age`, `prior_admissions`, `ed_visits`, `length_of_stay`, `charlson`, `medications`, and `hemoglobin`. Values outside the configured ranges are clamped by the API.

## Configuration

| Variable       | Default                 | Purpose                                                        |
| -------------- | ----------------------- | -------------------------------------------------------------- |
| `PORT`         | `8000`                  | Port used by the container entrypoint                          |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins                       |
| `STATIC_DIR`   | `backend/static`        | Directory containing the built frontend when served by FastAPI |

The model is trained on synthetic data during application startup, so the first health check may take several seconds.

## Deployment

The Docker image listens on `$PORT` and uses `/api/health` as its health check. It does not require a database.

- **Render:** Create a new Blueprint from the repository; `render.yaml` provides the service configuration.
- **Cloud Run:** Deploy the repository with `gcloud run deploy --source .`.
- **Fly.io:** Run `fly launch`, then `fly deploy`.
- **VPS:** Run `docker compose up -d --build` and place a TLS reverse proxy in front of the service.

Allocate at least 512 MB of memory and allow time for model training during the first startup.

## Continuous Integration

GitHub Actions runs on pushes and pull requests targeting `main` and performs:

1. Backend dependency installation and pytest execution
2. Frontend dependency installation and production build
3. Docker image build

## Limitations and Next Steps

- Replace `synth()` in `backend/main.py` with validated application data while preserving the feature contract.
- For production use, train offline and load a versioned model instead of training at startup.
- Add authentication, authorization, audit logging, privacy controls, calibration and fairness evaluation before handling real health data.
- Obtain appropriate clinical, legal, security, and regulatory review before any clinical application.
