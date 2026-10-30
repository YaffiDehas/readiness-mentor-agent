# Backend API (v1)
- GET /sensors - list sensors (id, name, status)
- GET /sensors/{id}/readings?from&to - readings for a sensor
- GET /sensors/{id}/alerts - NOT IMPLEMENTED YET, backend team is still working on it; contract not final.
Auth: Bearer token added by apiClient.
