module.exports = {
  legalSearchApi: {
    input: "./contracts/openapi.yaml",
    output: {
      target: "./src/lib/api/generated/client.ts",
      schemas: "./src/lib/api/generated/model",
      client: "react-query",
      mode: "split",
      override: {
        mutator: {
          path: "./src/lib/api/http.ts",
          name: "httpClient",
        },
      },
    },
  },
};
