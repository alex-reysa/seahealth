/// <reference types="vite/client" />

declare module '*.topojson?raw' {
  const content: string;
  export default content;
}
