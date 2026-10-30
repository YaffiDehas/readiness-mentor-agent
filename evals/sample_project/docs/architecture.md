# Architecture
Layers: screens -> hooks/store -> services -> apiClient.
- Screens never call axios directly; they dispatch Redux Toolkit thunks from src/store.
- All HTTP goes through src/services/apiClient.ts (base URL, auth header, error mapping).
- Reusable UI lives in src/components/shared (DataTable is the standard list/table component).
- Every new slice needs a test in src/__tests__.
