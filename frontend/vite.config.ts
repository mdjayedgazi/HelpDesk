import { defineConfig } from 'vite-plus';

export default defineConfig({
  fmt: {
      semi: false,
      singleQuote: true,
      jsxSingleQuote: true,
  },
  lint: {"jsPlugins":[{"name":"vite-plus","specifier":"vite-plus/oxlint-plugin"}],"rules":{"vite-plus/prefer-vite-plus-imports":"error"},"options":{"typeAware":true,"typeCheck":true}},
});
