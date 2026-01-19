# API Reference

RepGen provides a REST API built with FastAPI.

## Running the API

To start the API server:

```bash
uvicorn repgen.server:app --reload
```

The server typically runs on port `8000`.

## Documentation

Once the server is running, you can access the interactive API documentation at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

These pages provide detailed information about endpoints, request/response schemas, and allow you to test API calls directly from the browser.
