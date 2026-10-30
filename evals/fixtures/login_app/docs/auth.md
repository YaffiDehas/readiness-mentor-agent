# Authentication
The backend exposes POST /auth/login which returns an accessToken.
The access token is stored with AsyncStorage by src/auth/tokenStorage.ts and attached by src/services/apiClient.ts.
Refresh tokens are NOT defined yet. The identity provider has not been decided.
