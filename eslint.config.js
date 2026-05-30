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

const testGlobals = {
  afterEach: "readonly",
  describe: "readonly",
  expect: "readonly",
  it: "readonly",
  vi: "readonly",
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
  {
    files: ["tests/js/**/*.js"],
    ...eslint.configs.recommended,
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...browserGlobals, ...testGlobals },
    },
    rules: {
      ...eslint.configs.recommended.rules,
      "no-undef": "error",
    },
  },
];
