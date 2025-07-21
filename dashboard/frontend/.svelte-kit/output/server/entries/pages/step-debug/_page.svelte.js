import { c as create_ssr_component, e as escape, f as each } from "../../../chunks/ssr.js";
import "../../../chunks/api.js";
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let step = 1;
  let logs = [];
  return `<div style="padding: 20px; font-family: monospace; max-width: 1200px; margin: 0 auto;"><h1 data-svelte-h="svelte-148wpk6">🔍 Step-by-Step Dashboard Debug</h1> <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;"><strong data-svelte-h="svelte-1jk1i71">Current Step:</strong> ${escape(step)}/4
    <br> <strong data-svelte-h="svelte-1ftu2mm">Status:</strong> ${escape("Loading...")}</div> <div style="background: #000; color: #0f0; padding: 15px; border-radius: 5px; height: 300px; overflow-y: auto; margin: 20px 0;"><div style="color: #fff; margin-bottom: 10px;" data-svelte-h="svelte-1omwlnr"><strong>Debug Log:</strong></div> ${each(logs, (log) => {
    return `<div style="${"color: " + escape(
      log.type === "error" ? "#ff6b6b" : log.type === "success" ? "#51cf66" : "#0ff",
      true
    ) + ";"}">[${escape(log.timestamp)}] ${escape(log.message)} </div>`;
  })}</div> ${``} ${``} <div style="margin: 20px 0; text-align: center;" data-svelte-h="svelte-glqza8"><a href="/" style="margin-right: 15px; color: blue; text-decoration: none;">← Back to Main Dashboard</a> <a href="/simple" style="margin-right: 15px; color: blue; text-decoration: none;">Simple Dashboard</a> <a href="/debug" style="color: blue; text-decoration: none;">API Debug</a></div></div>`;
});
export {
  Page as default
};
