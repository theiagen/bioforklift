

export const index = 4;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/simple/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/4.9b5ea02b.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/api.a517d1be.js","_app/immutable/chunks/auth.d93981a9.js","_app/immutable/chunks/index.bca36699.js"];
export const stylesheets = ["_app/immutable/assets/4.6338f187.css"];
export const fonts = [];
