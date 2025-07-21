import { c as create_ssr_component, e as escape } from "../../../chunks/ssr.js";
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let status = "Loading...";
  return `<div style="padding: 20px; font-family: monospace;"><h1 data-svelte-h="svelte-1kttz3m">API Connection Test</h1> <p><strong data-svelte-h="svelte-1ftu2mm">Status:</strong> ${escape(status)}</p> ${``} ${``} <h2 data-svelte-h="svelte-d1byaj">Manual Test Links</h2> <ul data-svelte-h="svelte-1nm07s0"><li><a href="http://localhost:8000/health" target="_blank">Backend Health</a></li> <li><a href="http://localhost:8000/api/v1/metrics/system-health" target="_blank">System Health API</a></li> <li><a href="http://localhost:8000/docs" target="_blank">API Documentation</a></li></ul></div>`;
});
export {
  Page as default
};
