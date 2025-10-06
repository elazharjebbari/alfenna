module.exports = {
  testDir: 'tests_e2e',
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8000',
    headless: true,
  },
};
