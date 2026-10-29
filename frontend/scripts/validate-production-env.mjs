const value = process.env.VITE_API_BASE_URL;

if (!value) {
  console.error("VITE_API_BASE_URL must be set when building the production frontend.");
  process.exit(1);
}

try {
  const apiUrl = new URL(value);
  if (
    apiUrl.protocol !== "https:" ||
    apiUrl.pathname !== "/api/v1" ||
    apiUrl.username ||
    apiUrl.password ||
    apiUrl.search ||
    apiUrl.hash
  ) {
    throw new Error();
  }
} catch {
  console.error("VITE_API_BASE_URL must be an HTTPS URL ending exactly in /api/v1.");
  process.exit(1);
}
