import { c as create_ssr_component, e as escape, f as each } from "../../../chunks/ssr.js";
import "../../../chunks/api.js";
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let apiStatus = "Testing...";
  let logs = [];
  return `<div style="padding: 20px; font-family: monospace;"><h1 data-svelte-h="svelte-2ae6o3">🔧 Dashboard API Debug</h1> <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0;"><strong data-svelte-h="svelte-1ftu2mm">Status:</strong> ${escape(apiStatus)}</div> ${``} <h2 data-svelte-h="svelte-3d3hyk">📋 API Test Log</h2> <div style="background: #000; color: #0f0; padding: 15px; border-radius: 5px; height: 200px; overflow-y: auto; font-family: monospace;">${each(logs, (log) => {
    return `<div>${escape(log)}</div>`;
  })}</div> ${``} <h2 data-svelte-h="svelte-14z6tzv">🔗 Useful Links</h2> <div style="margin: 20px 0;" data-svelte-h="svelte-11l59gr"><a href="/" style="margin-right: 15px; color: blue;">← Back to Dashboard</a> <a href="http://localhost:8000/docs" target="_blank" style="margin-right: 15px; color: blue;">API Docs</a> <a href="http://localhost:8000/health" target="_blank" style="color: blue;">Health Check</a></div></div>`;
});
export {
  Page as default
};
