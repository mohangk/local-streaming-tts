import eslint from "@eslint/js";

const browserGlobals = {
  Blob: "readonly",
  EventSource: "readonly",
  File: "readonly",
  FileReader: "readonly",
  FormData: "readonly",
  Image: "readonly",
  URL: "readonly",
  XMLHttpRequest: "readonly",
  clearTimeout: "readonly",
  console: "readonly",
  document: "readonly",
  fetch: "readonly",
  navigator: "readonly",
  setTimeout: "readonly",
  window: "readonly",
};

export default [
  {
    ignores: ["node_modules/**"],
  },
  {
    files: ["src/tts_app/static/**/*.js"],
    ...eslint.configs.recommended,
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: browserGlobals,
    },
    rules: {
      ...eslint.configs.recommended.rules,
      "no-undef": "error",
    },
  },
];
