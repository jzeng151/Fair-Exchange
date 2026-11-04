/// <reference types="vite/client" />
interface ImportMetaEnv {
  /** Chat API base URL for live mode (#116). Unset: the live tab is hidden and only the scripted demo runs. */
  readonly VITE_FEX_API_URL?: string
}
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
