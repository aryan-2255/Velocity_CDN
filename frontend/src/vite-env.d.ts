/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LB_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
