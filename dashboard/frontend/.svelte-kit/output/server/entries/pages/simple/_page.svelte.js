import { c as create_ssr_component } from "../../../chunks/ssr.js";
import "../../../chunks/api.js";
const _page_svelte_svelte_type_style_lang = "";
const css = {
  code: "@keyframes svelte-1c698dq-spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}",
  map: null
};
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  $$result.css.add(css);
  return `<div style="padding: 20px; font-family: sans-serif;"><h1 data-svelte-h="svelte-iqk4n4">🧬 Simple Dashboard Test</h1> ${`<div style="text-align: center; padding: 40px;" data-svelte-h="svelte-1q0v5eq"><div style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 2s linear infinite; margin: 0 auto;"></div> <p>Loading...</p></div>`} <div style="margin: 20px 0; text-align: center;" data-svelte-h="svelte-trcwir"><a href="/" style="margin-right: 15px; color: blue; text-decoration: none;">← Back to Main Dashboard</a> <a href="/debug" style="margin-right: 15px; color: blue; text-decoration: none;">Debug Page</a> <a href="/test" style="color: blue; text-decoration: none;">API Test</a></div> </div>`;
});
export {
  Page as default
};
